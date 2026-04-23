from __future__ import annotations

import json
from pathlib import Path

import pytest

from engram._exceptions import InvalidImportanceError
from engram.commands import memory as commands
from engram.core.embeddings import DeterministicEmbedder
from engram.core.memory import Engram
from tests.conftest import ARC_HISTORY

ITEM_KEYS = {
    "id",
    "tier",
    "text",
    "created_at",
    "access",
    "relevance",
    "indexed_at",
    "summary_terms",
}
SEARCH_KEYS = {
    "id",
    "tier",
    "text",
    "source",
    "fused_score",
    "access",
    "relevance",
    "score",
}
STATUS_KEYS = {
    "vault_path",
    "sqlite_path",
    "index_path",
    "broker_path",
    "schema_version",
    "item_counts",
    "indexed_items",
    "index_rows",
    "items_needing_processing",
    "unindexed_items",
    "failed_processing_items",
    "failed_items",
    "needs_rebuild",
}
REBUILD_KEYS = {"rebuilt_items", "index_rows", "indexed_at"}
PROCESS_KEYS = {
    "processed_ids",
    "created_episode_ids",
    "created_arc_ids",
    "failed_item_ids",
    "processed_count",
    "is_idle",
}


def test_commands_return_json_serializable_values(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    memory = commands.open_vault(
        vault_path,
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: use SQLite for local state and LanceDB for retrieval.",
        )
        process_result = commands.process(memory)

        assert item_id in process_result["processed_ids"]

        rendered_context = commands.context(
            memory,
            term="SQLite retrieval",
            total_tokens=64,
        )
        assert (
            rendered_context
            == memory.build_context(
                term="SQLite retrieval",
                total_tokens=64,
            ).render()
        )

        results = commands.search(
            memory,
            "SQLite retrieval",
            limit=5,
            count_access=False,
        )
        item = commands.recall(memory, item_id, count_access=False)
        status = commands.status(memory)

        assert results
        assert results[0]["id"] == item_id
        assert set(results[0]) == SEARCH_KEYS
        assert item is not None
        assert item["id"] == item_id
        assert set(item) == ITEM_KEYS
        assert set(process_result) == PROCESS_KEYS
        assert set(status) == STATUS_KEYS
        json.dumps(process_result)
        json.dumps(results)
        json.dumps(item)
        json.dumps(status)
    finally:
        memory.close()


def test_command_shapes_are_exact_and_json_safe(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: command return shapes should not drift.",
        )
        process_once = commands.process_once(memory)
        commands.process(memory)

        search_result = commands.search(
            memory,
            "command return shapes",
            count_access=False,
        )[0]
        recall_result = commands.recall(memory, item_id, count_access=False)
        status = commands.status(memory)
        rebuild_result = commands.rebuild_index(memory)
        process_result = commands.process(memory)

        assert set(process_once) == PROCESS_KEYS
        assert set(search_result) == SEARCH_KEYS
        assert recall_result is not None
        assert set(recall_result) == ITEM_KEYS
        assert set(status) == STATUS_KEYS
        assert set(rebuild_result) == REBUILD_KEYS
        assert set(process_result) == PROCESS_KEYS
        json.dumps(
            {
                "process_once": process_once,
                "search": search_result,
                "recall": recall_result,
                "status": status,
                "rebuild": rebuild_result,
                "process": process_result,
            }
        )
    finally:
        memory.close()


def test_command_record_importance_sets_relevance(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: command record importance should set relevance.",
            importance=4,
        )

        item = commands.recall(memory, item_id, count_access=False)

        assert item is not None
        assert set(item) == ITEM_KEYS
        assert item["relevance"] == 4.0
    finally:
        memory.close()


def test_command_record_rejects_invalid_importance(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        with pytest.raises(InvalidImportanceError):
            commands.record(
                memory,
                "Decision: invalid command importance should not write.",
                importance=0,
            )
    finally:
        memory.close()


def test_command_set_importance_updates_relevance(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: command set importance should update relevance.",
        )

        item = commands.set_importance(memory, item_id, importance=6)

        assert set(item) == ITEM_KEYS
        assert item["relevance"] == 6.0
    finally:
        memory.close()


def test_command_set_importance_rejects_invalid_importance(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: invalid command importance should not update relevance.",
        )

        with pytest.raises(InvalidImportanceError):
            commands.set_importance(memory, item_id, importance=0)

        stored = commands.recall(memory, item_id, count_access=False)
        assert stored is not None
        assert stored["relevance"] == 1.0
    finally:
        memory.close()


def test_command_layer_does_not_export_removed_public_names() -> None:
    assert not hasattr(commands, "pin")
    assert not hasattr(commands, "work_once")
    assert not hasattr(commands, "drain")
    assert not hasattr(commands, "lookup")


def test_command_recall_supports_scoped_summaries(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [
            commands.record(memory, text)
            for text in (
                "Decision: command recall should find containing episodes.",
                "Reason: scoped recall uses support edges.",
                "Rule: access counting applies only to returned summaries.",
                "Poster note: unrelated topic boundary.",
            )
        ]
        commands.process(memory)

        episode = commands.recall(
            memory,
            item_ids[0],
            scope="episode",
            count_access=False,
        )

        assert episode is not None
        assert set(episode) == ITEM_KEYS
        assert episode["tier"] == 1
    finally:
        memory.close()


def test_command_recall_supports_arc_scope(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [commands.record(memory, text) for text in ARC_HISTORY]
        commands.process(memory)

        arc = commands.recall(
            memory,
            item_ids[0],
            scope="arc",
            count_access=False,
        )

        assert arc is not None
        assert set(arc) == ITEM_KEYS
        assert arc["tier"] == 2
    finally:
        memory.close()


def test_command_recall_supports_integer_tier_scope(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [commands.record(memory, text) for text in ARC_HISTORY]
        commands.process(memory)

        episode = commands.recall(
            memory,
            item_ids[0],
            scope=1,
            count_access=False,
        )
        arc = commands.recall(
            memory,
            item_ids[0],
            scope=2,
            count_access=False,
        )

        assert episode is not None
        assert set(episode) == ITEM_KEYS
        assert episode["tier"] == 1
        assert arc is not None
        assert set(arc) == ITEM_KEYS
        assert arc["tier"] == 2
    finally:
        memory.close()


def test_command_recall_rejects_invalid_scope(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: invalid command recall scope should fail.",
        )

        with pytest.raises(ValueError, match="scope"):
            commands.recall(memory, item_id, scope="bad")
        with pytest.raises(ValueError, match="at least 1"):
            commands.recall(memory, item_id, scope=0)
    finally:
        memory.close()


def test_snapshot_vault_rejects_unsafe_targets(tmp_path: Path) -> None:
    source_path = tmp_path / ".engram"
    memory = commands.open_vault(
        source_path,
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        with pytest.raises(ValueError, match="must differ"):
            commands.snapshot_vault(memory, source_path)
        with pytest.raises(ValueError, match="must not be inside"):
            commands.snapshot_vault(memory, source_path / "snapshots" / "one")

        target = tmp_path / "target"
        target.mkdir()
        (target / "old.txt").write_text("old", encoding="utf-8")
        with pytest.raises(FileExistsError, match="not empty"):
            commands.snapshot_vault(memory, target)
    finally:
        memory.close()


def test_recall_and_search_can_skip_access_counting(tmp_path: Path) -> None:
    memory = commands.open_vault(
        tmp_path / ".engram",
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: tool-safe reads must not mutate access scores.",
        )
        commands.process(memory)

        assert memory.recall(item_id, count_access=False).access == 1.0

        assert commands.recall(memory, item_id, count_access=False) is not None
        assert memory.recall(item_id, count_access=False).access == 1.0

        commands.search(
            memory,
            "tool-safe reads",
            limit=5,
            count_access=False,
        )
        assert memory.recall(item_id, count_access=False).access == 1.0

        assert commands.recall(memory, item_id, count_access=True) is not None
        assert memory.recall(item_id, count_access=False).access == 2.0

        commands.search(
            memory,
            "tool-safe reads",
            limit=5,
            count_access=True,
        )
        assert memory.recall(item_id, count_access=False).access == 3.0
    finally:
        memory.close()


def test_snapshot_vault_copies_processed_vault(tmp_path: Path) -> None:
    source_path = tmp_path / ".engram"
    snapshot_path = tmp_path / "snapshot.engram"
    memory = commands.open_vault(
        source_path,
        create=True,
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = commands.record(
            memory,
            "Decision: snapshots must include SQLite and LanceDB state.",
        )

        commands.snapshot_vault(memory, snapshot_path)
    finally:
        memory.close()

    restored = Engram.open(snapshot_path, embedder=DeterministicEmbedder())
    try:
        assert (snapshot_path / "engram.db").exists()
        assert (snapshot_path / "lance").exists()
        results = restored.search("SQLite LanceDB state", count_access=False)
        assert results
        assert results[0].id == item_id
    finally:
        restored.close()
