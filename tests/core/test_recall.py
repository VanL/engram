from __future__ import annotations

from collections.abc import Iterable

import pytest

from engram._constants import TIER_ARC, TIER_EPISODE, TIER_MOMENT
from engram._exceptions import MemoryItemNotFoundError
from engram._models import MemoryItem
from engram.core.memory import Engram
from engram.store.sqlite import SQLiteStateStore
from tests.fixtures.state_inspection import children


def _put_moments(store: SQLiteStateStore, item_ids: Iterable[int]) -> None:
    for item_id in item_ids:
        store.put_item(
            MemoryItem(
                id=item_id,
                tier=TIER_MOMENT,
                text=f"Decision: domain recall fixture {item_id}.",
                created_at=item_id,
            )
        )


def _create_recall_hierarchy(memory: Engram) -> dict[str, int]:
    store = SQLiteStateStore(memory.vault_path, create=False)
    try:
        first_child_ids = (900, 999)
        second_child_ids = (1500, 2999)
        _put_moments(store, (*first_child_ids, *second_child_ids))
        first_episode = store.create_episode(
            text="Episode: first domain recall range.",
            summary_terms=("first", "domain", "recall"),
            child_ids=first_child_ids,
        )
        second_episode = store.create_episode(
            text="Episode: second domain recall range.",
            summary_terms=("second", "domain", "recall"),
            child_ids=second_child_ids,
        )
        arc = store.create_arc(
            text="Arc: domain recall hierarchy.",
            summary_terms=("arc", "domain", "recall"),
            child_ids=(first_episode.id, second_episode.id),
        )
        epoch = store.create_summary_item(
            tier=3,
            text="Epoch: domain recall hierarchy.",
            summary_terms=("epoch", "domain", "recall"),
            child_ids=(arc.id,),
        )
    finally:
        store.close()

    return {
        "first_child_id": first_child_ids[0],
        "second_child_id": second_child_ids[0],
        "second_episode_id": second_episode.id,
        "arc_id": arc.id,
        "epoch_id": epoch.id,
    }


def test_recall_exact_item_increments_access_by_default(memory: Engram) -> None:
    item_id = memory.record("Decision: exact recall should count access.")

    initial = memory.recall(item_id, count_access=False)
    recalled = memory.recall(item_id)
    final = memory.recall(item_id, count_access=False)

    assert initial.id == item_id
    assert initial.tier == TIER_MOMENT
    assert recalled.access == initial.access + 1.0
    assert final.access == initial.access + 1.0


def test_recall_episode_from_child_and_in_between_anchor(memory: Engram) -> None:
    ids = _create_recall_hierarchy(memory)

    from_child = memory.recall(
        ids["second_child_id"],
        scope="episode",
        count_access=False,
    )
    from_anchor = memory.recall(2000, scope="episode", count_access=False)
    exact_episode = memory.recall(
        ids["second_episode_id"],
        scope="episode",
        count_access=False,
    )

    assert from_child.tier == TIER_EPISODE
    assert from_child.id == ids["second_episode_id"]
    assert from_anchor.id == ids["second_episode_id"]
    assert exact_episode.id == ids["second_episode_id"]
    assert ids["second_child_id"] in [
        child.id for child in children(memory.vault_path, from_child.id)
    ]


def test_recall_arc_from_moment_episode_and_exact_arc(memory: Engram) -> None:
    ids = _create_recall_hierarchy(memory)

    from_moment = memory.recall(
        ids["second_child_id"],
        scope="arc",
        count_access=False,
    )
    from_episode = memory.recall(
        ids["second_episode_id"],
        scope="arc",
        count_access=False,
    )
    exact_arc = memory.recall(ids["arc_id"], scope="arc", count_access=False)

    assert from_moment.tier == TIER_ARC
    assert from_moment.id == ids["arc_id"]
    assert from_episode.id == ids["arc_id"]
    assert exact_arc.id == ids["arc_id"]


def test_recall_supports_integer_summary_tiers(memory: Engram) -> None:
    ids = _create_recall_hierarchy(memory)

    episode = memory.recall(ids["second_child_id"], scope=1, count_access=False)
    arc = memory.recall(ids["second_child_id"], scope=2, count_access=False)
    epoch = memory.recall(ids["second_child_id"], scope=3, count_access=False)
    exact_epoch = memory.recall(ids["epoch_id"], scope=3, count_access=False)

    assert episode.id == ids["second_episode_id"]
    assert episode.tier == TIER_EPISODE
    assert arc.id == ids["arc_id"]
    assert arc.tier == TIER_ARC
    assert epoch.id == ids["epoch_id"]
    assert epoch.tier == 3
    assert exact_epoch.id == ids["epoch_id"]


def test_scoped_recall_counts_only_returned_item(memory: Engram) -> None:
    ids = _create_recall_hierarchy(memory)
    anchor_id = ids["second_child_id"]
    episode_id = ids["second_episode_id"]

    before_anchor = memory.recall(anchor_id, count_access=False).access
    before_episode = memory.recall(episode_id, count_access=False).access

    returned = memory.recall(anchor_id, scope="episode")

    after_anchor = memory.recall(anchor_id, count_access=False).access
    after_episode = memory.recall(episode_id, count_access=False).access

    assert returned.id == episode_id
    assert after_anchor == before_anchor
    assert after_episode == before_episode + 1.0


def test_scoped_recall_raises_when_no_containing_summary(memory: Engram) -> None:
    _create_recall_hierarchy(memory)

    with pytest.raises(MemoryItemNotFoundError):
        memory.recall(1200, scope="episode")

    with pytest.raises(MemoryItemNotFoundError):
        memory.recall(5000, scope="arc")


def test_recall_rejects_invalid_scope(memory: Engram) -> None:
    item_id = memory.record("Decision: invalid recall scope should fail clearly.")

    with pytest.raises(ValueError, match="scope"):
        memory.recall(item_id, scope="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least 1"):
        memory.recall(item_id, scope=0)
    with pytest.raises(ValueError, match="scope"):
        memory.recall(item_id, scope=True)  # type: ignore[arg-type]


def test_removed_domain_lookup_helpers_are_absent() -> None:
    assert not hasattr(Engram, "lookup")
    assert not hasattr(Engram, "moment")
    assert not hasattr(Engram, "episode")
    assert not hasattr(Engram, "arc")
