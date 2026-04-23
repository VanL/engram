from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from engram._models import MemoryItem
from engram.core.embeddings import DeterministicLanceEmbeddings
from engram.index.lance import LanceIndex
from engram.store.sqlite import SQLiteStateStore


def recent_items(vault_path: Path, *, tier: int, limit: int) -> list[MemoryItem]:
    """Read recent state-store items for tests."""

    store = SQLiteStateStore(vault_path, create=False)
    try:
        return store.list_recent_items(tier=tier, limit=limit)
    finally:
        store.close()


def children(vault_path: Path, parent_id: int) -> list[MemoryItem]:
    """Read ordered state-store children for tests."""

    store = SQLiteStateStore(vault_path, create=False)
    try:
        return store.get_children(parent_id)
    finally:
        store.close()


def create_summary_item_for_test(
    vault_path: Path,
    *,
    tier: int,
    text: str,
    summary_terms: Sequence[str],
    child_ids: Sequence[int],
    created_at: int,
) -> MemoryItem:
    """Create a summary item through the real state store for setup."""

    store = SQLiteStateStore(vault_path, create=False)
    try:
        return store.create_summary_item(
            tier=tier,
            text=text,
            summary_terms=summary_terms,
            child_ids=child_ids,
            created_at=created_at,
        )
    finally:
        store.close()


def delete_index_item(vault_path: Path, item_id: int) -> None:
    """Delete one retrieval-index item to simulate index drift."""

    index = LanceIndex(
        vault_path,
        embedding_function=DeterministicLanceEmbeddings.create(
            dimensions=8,
            max_retries=0,
        ),
    )
    try:
        index.delete_item(item_id)
    finally:
        index.close()
