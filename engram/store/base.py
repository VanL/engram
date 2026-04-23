"""State-store protocol for Engram.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-12], [MM-19]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-2], [MWS-8]
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from engram._models import FailedItemRecord, MemoryItem


class StateStore(Protocol):
    """Interface for Engram transactional state."""

    @property
    def db_path(self) -> Path:
        """Return the current state-store database path."""

    def close(self) -> None:
        """Close state-store resources."""

    def get_metadata(self) -> dict[str, str]:
        """Return vault metadata from the authoritative store."""

    def get_schema_version(self) -> int:
        """Return the explicit schema version for this vault."""

    def put_item(self, item: MemoryItem) -> MemoryItem:
        """Persist a memory item."""

    def allocate_memory_id(self, physical_ns: int) -> int:
        """Allocate a unique memory ID for the given physical timestamp."""

    def get_item(self, item_id: int, tier: int | None = None) -> MemoryItem | None:
        """Fetch a memory item."""

    def get_items(self, item_ids: Sequence[int]) -> list[MemoryItem]:
        """Fetch multiple memory items."""

    def list_recent_items(self, *, tier: int, limit: int) -> list[MemoryItem]:
        """List recent items in descending time order."""

    def list_high_value_items(
        self,
        *,
        limit: int,
        exclude_ids: Sequence[int] = (),
    ) -> list[MemoryItem]:
        """List high-value items in descending score order."""

    def list_uncoalesced_moments(self) -> list[MemoryItem]:
        """List moments that are not yet children of an episode."""

    def list_uncoalesced_episodes(self) -> list[MemoryItem]:
        """List episodes that are not yet children of an arc."""

    def list_uncoalesced_items(
        self,
        *,
        child_tier: int,
        parent_tier: int,
    ) -> list[MemoryItem]:
        """List items not yet attached to a parent at the next tier."""

    def create_episode(
        self,
        *,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create an episode and attach its ordered children."""

    def create_arc(
        self,
        *,
        text: str,
        summary_terms: Sequence[str],
        child_ids: Sequence[int],
        created_at: int | None = None,
    ) -> MemoryItem:
        """Create an arc and attach its ordered child episodes."""

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

    def get_children(self, parent_id: int) -> list[MemoryItem]:
        """Fetch ordered children for a parent item."""

    def get_parent(self, child_id: int, *, parent_tier: int) -> MemoryItem | None:
        """Fetch the immediate parent at `parent_tier` for a child item."""

    def find_summary_containing(
        self,
        anchor_id: int,
        *,
        parent_tier: int,
    ) -> MemoryItem | None:
        """Fetch the summary whose child-ID support range contains `anchor_id`."""

    def get_next_repairable_item(self) -> MemoryItem | None:
        """Fetch the next item that still needs local repair work."""

    def record_processing_success(self, item_id: int, *, updated_at: int) -> None:
        """Record successful deferred processing for one item."""

    def record_processing_failure(
        self,
        item_id: int,
        *,
        updated_at: int,
        error: str,
    ) -> None:
        """Record deferred-processing failure for one item."""

    def record_task_submission(
        self,
        item_id: int,
        *,
        task_tid: str,
        updated_at: int,
    ) -> None:
        """Record last-known Weft correlation for one item."""

    def count_items_needing_processing(self) -> int:
        """Return the number of tier-0 items still needing downstream work."""

    def count_unindexed_items(self) -> int:
        """Return the number of tier-0 items not yet indexed."""

    def count_failed_processing_items(self) -> int:
        """Return the number of tier-0 items with recorded failure state."""

    def list_failed_items(self, *, limit: int) -> list[FailedItemRecord]:
        """Return recent failed items for inspection."""

    def count_items_by_tier(self) -> dict[int, int]:
        """Return item counts keyed by tier."""

    def count_indexed_items(self) -> int:
        """Return the number of items marked indexed in the state store."""

    def update_indexed_at(self, item_id: int, *, indexed_at: int) -> MemoryItem:
        """Record the latest index update time."""

    def update_indexed_at_many(
        self,
        item_ids: Sequence[int],
        *,
        indexed_at: int,
    ) -> None:
        """Record the latest index update time for multiple items."""

    def increment_access(self, item_ids: Sequence[int]) -> None:
        """Increment access for the given item IDs."""

    def set_item_importance(self, item_id: int, *, relevance: float) -> MemoryItem:
        """Update item importance stored as relevance."""

    def all_items(self) -> list[MemoryItem]:
        """List all memory items."""
