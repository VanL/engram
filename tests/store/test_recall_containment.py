from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from engram._constants import TIER_EPISODE, TIER_MOMENT
from engram._models import MemoryItem
from engram.store.sqlite import SQLiteStateStore


def _put_moments(store: SQLiteStateStore, item_ids: Iterable[int]) -> None:
    for item_id in item_ids:
        store.put_item(
            MemoryItem(
                id=item_id,
                tier=TIER_MOMENT,
                text=f"Decision: recall containment fixture {item_id}.",
                created_at=item_id,
            )
        )


def test_store_finds_summary_containing_in_between_anchor(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        first_child_ids = (900, 999)
        second_child_ids = (1500, 2999)
        _put_moments(store, (*first_child_ids, *second_child_ids))

        first_episode = store.create_episode(
            text="Episode: first recall containment range.",
            summary_terms=("first", "containment"),
            child_ids=first_child_ids,
        )
        second_episode = store.create_episode(
            text="Episode: second recall containment range.",
            summary_terms=("second", "containment"),
            child_ids=second_child_ids,
        )

        containing = store.find_summary_containing(
            2000,
            parent_tier=TIER_EPISODE,
        )
        outside = store.find_summary_containing(
            1200,
            parent_tier=TIER_EPISODE,
        )
        direct_parent = store.get_parent(1500, parent_tier=TIER_EPISODE)
    finally:
        store.close()

    assert first_episode.id == 1000
    assert second_episode.id == 3000
    assert containing is not None
    assert containing.id == second_episode.id
    assert outside is None
    assert direct_parent is not None
    assert direct_parent.id == second_episode.id


def test_store_containment_overlap_returns_lowest_parent_id(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    try:
        _put_moments(store, (100, 200, 300, 400))

        lower_parent = store.create_episode(
            text="Episode: lower overlapping support range.",
            summary_terms=("lower", "overlap"),
            child_ids=(100, 300),
        )
        higher_parent = store.create_episode(
            text="Episode: higher overlapping support range.",
            summary_terms=("higher", "overlap"),
            child_ids=(200, 400),
        )

        containing = store.find_summary_containing(
            250,
            parent_tier=TIER_EPISODE,
        )
    finally:
        store.close()

    assert lower_parent.id < higher_parent.id
    assert containing is not None
    assert containing.id == lower_parent.id
