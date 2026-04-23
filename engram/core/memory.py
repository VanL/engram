"""Public Engram memory API for the local memory app.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-1], [MM-19], [MM-21]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-5], [MWS-18], [MWS-23], [MWS-27]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12], [LAS-19], [LAS-29]
- docs/specs/13-context-assembly-and-arcs.md [CAA-1], [CAA-5], [CAA-11]
- docs/specs/14-embedded-weft-execution-model.md [EWM-16]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-10], [FCI-16]
"""

from __future__ import annotations

import importlib
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engram._constants import (
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_IMPORTANCE,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_VAULT_DIR_NAME,
    MAX_BUILTIN_TIER,
    RECALL_SCOPE_ITEM,
    TIER_ARC,
    TIER_EPISODE,
    TIER_MOMENT,
    normalize_recall_scope,
    recall_scope_tier,
    tier_name,
)
from engram._exceptions import (
    InvalidImportanceError,
    InvalidMemoryTextError,
    MemoryItemNotFoundError,
    VaultNotFoundError,
)
from engram._models import (
    ContextView,
    MemoryItem,
    ProcessResult,
    RebuildResult,
    SearchResult,
    VaultStatus,
)
from engram.core.coalesce import choose_summary_window
from engram.core.context import (
    build_context_view,
    resolve_budgets,
    select_items_for_budget,
    used_tokens,
)
from engram.core.embeddings import (
    DeterministicEmbedder,
    EmbeddingModel,
    SentenceTransformerEmbedder,
    embedder_to_lance_function,
)
from engram.core.llm_tasks import summarize_items_with_llm
from engram.core.scoring import boosted_search_score, reciprocal_rank_fusion
from engram.index.lance import LanceIndex
from engram.runtime import weft as weft_runtime
from engram.store.factory import open_state_store

try:
    fcntl: Any = importlib.import_module("fcntl")
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


@dataclass(slots=True)
class _FusionCandidate:
    """Internal ranked retrieval candidate."""

    id: int
    tier: int
    text: str
    source: str
    fused_score: float


RecallScope = str | int


class Engram:
    """Hierarchical memory entry point for the minimum slice."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        create: bool = False,
        embedder: EmbeddingModel | None = None,
        submit_background: bool = True,
    ) -> None:
        self._vault_path = self._resolve_vault_path(path)
        if not self._vault_path.exists():
            if not create:
                raise VaultNotFoundError(str(self._vault_path))
            self._vault_path.mkdir(parents=True, exist_ok=True)
        self._store = open_state_store(self._vault_path, create=create)
        self._embedder = embedder or SentenceTransformerEmbedder()
        self._index = LanceIndex(
            self._vault_path,
            embedding_function=embedder_to_lance_function(self._embedder),
        )
        self._submit_background = submit_background

    @classmethod
    def init(
        cls,
        path: str | Path | None = None,
        *,
        embedder: EmbeddingModel | None = None,
        autostart: bool = True,
        submit_background: bool = True,
    ) -> Engram:
        """Create or initialize a vault and return an Engram handle.

        Spec:
            - [LAS-1]
            - [LAS-29]
        """
        vault_path = cls._resolve_vault_path(path)
        weft_runtime.initialize_embedded_weft_project(
            vault_path,
            autostart=autostart,
        )
        return cls(
            path,
            create=True,
            embedder=embedder,
            submit_background=submit_background,
        )

    @classmethod
    def open(
        cls,
        path: str | Path | None = None,
        *,
        embedder: EmbeddingModel | None = None,
        submit_background: bool = True,
    ) -> Engram:
        """Open an existing vault without silently creating one.

        Spec:
            - [LAS-2]
            - [LAS-29]
        """
        return cls(
            path,
            create=False,
            embedder=embedder,
            submit_background=submit_background,
        )

    @staticmethod
    def record_processing_failure_for_vault(
        vault_path: str | Path,
        *,
        item_id: int,
        error: str,
        updated_at: int | None = None,
    ) -> None:
        """Record item-processing failure for a vault without opening Engram."""

        resolved_vault_path = Path(vault_path).expanduser().resolve()
        store = open_state_store(resolved_vault_path, create=False)
        try:
            store.record_processing_failure(
                item_id,
                updated_at=time.time_ns() if updated_at is None else updated_at,
                error=error,
            )
        finally:
            store.close()

    @property
    def vault_path(self) -> Path:
        """Return the resolved vault path."""
        return self._vault_path

    @staticmethod
    def _validate_importance(importance: int) -> None:
        if not isinstance(importance, int) or isinstance(importance, bool):
            raise InvalidImportanceError("importance must be an integer")
        if importance < DEFAULT_IMPORTANCE:
            raise InvalidImportanceError("importance must be at least 1")

    def record(self, text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int:
        """Store a moment and submit Weft-backed background processing.

        Spec:
            - [MWS-1]
            - [MWS-2]
            - [MWS-4]
        """

        stripped = text.strip()
        if not stripped:
            raise InvalidMemoryTextError("memory text must not be empty")
        self._validate_importance(importance)
        created_at = time.time_ns()
        item_id = self._store.allocate_memory_id(created_at)
        item = MemoryItem(
            id=item_id,
            tier=TIER_MOMENT,
            text=stripped,
            created_at=created_at,
            relevance=float(importance),
        )
        self._store.put_item(item)
        if self._submit_background:
            self._submit_background_task(item.id)
        return item.id

    def process_once(self, *, max_items: int = 1) -> ProcessResult:
        """Process up to ``max_items`` locally processable items."""
        processed_ids: list[int] = []
        failed_item_ids: list[int] = []
        created_episode_ids: list[int] = []
        created_arc_ids: list[int] = []

        for _ in range(max_items):
            item = self._store.get_next_repairable_item()
            if item is None:
                break
            try:
                result = self.repair_item(item.id)
                processed_ids.extend(result.processed_ids)
                created_episode_ids.extend(result.created_episode_ids)
                created_arc_ids.extend(result.created_arc_ids)
            except Exception as exc:
                del exc
                failed_item_ids.append(item.id)
                continue

        return ProcessResult(
            processed_ids=tuple(processed_ids),
            created_episode_ids=tuple(created_episode_ids),
            failed_item_ids=tuple(failed_item_ids),
            created_arc_ids=tuple(created_arc_ids),
        )

    def process(self, *, max_passes: int = 100) -> ProcessResult:
        """Process locally retryable items until no more progress occurs."""
        processed_ids: list[int] = []
        created_episode_ids: list[int] = []
        failed_item_ids: list[int] = []
        created_arc_ids: list[int] = []

        for _ in range(max_passes):
            result = self.process_once(max_items=1)
            processed_ids.extend(result.processed_ids)
            created_episode_ids.extend(result.created_episode_ids)
            failed_item_ids.extend(result.failed_item_ids)
            created_arc_ids.extend(result.created_arc_ids)
            if result.is_idle:
                break
        return ProcessResult(
            processed_ids=tuple(processed_ids),
            created_episode_ids=tuple(created_episode_ids),
            failed_item_ids=tuple(failed_item_ids),
            created_arc_ids=tuple(created_arc_ids),
        )

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
        tiers: tuple[int, ...] | None = None,
        count_access: bool = True,
    ) -> list[SearchResult]:
        """Run hybrid retrieval and return ranked results."""
        stripped = query.strip()
        if not stripped:
            raise InvalidMemoryTextError("search query must not be empty")

        text_rows = self._index.search_text(stripped, limit=limit, tiers=tiers)
        vector_rows = self._index.search_vector(
            stripped,
            limit=limit,
            tiers=tiers,
        )
        candidates = self._fuse_candidates(text_rows=text_rows, vector_rows=vector_rows)
        ordered_ids = [candidate.id for candidate in candidates[:limit]]
        items = {item.id: item for item in self._store.get_items(ordered_ids)}

        results: list[SearchResult] = []
        for candidate in candidates:
            item = items.get(candidate.id)
            if item is None:
                continue
            score = boosted_search_score(
                candidate.fused_score,
                access=item.access,
                relevance=item.relevance,
            )
            results.append(
                SearchResult(
                    id=item.id,
                    tier=item.tier,
                    text=item.text,
                    source=candidate.source,
                    fused_score=candidate.fused_score,
                    access=item.access,
                    relevance=item.relevance,
                    score=score,
                )
            )

        results.sort(
            key=lambda result: (result.score, result.fused_score), reverse=True
        )
        final_results = results[:limit]
        if count_access:
            self._store.increment_access([result.id for result in final_results])
        return final_results

    def recall(
        self,
        item_id: int,
        *,
        scope: RecallScope = "item",
        count_access: bool = True,
    ) -> MemoryItem:
        """Recall an exact item or containing summary by anchor ID.

        Use exact recall when you already have a concrete memory ID. Use scoped
        recall when you want the summary tier that contains an anchor in memory
        time. Named scopes (`"episode"`, `"arc"`) and integer tiers (`1`, `2`,
        `3`, ...) both work.

        Examples:
            `memory.recall(mid)`
            `memory.recall(mid, scope="episode")`
            `memory.recall(mid, scope=2)`

        Spec:
            - [FCI-10]
            - [FCI-16]
        """
        normalized_scope = normalize_recall_scope(scope)
        target_tier = recall_scope_tier(normalized_scope)
        if normalized_scope == RECALL_SCOPE_ITEM:
            item = self._recall_item(item_id)
        else:
            assert target_tier is not None  # pragma: no cover - scope normalization
            item = self._recall_summary(item_id, target_tier=target_tier)
        if count_access:
            return self._count_access_and_reload(item)
        return item

    def set_importance(self, item_id: int, *, importance: int) -> MemoryItem:
        """Set an item's importance multiplier."""

        self._validate_importance(importance)
        return self._store.set_item_importance(
            item_id,
            relevance=float(importance),
        )

    def build_context(
        self,
        *,
        term: str | None = None,
        total_tokens: int = DEFAULT_CONTEXT_TOKENS,
        immediate: float | None = None,
        short_term: float | None = None,
        medium_term: float | None = None,
        long_term: float | None = None,
    ) -> ContextView:
        """Build a multi-horizon context view.

        Spec:
            - [CAA-5]
            - [CAA-8]
            - [CAA-9]
        """
        budgets = resolve_budgets(
            total_tokens=total_tokens,
            immediate=immediate,
            short_term=short_term,
            medium_term=medium_term,
            long_term=long_term,
        )
        recent_moments = self._store.list_recent_items(tier=TIER_MOMENT, limit=50)
        immediate_items = select_items_for_budget(
            recent_moments,
            token_budget=budgets["immediate"],
        )

        recent_episodes = self._store.list_recent_items(tier=TIER_EPISODE, limit=25)
        short_items = select_items_for_budget(
            recent_episodes,
            token_budget=budgets["short_term"],
            exclude_ids=[item.id for item in immediate_items],
        )

        excluded_ids = [item.id for item in (*immediate_items, *short_items)]
        recent_arcs = self._store.list_recent_items(tier=TIER_ARC, limit=15)
        medium_candidates: list[MemoryItem] = list(recent_arcs)
        long_candidates: list[MemoryItem] = []
        if term is not None and term.strip():
            search_items = self.search(
                term,
                limit=30,
                tiers=(TIER_MOMENT, TIER_EPISODE, TIER_ARC),
                count_access=False,
            )
            medium_search_ids = [
                result.id
                for result in sorted(
                    [result for result in search_items if result.tier == TIER_ARC],
                    key=lambda result: -result.score,
                )
            ]
            medium_candidates = self._merge_unique_items(
                medium_candidates,
                self._store.get_items(medium_search_ids),
            )
            tier_order = {TIER_MOMENT: 0, TIER_EPISODE: 1}
            ordered_search_ids = [
                result.id
                for result in sorted(
                    [result for result in search_items if result.tier != TIER_ARC],
                    key=lambda result: (tier_order.get(result.tier, 99), -result.score),
                )
            ]
            long_candidates = self._merge_unique_items(
                long_candidates,
                self._store.get_items(ordered_search_ids),
            )
        medium_items = select_items_for_budget(
            medium_candidates,
            token_budget=budgets["medium_term"],
            exclude_ids=excluded_ids,
        )
        excluded_ids.extend(item.id for item in medium_items)
        high_value_items = self._store.list_high_value_items(
            limit=20,
            exclude_ids=excluded_ids,
        )
        long_candidates = self._merge_unique_items(long_candidates, high_value_items)

        long_items = select_items_for_budget(
            long_candidates,
            token_budget=budgets["long_term"]
            + (budgets["medium_term"] - used_tokens(medium_items)),
            exclude_ids=excluded_ids,
        )
        return build_context_view(
            total_tokens=total_tokens,
            immediate_budget=budgets["immediate"],
            short_budget=budgets["short_term"],
            medium_budget=budgets["medium_term"],
            long_budget=budgets["long_term"],
            immediate_items=immediate_items,
            short_items=short_items,
            medium_items=medium_items,
            long_items=long_items,
        )

    def items_needing_processing_count(self) -> int:
        """Return the number of tier-0 items still needing downstream work."""
        return self._store.count_items_needing_processing()

    def status(self, *, failed_item_limit: int = 5) -> VaultStatus:
        """Return vault lifecycle and recovery status.

        Spec:
            - [LAS-8]
            - [LAS-9]
        """
        item_counts = {
            tier_name(tier): count
            for tier, count in self._store.count_items_by_tier().items()
        }
        indexed_items = self._store.count_indexed_items()
        index_rows = self._index.count_rows()
        total_items = sum(item_counts.values())
        items_needing_processing = self._store.count_items_needing_processing()
        unindexed_items = self._store.count_unindexed_items()
        failed_processing_items = self._store.count_failed_processing_items()
        needs_rebuild = indexed_items != total_items or index_rows != total_items
        return VaultStatus(
            vault_path=str(self._vault_path),
            sqlite_path=str(self._store.db_path),
            index_path=str(self._index.path),
            broker_path=str(self._vault_path / "broker.db"),
            schema_version=self._store.get_schema_version(),
            item_counts=item_counts,
            indexed_items=indexed_items,
            index_rows=index_rows,
            items_needing_processing=items_needing_processing,
            unindexed_items=unindexed_items,
            failed_processing_items=failed_processing_items,
            failed_items=tuple(self._store.list_failed_items(limit=failed_item_limit)),
            needs_rebuild=needs_rebuild,
        )

    def rebuild_index(self) -> RebuildResult:
        """Rebuild the retrieval index from authoritative SQLite state.

        Spec:
            - [LAS-12]
            - [LAS-13]
            - [LAS-14]
        """
        items = self._store.all_items()
        self._index.rebuild(items)
        indexed_at = time.time_ns()
        self._store.update_indexed_at_many(
            [item.id for item in items],
            indexed_at=indexed_at,
        )
        return RebuildResult(
            rebuilt_items=len(items),
            index_rows=self._index.count_rows(),
            indexed_at=indexed_at,
        )

    def process_item_operation(self, item_id: int) -> ProcessResult:
        """Run the shared item-processing domain operation.

        This is the core operation reused by embedded-Weft tasks and local
        repair tooling. It performs the domain work but does not mutate the
        caller-facing processing status by itself.

        Spec:
            - [MWS-27]
            - [EWM-16]
        """

        with self._processing_lock():
            processed_ids = self._index_item_if_needed(item_id)
            created_episode_ids, created_arc_ids = (
                self._coalesce_available_summaries_operation()
            )
            return ProcessResult(
                processed_ids=processed_ids,
                created_episode_ids=created_episode_ids,
                failed_item_ids=(),
                created_arc_ids=created_arc_ids,
            )

    def repair_item(self, item_id: int) -> ProcessResult:
        """Run the shared item-processing operation and record local repair state.

        Spec:
            - [MWS-27]
            - [LAS-19]
            - [EWM-16]
        """

        updated_at = time.time_ns()
        try:
            result = self.process_item_operation(item_id)
        except Exception as exc:
            self._store.record_processing_failure(
                item_id,
                updated_at=updated_at,
                error=str(exc),
            )
            raise
        self._store.record_processing_success(item_id, updated_at=updated_at)
        return result

    def close(self) -> None:
        """Close open resources."""
        self._index.close()
        self._store.close()

    def _recall_item(self, item_id: int) -> MemoryItem:
        """Recall an exact memory item by ID."""

        return self._get_item_or_raise(item_id)

    def _recall_summary(self, anchor_id: int, *, target_tier: int) -> MemoryItem:
        """Recall the summary at `target_tier` whose support contains `anchor_id`."""

        exact_item = self._store.get_item(anchor_id)
        if exact_item is not None:
            if exact_item.tier == target_tier:
                return exact_item
            if exact_item.tier > target_tier:
                raise MemoryItemNotFoundError(anchor_id, tier=target_tier)
            return self._climb_summary_parents(
                exact_item,
                anchor_id=anchor_id,
                target_tier=target_tier,
            )

        return self._recall_missing_anchor_summary(
            anchor_id,
            target_tier=target_tier,
        )

    def _recall_missing_anchor_summary(
        self,
        anchor_id: int,
        *,
        target_tier: int,
    ) -> MemoryItem:
        """Recall a summary for an anchor that is not an exact stored item."""

        for candidate_tier in range(TIER_EPISODE, target_tier + 1):
            containing = self._store.find_summary_containing(
                anchor_id,
                parent_tier=candidate_tier,
            )
            if containing is None:
                continue
            if containing.tier == target_tier:
                return containing
            return self._climb_summary_parents(
                containing,
                anchor_id=anchor_id,
                target_tier=target_tier,
            )
        raise MemoryItemNotFoundError(anchor_id, tier=target_tier)

    def _climb_summary_parents(
        self,
        item: MemoryItem,
        *,
        anchor_id: int,
        target_tier: int,
    ) -> MemoryItem:
        """Climb adjacent summary tiers until `target_tier` is reached."""

        current_item = item
        while current_item.tier < target_tier:
            parent_tier = current_item.tier + 1
            parent = self._store.get_parent(
                current_item.id,
                parent_tier=parent_tier,
            )
            if parent is None:
                parent = self._store.find_summary_containing(
                    current_item.id,
                    parent_tier=parent_tier,
                )
            if parent is None:
                raise MemoryItemNotFoundError(anchor_id, tier=target_tier)
            current_item = parent
        return current_item

    def _get_item_or_raise(
        self,
        item_id: int,
        *,
        tier: int | None = None,
    ) -> MemoryItem:
        """Fetch one exact item or raise the public not-found error."""

        item = self._store.get_item(item_id, tier=tier)
        if item is None:
            raise MemoryItemNotFoundError(item_id, tier=tier)
        return item

    def _count_access_and_reload(self, item: MemoryItem) -> MemoryItem:
        """Increment access for one returned item and return fresh state."""

        self._store.increment_access([item.id])
        reloaded = self._store.get_item(item.id, tier=item.tier)
        if reloaded is None:  # pragma: no cover - defensive
            raise MemoryItemNotFoundError(item.id, tier=item.tier)
        return reloaded

    def _submit_background_task(self, item_id: int) -> None:
        """Submit one Weft-backed processing task for the item."""
        try:
            task_tid = weft_runtime.submit_process_item_task(
                self._vault_path,
                item_id=item_id,
            )
        except Exception as exc:
            self._store.record_processing_failure(
                item_id,
                updated_at=time.time_ns(),
                error=f"background submit failed: {exc}",
            )
            return
        if task_tid is None:  # pragma: no cover - test shim path
            return
        self._store.record_task_submission(
            item_id,
            task_tid=task_tid,
            updated_at=time.time_ns(),
        )

    @contextmanager
    def _processing_lock(self) -> Any:
        """Serialize vault mutation paths across local and Weft workers."""
        lock_path = self._vault_path / ".processing.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _index_item_if_needed(self, item_id: int) -> tuple[int, ...]:
        """Index one item if it is not already in the retrieval projection."""

        item = self._get_item_or_raise(item_id)
        if item.indexed_at is not None:
            return ()
        self._index.upsert_item(item)
        self._store.update_indexed_at(item.id, indexed_at=time.time_ns())
        return (item.id,)

    def _coalesce_available_summaries_operation(
        self,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Run the shared higher-tier coalescing operation set."""

        created_by_tier = self._coalesce_declared_tier_pairs_operation()
        created_episode_ids = created_by_tier.get(TIER_EPISODE, ())
        created_arc_ids = created_by_tier.get(TIER_ARC, ())
        return created_episode_ids, created_arc_ids

    def _declared_summary_tier_pairs(self) -> tuple[tuple[int, int], ...]:
        """Return the declared summary-tier pairs Engram currently maintains."""

        return tuple(
            (source_tier, source_tier + 1)
            for source_tier in range(TIER_MOMENT, MAX_BUILTIN_TIER)
        )

    def _coalesce_declared_tier_pairs_operation(self) -> dict[int, tuple[int, ...]]:
        """Run coalescing for each declared summary-tier pair."""

        created_by_tier: dict[int, tuple[int, ...]] = {}
        for source_tier, target_tier in self._declared_summary_tier_pairs():
            created_ids = self._coalesce_available_tier_operation(
                source_tier=source_tier,
                target_tier=target_tier,
            )
            if created_ids:
                created_by_tier[target_tier] = created_ids
        return created_by_tier

    def _coalesce_available_tier_operation(
        self,
        *,
        source_tier: int,
        target_tier: int,
    ) -> tuple[int, ...]:
        """Create newly closable summaries for one declared tier pair."""

        created_ids: list[int] = []
        while True:
            source_items = self._store.list_uncoalesced_items(
                child_tier=source_tier,
                parent_tier=target_tier,
            )
            window = choose_summary_window(
                source_items,
                embed_text=self._embedder.embed_document,
            )
            if not window:
                break
            summary_text, summary_terms = summarize_items_with_llm(
                window,
                tier=target_tier,
                corpus_items=self._store.all_items(),
            )
            summary_item = self._store.create_summary_item(
                tier=target_tier,
                text=summary_text,
                summary_terms=summary_terms,
                child_ids=[item.id for item in window],
            )
            self._index.upsert_item(summary_item)
            self._store.update_indexed_at(
                summary_item.id,
                indexed_at=time.time_ns(),
            )
            created_ids.append(summary_item.id)
        return tuple(created_ids)

    def _fuse_candidates(
        self,
        *,
        text_rows: list[dict[str, Any]],
        vector_rows: list[dict[str, Any]],
    ) -> list[_FusionCandidate]:
        """Fuse ranked text and vector retrieval rows."""
        merged: dict[int, _FusionCandidate] = {}

        for rank, row in enumerate(text_rows, start=1):
            item_id = int(row["id"])
            merged[item_id] = _FusionCandidate(
                id=item_id,
                tier=int(row["tier"]),
                text=str(row["text"]),
                source="fts",
                fused_score=reciprocal_rank_fusion(rank),
            )

        for rank, row in enumerate(vector_rows, start=1):
            item_id = int(row["id"])
            score = reciprocal_rank_fusion(rank)
            if item_id in merged:
                candidate = merged[item_id]
                candidate.source = "hybrid"
                candidate.fused_score += score
            else:
                merged[item_id] = _FusionCandidate(
                    id=item_id,
                    tier=int(row["tier"]),
                    text=str(row["text"]),
                    source="vector",
                    fused_score=score,
                )

        return sorted(
            merged.values(),
            key=lambda candidate: candidate.fused_score,
            reverse=True,
        )

    @staticmethod
    def _resolve_vault_path(path: str | Path | None) -> Path:
        if path is None:
            return Path.cwd() / DEFAULT_VAULT_DIR_NAME
        return Path(path).expanduser().resolve()

    def _merge_unique_items(
        self,
        current: list[MemoryItem],
        extras: list[MemoryItem],
    ) -> list[MemoryItem]:
        seen = {item.id for item in current}
        for item in extras:
            if item.id in seen:
                continue
            current.append(item)
            seen.add(item.id)
        return current


__all__ = ["DeterministicEmbedder", "Engram"]
