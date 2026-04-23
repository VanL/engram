"""SQLite state store for Engram.

This module preserves the existing `SQLiteStateStore` public class while
delegating setup and operations to the simplebroker-style backend foundation.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-13], [MM-19], [MM-20]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-5], [MWS-8]
- docs/specs/12-local-app-surface.md [LAS-4], [LAS-5], [LAS-7], [LAS-10]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from engram._constants import DEFAULT_SQLITE_FILENAME
from engram._exceptions import VaultNotInitializedError
from engram._models import FailedItemRecord, MemoryItem
from engram.store._sql import sqlite as sqlite_sql
from engram.store.backends.sqlite import SQLiteBackend
from engram.store.core import StateStoreCore
from engram.store.pathing import (
    validate_database_parent_directory,
    validate_safe_path_components,
)


class SQLiteStateStore:
    """SQLite-backed transactional state store."""

    def __init__(self, vault_path: Path, *, create: bool = True) -> None:
        validate_safe_path_components(DEFAULT_SQLITE_FILENAME)
        self._db_path = vault_path / DEFAULT_SQLITE_FILENAME
        if not self._db_path.exists() and not create:
            raise VaultNotInitializedError(str(vault_path))
        if create:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        validate_database_parent_directory(self._db_path)

        self._backend = SQLiteBackend()
        self._runner = self._backend.create_runner(self._db_path)
        self._backend.setup(self._runner, create=create, vault_path=vault_path)
        self._core = StateStoreCore(self._runner, sqlite_sql)

    @property
    def db_path(self) -> Path:
        """Return the SQLite database path."""

        return self._db_path

    def close(self) -> None:
        """Close the underlying SQLite resources."""

        self._core.close()

    def get_metadata(self) -> dict[str, str]:
        """Return vault metadata from the authoritative store."""

        return self._core.get_metadata()

    def get_schema_version(self) -> int:
        """Return the explicit schema version for this vault."""

        return self._core.get_schema_version()

    def put_item(self, item: MemoryItem) -> MemoryItem:
        """Persist a memory item."""

        return self._core.put_item(item)

    def allocate_memory_id(self, physical_ns: int) -> int:
        """Allocate a unique memory ID for the given physical timestamp."""

        return self._core.allocate_memory_id(physical_ns)

    def get_item(self, item_id: int, tier: int | None = None) -> MemoryItem | None:
        """Fetch a memory item."""

        return self._core.get_item(item_id, tier=tier)

    def get_items(self, item_ids: Sequence[int]) -> list[MemoryItem]:
        """Fetch multiple memory items preserving input order."""

        return self._core.get_items(item_ids)

    def list_recent_items(self, *, tier: int, limit: int) -> list[MemoryItem]:
        """List recent items in descending time order."""

        return self._core.list_recent_items(tier=tier, limit=limit)

    def list_high_value_items(
        self,
        *,
        limit: int,
        exclude_ids: Sequence[int] = (),
    ) -> list[MemoryItem]:
        """List high-value items in descending score order."""

        return self._core.list_high_value_items(limit=limit, exclude_ids=exclude_ids)

    def list_uncoalesced_moments(self) -> list[MemoryItem]:
        """List moments that are not yet children of an episode."""

        return self._core.list_uncoalesced_moments()

    def list_uncoalesced_episodes(self) -> list[MemoryItem]:
        """List episodes that are not yet children of an arc."""

        return self._core.list_uncoalesced_episodes()

    def list_uncoalesced_items(
        self,
        *,
        child_tier: int,
        parent_tier: int,
    ) -> list[MemoryItem]:
        """List items not yet attached to a parent at the next tier."""

        return self._core.list_uncoalesced_items(
            child_tier=child_tier,
            parent_tier=parent_tier,
        )

    def create_episode(
        self,
        *,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create an episode and attach its ordered children."""

        return self._core.create_episode(
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

        return self._core.create_arc(
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

        return self._core.create_summary_item(
            tier=tier,
            text=text,
            summary_terms=summary_terms,
            child_ids=child_ids,
            created_at=created_at,
        )

    def get_children(self, parent_id: int) -> list[MemoryItem]:
        """Fetch ordered children for a parent item."""

        return self._core.get_children(parent_id)

    def get_parent(self, child_id: int, *, parent_tier: int) -> MemoryItem | None:
        """Fetch the immediate parent at `parent_tier` for a child item."""

        return self._core.get_parent(child_id, parent_tier=parent_tier)

    def find_summary_containing(
        self,
        anchor_id: int,
        *,
        parent_tier: int,
    ) -> MemoryItem | None:
        """Fetch the summary whose child-ID support range contains `anchor_id`."""

        return self._core.find_summary_containing(
            anchor_id,
            parent_tier=parent_tier,
        )

    def get_next_repairable_item(self) -> MemoryItem | None:
        """Fetch the next item that still needs local repair work."""

        return self._core.get_next_repairable_item()

    def record_processing_success(self, item_id: int, *, updated_at: int) -> None:
        """Record successful deferred processing for one item."""

        self._core.record_processing_success(item_id, updated_at=updated_at)

    def record_processing_failure(
        self,
        item_id: int,
        *,
        updated_at: int,
        error: str,
    ) -> None:
        """Record deferred-processing failure for one item."""

        self._core.record_processing_failure(
            item_id,
            updated_at=updated_at,
            error=error,
        )

    def record_task_submission(
        self,
        item_id: int,
        *,
        task_tid: str,
        updated_at: int,
    ) -> None:
        """Record last-known Weft correlation for one item."""

        self._core.record_task_submission(
            item_id,
            task_tid=task_tid,
            updated_at=updated_at,
        )

    def count_items_needing_processing(self) -> int:
        """Return the number of tier-0 items still needing downstream work."""

        return self._core.count_items_needing_processing()

    def count_unindexed_items(self) -> int:
        """Return the number of tier-0 items not yet indexed."""

        return self._core.count_unindexed_items()

    def count_failed_processing_items(self) -> int:
        """Return the number of tier-0 items with recorded failure state."""

        return self._core.count_failed_processing_items()

    def list_failed_items(self, *, limit: int) -> list[FailedItemRecord]:
        """Return recent failed background-processing records for inspection."""

        return self._core.list_failed_items(limit=limit)

    def count_items_by_tier(self) -> dict[int, int]:
        """Return item counts keyed by tier."""

        return self._core.count_items_by_tier()

    def count_indexed_items(self) -> int:
        """Return the number of items marked indexed in SQLite."""

        return self._core.count_indexed_items()

    def update_indexed_at(self, item_id: int, *, indexed_at: int) -> MemoryItem:
        """Record the latest index update time."""

        return self._core.update_indexed_at(item_id, indexed_at=indexed_at)

    def update_indexed_at_many(
        self,
        item_ids: Sequence[int],
        *,
        indexed_at: int,
    ) -> None:
        """Record the latest index update time for multiple items."""

        self._core.update_indexed_at_many(item_ids, indexed_at=indexed_at)

    def increment_access(self, item_ids: Sequence[int]) -> None:
        """Increment access for the given item IDs."""

        self._core.increment_access(item_ids)

    def set_item_importance(self, item_id: int, *, relevance: float) -> MemoryItem:
        """Update item importance stored as relevance."""

        return self._core.set_item_importance(item_id, relevance=relevance)

    def all_items(self) -> list[MemoryItem]:
        """List all items in ascending time order."""

        return self._core.all_items()
