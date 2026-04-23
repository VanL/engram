"""Backend-neutral state-store operations.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-13], [MM-19], [MM-20]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-5], [MWS-8]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from engram._constants import (
    SQLITE_MAX_INT64,
    TIER_ARC,
    TIER_EPISODE,
    TIER_MOMENT,
    VAULT_SCHEMA_VERSION_KEY,
)
from engram._exceptions import (
    MemoryItemNotFoundError,
    StoreDataError,
    StoreVersionError,
)
from engram._models import FailedItemRecord, MemoryItem
from engram.store._sql.base import StateSQL
from engram.store.db import SQLRunner
from engram.store.id_generator import MemoryIdGenerator


class StateStoreCore:
    """Shared state-store operations implemented against SQLRunner."""

    def __init__(self, runner: SQLRunner, sql: StateSQL) -> None:
        self._runner = runner
        self._sql = sql
        self._id_generator = MemoryIdGenerator(runner)

    def close(self) -> None:
        """Close the underlying SQL runner."""

        self._runner.close()

    def get_metadata(self) -> dict[str, str]:
        """Return vault metadata from the authoritative store."""

        rows = self._runner.run(
            """
            SELECT key, value
            FROM vault_meta
            ORDER BY key ASC
            """
        )
        return {str(row[0]): str(row[1]) for row in rows}

    def get_schema_version(self) -> int:
        """Return the explicit schema version for this vault."""

        metadata = self.get_metadata()
        raw_version = metadata.get(VAULT_SCHEMA_VERSION_KEY)
        if raw_version is None:
            raise StoreVersionError("Engram state store is missing schema_version")
        try:
            return int(raw_version)
        except ValueError as exc:
            raise StoreVersionError(
                f"invalid Engram schema version: {raw_version!r}"
            ) from exc

    def put_item(self, item: MemoryItem) -> MemoryItem:
        """Persist a memory item."""

        with self._runner.transaction():
            self._runner.run(
                """
                INSERT INTO memory_items (
                    id,
                    tier,
                    text,
                    created_at,
                    access,
                    relevance,
                    indexed_at,
                    summary_terms_json,
                    processing_attempts,
                    last_processing_error,
                    last_task_tid,
                    last_task_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.tier,
                    item.text,
                    item.created_at,
                    item.access,
                    item.relevance,
                    item.indexed_at,
                    json.dumps(list(item.summary_terms)),
                    0,
                    None,
                    None,
                    None,
                ),
                fetch=False,
            )
            self._id_generator.observe_existing_id(item.id)
        return item

    def allocate_memory_id(self, physical_ns: int) -> int:
        """Allocate a unique memory ID for the given physical timestamp."""

        return self._id_generator.generate(physical_ns)

    def get_item(self, item_id: int, tier: int | None = None) -> MemoryItem | None:
        """Fetch a memory item."""

        if tier is None:
            rows = self._runner.run(
                f"""
                SELECT {self._sql.MEMORY_ITEM_SELECT}
                FROM memory_items
                WHERE id = ?
                """,
                (item_id,),
            )
        else:
            rows = self._runner.run(
                f"""
                SELECT {self._sql.MEMORY_ITEM_SELECT}
                FROM memory_items
                WHERE id = ? AND tier = ?
                """,
                (item_id, tier),
            )
        if not rows:
            return None
        return self._item_from_row(rows[0])

    def get_items(self, item_ids: Sequence[int]) -> list[MemoryItem]:
        """Fetch multiple memory items preserving input order."""

        if not item_ids:
            return []
        placeholders = ", ".join("?" for _ in item_ids)
        rows = self._runner.run(
            f"""
            SELECT {self._sql.MEMORY_ITEM_SELECT}
            FROM memory_items
            WHERE id IN ({placeholders})
            """,
            tuple(item_ids),
        )
        by_id = {int(row[0]): self._item_from_row(row) for row in rows}
        return [by_id[item_id] for item_id in item_ids if item_id in by_id]

    def list_recent_items(self, *, tier: int, limit: int) -> list[MemoryItem]:
        """List recent items in descending time order."""

        rows = self._runner.run(
            f"""
            SELECT {self._sql.MEMORY_ITEM_SELECT}
            FROM memory_items
            WHERE tier = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tier, limit),
        )
        return [self._item_from_row(row) for row in rows]

    def list_high_value_items(
        self,
        *,
        limit: int,
        exclude_ids: Sequence[int] = (),
    ) -> list[MemoryItem]:
        """List high-value items in descending score order."""

        clauses = []
        params: list[Any] = []
        if exclude_ids:
            placeholders = ", ".join("?" for _ in exclude_ids)
            clauses.append(f"id NOT IN ({placeholders})")
            params.extend(exclude_ids)
        where_sql = ""
        if clauses:
            where_sql = "WHERE " + " AND ".join(clauses)
        rows = self._runner.run(
            f"""
            SELECT {self._sql.MEMORY_ITEM_SELECT}
            FROM memory_items
            {where_sql}
            ORDER BY (access * relevance) DESC, created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [self._item_from_row(row) for row in rows]

    def list_uncoalesced_moments(self) -> list[MemoryItem]:
        """List moments that are not yet children of an episode."""

        return self.list_uncoalesced_items(
            child_tier=TIER_MOMENT,
            parent_tier=TIER_EPISODE,
        )

    def list_uncoalesced_episodes(self) -> list[MemoryItem]:
        """List episodes that are not yet children of an arc."""

        return self.list_uncoalesced_items(
            child_tier=TIER_EPISODE,
            parent_tier=TIER_ARC,
        )

    def list_uncoalesced_items(
        self,
        *,
        child_tier: int,
        parent_tier: int,
    ) -> list[MemoryItem]:
        """List items not yet attached to a parent at the next tier."""

        rows = self._runner.run(
            f"""
            SELECT {", ".join(f"m.{column}" for column in self._sql.MEMORY_ITEM_COLUMNS)}
            FROM memory_items AS m
            WHERE m.tier = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM memory_edges AS e
                  JOIN memory_items AS p ON p.id = e.parent_id
                  WHERE e.child_id = m.id
                    AND p.tier = ?
              )
            ORDER BY m.created_at ASC
            """,
            (child_tier, parent_tier),
        )
        return [self._item_from_row(row) for row in rows]

    def create_episode(
        self,
        *,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create an episode and attach its ordered children."""

        return self.create_summary_item(
            tier=TIER_EPISODE,
            text=text,
            summary_terms=summary_terms,
            child_ids=child_ids,
            created_at=created_at,
        )

    def create_arc(
        self,
        *,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create an arc and attach its ordered child episodes."""

        return self.create_summary_item(
            tier=TIER_ARC,
            text=text,
            summary_terms=summary_terms,
            child_ids=child_ids,
            created_at=created_at,
        )

    def create_summary_item(
        self,
        *,
        tier: int,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create a summary item and attach its ordered children."""

        with self._runner.transaction():
            if child_ids:
                max_child_id, max_child_created_at = self._summary_timeline_anchor(
                    child_ids
                )
                if created_at is not None and created_at != max_child_created_at:
                    raise StoreDataError(
                        "summary created_at must match max child created_at"
                    )
                item_id = self._first_unused_memory_id_after(max_child_id)
                item_created_at = max_child_created_at
            else:
                if created_at is None:
                    raise StoreDataError(
                        "childless summary creation requires created_at"
                    )
                item_id = self.allocate_memory_id(created_at)
                item_created_at = created_at
            item = MemoryItem(
                id=item_id,
                tier=tier,
                text=text,
                created_at=item_created_at,
                summary_terms=tuple(summary_terms),
            )
            self._runner.run(
                """
                INSERT INTO memory_items (
                    id,
                    tier,
                    text,
                    created_at,
                    access,
                    relevance,
                    indexed_at,
                    summary_terms_json,
                    processing_attempts,
                    last_processing_error,
                    last_task_tid,
                    last_task_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.tier,
                    item.text,
                    item.created_at,
                    item.access,
                    item.relevance,
                    item.indexed_at,
                    json.dumps(list(item.summary_terms)),
                    0,
                    None,
                    None,
                    None,
                ),
                fetch=False,
            )
            self._runner.run_many(
                """
                INSERT INTO memory_edges (parent_id, child_id, position)
                VALUES (?, ?, ?)
                """,
                (
                    (item.id, child_id, position)
                    for position, child_id in enumerate(child_ids)
                ),
            )
            self._id_generator.observe_existing_id(item.id)
        return item

    def _summary_timeline_anchor(self, child_ids: Sequence[int]) -> tuple[int, int]:
        if len(set(child_ids)) != len(child_ids):
            raise StoreDataError("summary child_ids must not contain duplicates")
        placeholders = ", ".join("?" for _ in child_ids)
        rows = self._runner.run(
            f"""
            SELECT id, created_at
            FROM memory_items
            WHERE id IN ({placeholders})
            """,
            tuple(child_ids),
        )
        by_id = {int(row[0]): int(row[1]) for row in rows}
        for child_id in child_ids:
            if child_id not in by_id:
                raise MemoryItemNotFoundError(child_id)
        return max(child_ids), max(by_id.values())

    def _first_unused_memory_id_after(self, anchor_id: int) -> int:
        if anchor_id < 0:
            raise StoreDataError("summary MID anchor cannot be negative")
        candidate = anchor_id + 1
        while candidate < SQLITE_MAX_INT64:
            if not self._memory_id_exists(candidate):
                return candidate
            candidate += 1
        raise StoreDataError("no valid summary MID remains after child anchor")

    def _memory_id_exists(self, item_id: int) -> bool:
        rows = self._runner.run(
            """
            SELECT 1
            FROM memory_items
            WHERE id = ?
            LIMIT 1
            """,
            (item_id,),
        )
        return bool(rows)

    def get_children(self, parent_id: int) -> list[MemoryItem]:
        """Fetch ordered children for a parent item."""

        rows = self._runner.run(
            f"""
            SELECT {", ".join(f"c.{column}" for column in self._sql.MEMORY_ITEM_COLUMNS)}
            FROM memory_edges AS e
            JOIN memory_items AS c ON c.id = e.child_id
            WHERE e.parent_id = ?
            ORDER BY e.position ASC
            """,
            (parent_id,),
        )
        return [self._item_from_row(row) for row in rows]

    def get_parent(self, child_id: int, *, parent_tier: int) -> MemoryItem | None:
        """Fetch the immediate parent at `parent_tier` for a child item."""

        rows = self._runner.run(
            f"""
            SELECT {", ".join(f"p.{column}" for column in self._sql.MEMORY_ITEM_COLUMNS)}
            FROM memory_edges AS e
            JOIN memory_items AS p ON p.id = e.parent_id
            WHERE e.child_id = ?
              AND p.tier = ?
            ORDER BY p.id ASC
            LIMIT 1
            """,
            (child_id, parent_tier),
        )
        if not rows:
            return None
        return self._item_from_row(rows[0])

    def find_summary_containing(
        self,
        anchor_id: int,
        *,
        parent_tier: int,
    ) -> MemoryItem | None:
        """Fetch the summary whose child-ID support range contains `anchor_id`."""

        rows = self._runner.run(
            f"""
            WITH containing AS (
                SELECT e.parent_id
                FROM memory_edges AS e
                JOIN memory_items AS p ON p.id = e.parent_id
                JOIN memory_items AS c ON c.id = e.child_id
                WHERE p.tier = ?
                GROUP BY e.parent_id
                HAVING MIN(c.id) <= ? AND MAX(c.id) >= ?
                ORDER BY e.parent_id ASC
                LIMIT 1
            )
            SELECT {", ".join(f"m.{column}" for column in self._sql.MEMORY_ITEM_COLUMNS)}
            FROM memory_items AS m
            WHERE m.id = (SELECT parent_id FROM containing)
            """,
            (parent_tier, anchor_id, anchor_id),
        )
        if not rows:
            return None
        return self._item_from_row(rows[0])

    def get_next_repairable_item(self) -> MemoryItem | None:
        """Fetch the next item that still needs local repair work."""

        rows = self._runner.run(
            f"""
            SELECT {self._sql.MEMORY_ITEM_SELECT}
            FROM memory_items
            WHERE tier = ?
              AND (
                  indexed_at IS NULL
                  OR last_processing_error IS NOT NULL
              )
            ORDER BY
                CASE
                    WHEN indexed_at IS NULL AND last_processing_error IS NULL THEN 0
                    WHEN last_processing_error IS NOT NULL THEN 1
                    ELSE 2
                END,
                created_at ASC,
                id ASC
            LIMIT 1
            """,
            (TIER_MOMENT,),
        )
        if not rows:
            return None
        return self._item_from_row(rows[0])

    def record_processing_success(self, item_id: int, *, updated_at: int) -> None:
        """Record successful deferred processing for one item."""

        with self._runner.transaction():
            self._runner.run(
                """
                UPDATE memory_items
                SET last_processing_error = NULL,
                    last_task_updated_at = ?,
                    processing_attempts = processing_attempts + 1
                WHERE id = ?
                """,
                (updated_at, item_id),
                fetch=False,
            )

    def record_processing_failure(
        self,
        item_id: int,
        *,
        updated_at: int,
        error: str,
    ) -> None:
        """Record deferred-processing failure for one item."""

        with self._runner.transaction():
            self._runner.run(
                """
                UPDATE memory_items
                SET last_processing_error = ?,
                    last_task_updated_at = ?,
                    processing_attempts = processing_attempts + 1
                WHERE id = ?
                """,
                (error, updated_at, item_id),
                fetch=False,
            )

    def record_task_submission(
        self,
        item_id: int,
        *,
        task_tid: str,
        updated_at: int,
    ) -> None:
        """Record last-known Weft correlation for one item."""

        with self._runner.transaction():
            self._runner.run(
                """
                UPDATE memory_items
                SET last_task_tid = ?,
                    last_task_updated_at = ?
                WHERE id = ?
                """,
                (task_tid, updated_at, item_id),
                fetch=False,
            )

    def count_items_needing_processing(self) -> int:
        """Return the number of tier-0 items still needing downstream work."""

        rows = self._runner.run(
            """
            SELECT COUNT(*) AS total
            FROM memory_items
            WHERE tier = ?
              AND (
                  indexed_at IS NULL
                  OR last_processing_error IS NOT NULL
              )
            """,
            (TIER_MOMENT,),
        )
        return int(rows[0][0]) if rows else 0

    def count_unindexed_items(self) -> int:
        """Return the number of tier-0 items not yet indexed."""

        rows = self._runner.run(
            """
            SELECT COUNT(*) AS total
            FROM memory_items
            WHERE tier = ?
              AND indexed_at IS NULL
            """,
            (TIER_MOMENT,),
        )
        return int(rows[0][0]) if rows else 0

    def count_failed_processing_items(self) -> int:
        """Return the number of tier-0 items with recorded failure state."""

        rows = self._runner.run(
            """
            SELECT COUNT(*) AS total
            FROM memory_items
            WHERE tier = ?
              AND last_processing_error IS NOT NULL
            """,
            (TIER_MOMENT,),
        )
        return int(rows[0][0]) if rows else 0

    def list_failed_items(self, *, limit: int) -> list[FailedItemRecord]:
        """Return recent failed background-processing records for inspection."""

        rows = self._runner.run(
            f"""
            SELECT {self._sql.FAILED_ITEM_SELECT}
            FROM memory_items
            WHERE tier = ?
              AND last_processing_error IS NOT NULL
            ORDER BY COALESCE(last_task_updated_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (TIER_MOMENT, limit),
        )
        return [self._failed_item_from_row(row) for row in rows]

    def count_items_by_tier(self) -> dict[int, int]:
        """Return item counts keyed by tier."""

        rows = self._runner.run(
            """
            SELECT tier, COUNT(*) AS total
            FROM memory_items
            GROUP BY tier
            ORDER BY tier ASC
            """
        )
        return {int(row[0]): int(row[1]) for row in rows}

    def count_indexed_items(self) -> int:
        """Return the number of items marked indexed in SQLite."""

        rows = self._runner.run(
            """
            SELECT COUNT(*) AS total
            FROM memory_items
            WHERE indexed_at IS NOT NULL
            """
        )
        return int(rows[0][0]) if rows else 0

    def update_indexed_at(self, item_id: int, *, indexed_at: int) -> MemoryItem:
        """Record the latest index update time."""

        with self._runner.transaction():
            self._runner.run(
                """
                UPDATE memory_items
                SET indexed_at = ?
                WHERE id = ?
                """,
                (indexed_at, item_id),
                fetch=False,
            )
        item = self.get_item(item_id)
        if item is None:  # pragma: no cover - defensive
            raise MemoryItemNotFoundError(item_id)
        return item

    def update_indexed_at_many(
        self,
        item_ids: Sequence[int],
        *,
        indexed_at: int,
    ) -> None:
        """Record the latest index update time for multiple items."""

        if not item_ids:
            return
        placeholders = ", ".join("?" for _ in item_ids)
        with self._runner.transaction():
            self._runner.run(
                f"""
                UPDATE memory_items
                SET indexed_at = ?
                WHERE id IN ({placeholders})
                """,
                (indexed_at, *item_ids),
                fetch=False,
            )

    def increment_access(self, item_ids: Sequence[int]) -> None:
        """Increment access for the given item IDs."""

        if not item_ids:
            return
        placeholders = ", ".join("?" for _ in item_ids)
        with self._runner.transaction():
            self._runner.run(
                f"""
                UPDATE memory_items
                SET access = access + 1.0
                WHERE id IN ({placeholders})
                """,
                tuple(item_ids),
                fetch=False,
            )

    def set_item_importance(self, item_id: int, *, relevance: float) -> MemoryItem:
        """Update item importance stored as relevance."""

        with self._runner.transaction():
            self._runner.run(
                """
                UPDATE memory_items
                SET relevance = ?
                WHERE id = ?
                """,
                (relevance, item_id),
                fetch=False,
            )
        item = self.get_item(item_id)
        if item is None:
            raise MemoryItemNotFoundError(item_id)
        return item

    def all_items(self) -> list[MemoryItem]:
        """List all items in ascending time order."""

        rows = self._runner.run(
            f"""
            SELECT {self._sql.MEMORY_ITEM_SELECT}
            FROM memory_items
            ORDER BY created_at ASC, id ASC
            """
        )
        return [self._item_from_row(row) for row in rows]

    def _item_from_row(self, row: tuple[Any, ...]) -> MemoryItem:
        return MemoryItem(
            id=int(row[0]),
            tier=int(row[1]),
            text=str(row[2]),
            created_at=int(row[3]),
            access=float(row[4]),
            relevance=float(row[5]),
            indexed_at=int(row[6]) if row[6] is not None else None,
            summary_terms=tuple(json.loads(str(row[7]))),
        )

    def _failed_item_from_row(self, row: tuple[Any, ...]) -> FailedItemRecord:
        error = row[6]
        if error is None:  # pragma: no cover - defensive
            raise RuntimeError("failed item record requires last_processing_error")
        return FailedItemRecord(
            id=int(row[0]),
            tier=int(row[1]),
            text=str(row[2]),
            created_at=int(row[3]),
            indexed_at=int(row[4]) if row[4] is not None else None,
            processing_attempts=int(row[5]),
            error=str(error),
            last_task_tid=str(row[7]) if row[7] is not None else None,
            last_task_updated_at=int(row[8]) if row[8] is not None else None,
        )
