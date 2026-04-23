from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from lancedb.embeddings import get_registry
from lancedb.embeddings.base import TextEmbeddingFunction

from engram import (
    ContextView,
    FailedItemRecord,
    MemoryItem,
    ProcessResult,
    RebuildResult,
    VaultStatus,
)
from engram._constants import (
    MEMORY_ID_LOGICAL_COUNTER_MASK,
    TIER_ARC,
    TIER_EPISODE,
    tier_name,
)
from engram._exceptions import (
    InvalidImportanceError,
    InvalidMemoryTextError,
    MemoryItemNotFoundError,
    VaultNotFoundError,
)
from engram.core.embeddings import DeterministicEmbedder, LanceEmbeddingModel
from engram.core.memory import Engram
from tests.fixtures.state_inspection import (
    children,
    create_summary_item_for_test,
    delete_index_item,
    recent_items,
)


@get_registry().register("engram-test-failing")
class FailingLanceEmbeddings(TextEmbeddingFunction):
    dimensions: int = 8

    def ndims(self) -> int:
        return self.dimensions

    def generate_embeddings(self, texts, *args, **kwargs):
        del texts, args, kwargs
        raise RuntimeError("boom")


class FailingEmbedder(LanceEmbeddingModel):
    def __init__(self) -> None:
        super().__init__(
            FailingLanceEmbeddings.create(
                dimensions=8,
                max_retries=0,
            )
        )


def test_record_creates_pending_work_and_searchable_moment(memory):
    item_id = memory.record("Decision: use SQLite for local state in each vault.")

    assert memory.items_needing_processing_count() == 1

    result = memory.process()

    assert item_id in result.processed_ids
    search_results = memory.search("SQLite local state", limit=5)
    assert search_results
    assert search_results[0].id == item_id


def test_record_importance_sets_initial_relevance(memory):
    item_id = memory.record(
        "Decision: write-time importance should set initial relevance.",
        importance=5,
    )

    stored = memory.recall(item_id, count_access=False)

    assert stored.relevance == 5.0
    assert stored.access == 1.0
    assert stored.tier == 0
    assert memory.items_needing_processing_count() == 1

    result = memory.process()
    search_results = memory.search("write-time importance", limit=5)

    assert item_id in result.processed_ids
    assert search_results
    assert search_results[0].id == item_id


def test_record_rejects_invalid_importance_before_writing(memory):
    for invalid_importance in (0, -1, True, "3"):
        with pytest.raises(InvalidImportanceError):
            memory.record(
                "Decision: invalid importance should not store a moment.",
                importance=invalid_importance,
            )

    status = memory.status()
    assert memory.items_needing_processing_count() == 0
    assert status.item_counts.get("moment", 0) == 0


def test_record_uses_store_memory_id_clock_when_physical_clock_is_fixed(
    memory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    physical_ns = 1_754_685_000_000_000_123
    expected_base = physical_ns & ~MEMORY_ID_LOGICAL_COUNTER_MASK
    monkeypatch.setattr("engram.core.memory.time.time_ns", lambda: physical_ns)

    ids = [
        memory.record(f"Decision: fixed physical clock record {index}.")
        for index in range(4)
    ]

    assert ids == [
        expected_base,
        expected_base + 1,
        expected_base + 2,
        expected_base + 3,
    ]
    for item_id in ids:
        item = memory.recall(item_id, count_access=False)
        assert item.id == item_id
        assert item.created_at == physical_ns


def test_concurrent_record_uses_shared_store_memory_id_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_path = tmp_path / ".engram"
    setup = Engram.init(
        vault_path,
        embedder=DeterministicEmbedder(),
        submit_background=False,
    )
    setup.close()
    physical_ns = 1_754_685_000_000_000_123
    expected_base = physical_ns & ~MEMORY_ID_LOGICAL_COUNTER_MASK
    monkeypatch.setattr("engram.core.memory.time.time_ns", lambda: physical_ns)
    workers = 4
    per_worker = 5

    def _record_many(worker_index: int) -> list[int]:
        instance = Engram.open(
            vault_path,
            embedder=DeterministicEmbedder(),
            submit_background=False,
        )
        try:
            return [
                instance.record(
                    f"Decision: concurrent fixed-clock record {worker_index}-{index}."
                )
                for index in range(per_worker)
            ]
        finally:
            instance.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        batches = list(executor.map(_record_many, range(workers)))

    ids = [item_id for batch in batches for item_id in batch]
    expected = set(range(expected_base, expected_base + len(ids)))
    reader = Engram.open(
        vault_path,
        embedder=DeterministicEmbedder(),
        submit_background=False,
    )
    try:
        stored_ids = {reader.recall(item_id, count_access=False).id for item_id in ids}
    finally:
        reader.close()

    assert len(ids) == workers * per_worker
    assert len(set(ids)) == len(ids)
    assert set(ids) == expected
    assert stored_ids == set(ids)


def test_search_and_recall_increment_access(memory):
    item_id = memory.record("Decision: context assembly must not increment access.")
    memory.process()

    initial = memory.recall(item_id, count_access=False)
    assert initial.access == 1.0

    memory.search("context assembly", limit=5)
    after_search = memory.recall(item_id, count_access=False)
    assert after_search.access == 2.0

    memory.recall(item_id)
    after_recall = memory.recall(item_id, count_access=False)
    assert after_recall.access == 3.0


def test_recall_is_the_public_direct_read_surface(memory):
    item_id = memory.record("Decision: recall is the public direct read.")
    memory.process()

    item = memory.recall(item_id, count_access=False)
    assert item.id == item_id
    assert not hasattr(Engram, "get")
    assert not hasattr(Engram, "lookup")

    memory.recall(item_id)
    assert memory.recall(item_id, count_access=False).access == 2.0

    with pytest.raises(MemoryItemNotFoundError):
        memory.recall(item_id, scope="episode")


def test_set_importance_updates_relevance(memory):
    item_id = memory.record("Decision: keep LanceDB rebuildable from SQLite.")
    memory.process()

    updated = memory.set_importance(item_id, importance=5)

    assert updated.relevance == 5.0


def test_set_importance_rejects_invalid_importance_before_writing(memory):
    item_id = memory.record("Decision: importance updates must validate first.")
    original = memory.recall(item_id, count_access=False)

    for invalid_importance in (0, -1, True, "3"):
        with pytest.raises(InvalidImportanceError):
            memory.set_importance(item_id, importance=invalid_importance)

    stored = memory.recall(item_id, count_access=False)
    assert stored.relevance == original.relevance


def test_record_rejects_empty_text(memory):
    with pytest.raises(InvalidMemoryTextError):
        memory.record("   ")


def test_set_importance_raises_for_missing_item(memory):
    with pytest.raises(MemoryItemNotFoundError):
        memory.set_importance(999_999_999, importance=2)


def test_open_requires_existing_vault(tmp_path):
    with pytest.raises(VaultNotFoundError):
        Engram.open(tmp_path / ".engram")


def test_init_creates_embedded_weft_runtime_files(tmp_path):
    vault_path = tmp_path / ".engram"

    memory = Engram.init(vault_path)
    try:
        assert (vault_path / "broker.db").exists()
        assert (vault_path / "config.json").exists()
    finally:
        memory.close()


def test_public_api_exports_stable_types():
    assert ContextView.__name__ == "ContextView"
    assert FailedItemRecord.__name__ == "FailedItemRecord"
    assert MemoryItem.__name__ == "MemoryItem"
    assert RebuildResult.__name__ == "RebuildResult"
    assert VaultStatus.__name__ == "VaultStatus"
    assert ProcessResult.__name__ == "ProcessResult"
    assert not hasattr(Engram, "pin")
    assert not hasattr(Engram, "work_once")
    assert not hasattr(Engram, "work_until_idle")


def test_status_surfaces_failed_items(tmp_path):
    memory = Engram.init(tmp_path / ".engram", embedder=FailingEmbedder())
    try:
        item_id = memory.record("Decision: failures must stay visible in status.")
        result = memory.process_once()

        assert result.failed_item_ids

        status = memory.status()

        assert status.items_needing_processing == 1
        assert status.failed_processing_items == 1
        assert status.unindexed_items == 1
        assert status.failed_items[0].id == item_id
        assert "boom" in status.failed_items[0].error
        assert status.needs_rebuild is True
    finally:
        memory.close()


def test_repair_item_uses_shared_process_operation(memory, monkeypatch):
    item_id = memory.record("Decision: repair paths must reuse core operations.")
    calls: list[int] = []

    def _fake_process(self, subject_id):  # type: ignore[no-untyped-def]
        calls.append(subject_id)
        return ProcessResult(
            processed_ids=(subject_id,),
            created_episode_ids=(),
            failed_item_ids=(),
            created_arc_ids=(),
        )

    monkeypatch.setattr(Engram, "process_item_operation", _fake_process)

    result = memory.repair_item(item_id)
    stored = memory.recall(item_id, count_access=False)

    assert calls == [item_id]
    assert result.processed_ids == (item_id,)
    assert stored.indexed_at is None
    assert memory.items_needing_processing_count() == 1


def test_process_once_uses_repair_item(memory, monkeypatch):
    item_id = memory.record("Decision: process once should wrap repair item.")
    calls: list[int] = []

    def _fake_repair(self, subject_id):  # type: ignore[no-untyped-def]
        calls.append(subject_id)
        return ProcessResult(
            processed_ids=(subject_id,),
            created_episode_ids=(),
            failed_item_ids=(),
            created_arc_ids=(),
        )

    monkeypatch.setattr(Engram, "repair_item", _fake_repair)

    result = memory.process_once()

    assert calls == [item_id]
    assert result.processed_ids == (item_id,)


def test_rebuild_index_restores_search_projection(memory):
    item_id = memory.record("Decision: rebuild the retrieval index from SQLite.")
    memory.process()
    vault_path = memory.vault_path
    memory.close()

    delete_index_item(vault_path, item_id)

    reopened = Engram.open(vault_path, embedder=DeterministicEmbedder())
    try:
        status_before = reopened.status()
        assert status_before.needs_rebuild is True
        assert not reopened.search("rebuild retrieval index", limit=5)

        rebuild_result = reopened.rebuild_index()

        assert rebuild_result.rebuilt_items >= 1
        assert rebuild_result.index_rows >= 1

        results = reopened.search("rebuild retrieval index", limit=5)
        assert results
        assert results[0].id == item_id
        assert reopened.status().needs_rebuild is False
    finally:
        reopened.close()


def test_process_creates_arc_and_arc_recall(arc_memory):
    status = arc_memory.status()

    assert status.item_counts["arc"] == 1

    arc_items = recent_items(arc_memory.vault_path, tier=TIER_ARC, limit=5)
    assert len(arc_items) == 1

    arc = arc_memory.recall(arc_items[0].id, count_access=False)
    arc_children = children(arc_memory.vault_path, arc.id)

    assert arc.is_arc is True
    assert len(arc_children) == 3
    assert all(child.tier == TIER_EPISODE for child in arc_children)


def test_back_processed_episode_mid_and_created_at_follow_children(
    memory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 1_000_000_000}
    monkeypatch.setattr("engram.core.memory.time.time_ns", lambda: clock["now"])
    moment_ids = []
    for offset, text in enumerate(
        (
            "Engram memory vault schema metadata decision.",
            "Engram memory vault schema version rollout.",
            "Engram memory vault metadata recovery plan.",
            "Marketing poster typography direction.",
        )
    ):
        clock["now"] = 1_000_000_000 + (offset * 10_000)
        moment_ids.append(memory.record(text))

    processing_time = 1_754_685_000_000_000_000
    clock["now"] = processing_time

    result = memory.process()

    assert len(result.created_episode_ids) == 1
    episode = memory.recall(result.created_episode_ids[0], count_access=False)
    episode_children = children(memory.vault_path, episode.id)
    expected_child_ids = moment_ids[:3]

    assert [child.id for child in episode_children] == expected_child_ids
    assert episode.id == max(expected_child_ids) + 1
    assert episode.id < processing_time
    assert episode.created_at == max(child.created_at for child in episode_children)
    assert episode.indexed_at == processing_time


def test_back_processed_arc_mid_and_created_at_follow_episode_children(
    memory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 1_000_000_000}
    monkeypatch.setattr("engram.core.memory.time.time_ns", lambda: clock["now"])
    for offset, text in enumerate(
        (
            "Engram memory vault schema metadata decision.",
            "Engram memory vault schema version rollout.",
            "Engram memory vault metadata recovery plan.",
            "Engram memory index rebuild decision.",
            "Engram memory Lance search rebuild notes.",
            "Engram memory hybrid retrieval repair plan.",
            "Engram memory context budget decision.",
            "Engram memory context medium-term bucket notes.",
            "Engram memory high-importance long-term context rule.",
            "Marketing poster typography direction.",
            "Marketing poster color palette review.",
            "Marketing poster launch headline copy.",
            "Accounting receipt export reconciliation.",
        )
    ):
        clock["now"] = 1_000_000_000 + (offset * 10_000)
        memory.record(text)

    processing_time = 1_754_685_000_000_000_000
    clock["now"] = processing_time

    result = memory.process()

    assert len(result.created_arc_ids) == 1
    arc = memory.recall(result.created_arc_ids[0], count_access=False)
    arc_children = children(memory.vault_path, arc.id)

    assert len(arc_children) == 3
    assert all(child.tier == TIER_EPISODE for child in arc_children)
    assert arc.id == max(child.id for child in arc_children) + 1
    assert arc.id < processing_time
    assert arc.created_at == max(child.created_at for child in arc_children)
    assert arc.indexed_at == processing_time


def test_generic_tier_coalescing_supports_unwrapped_higher_tiers(memory):
    created_tier2_ids: list[int] = []
    created_at_base = 2_000_000_000
    for offset, text in enumerate(
        (
            "Arc: schema migration arc. Key terms: schema, migration, vault.",
            "Arc: retrieval rebuild arc. Key terms: retrieval, rebuild, index.",
            "Arc: context budget arc. Key terms: context, budget, token.",
            "Poster palette review and launch headline notes.",
        ),
        start=1,
    ):
        item = create_summary_item_for_test(
            memory.vault_path,
            tier=2,
            text=text,
            summary_terms=(tier_name(2), "engram"),
            child_ids=(),
            created_at=created_at_base + offset,
        )
        created_tier2_ids.append(item.id)

    # This private call is intentional: generic tier coalescing has no public
    # product surface, but its extensibility invariant needs direct proof.
    created_tier3_ids = memory._coalesce_available_tier_operation(  # noqa: SLF001
        source_tier=2,
        target_tier=3,
    )

    assert len(created_tier3_ids) == 1

    tier3_item = memory.recall(created_tier3_ids[0], count_access=False)
    tier3_children = children(memory.vault_path, tier3_item.id)

    assert tier3_item.tier == 3
    assert [child.id for child in tier3_children] == created_tier2_ids[:3]
