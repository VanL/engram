from __future__ import annotations

import json
from pathlib import Path

import pytest

from engram import EngramClient, EngramClosedError
from engram.commands import memory as commands
from engram.core.embeddings import DeterministicEmbedder
from tests.conftest import ARC_HISTORY


def test_client_wraps_command_outputs(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = client.record(
            "Decision: EngramClient should be a thin command adapter.",
        )
        process_result = client.process()

        assert item_id in process_result["processed_ids"]
        assert client.context("command adapter", max_tokens=64) == commands.context(
            client.memory,
            term="command adapter",
            total_tokens=64,
        )
        assert client.search(
            "command adapter",
            limit=5,
            count_access=False,
        ) == commands.search(
            client.memory,
            "command adapter",
            limit=5,
            count_access=False,
        )
        assert client.recall(item_id, count_access=False) == commands.recall(
            client.memory,
            item_id,
            count_access=False,
        )
        assert client.set_importance(item_id, 5) == commands.set_importance(
            client.memory,
            item_id,
            importance=5,
        )
        assert client.status() == commands.status(client.memory)
        assert client.process() == commands.process(client.memory)
        json.dumps(client.status())
    finally:
        client.close()


def test_client_record_importance_wraps_command_layer(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = client.record(
            "Decision: client record importance should wrap commands.",
            importance=3,
        )

        client_item = client.recall(item_id, count_access=False)
        command_item = commands.recall(client.memory, item_id, count_access=False)

        assert client_item is not None
        assert client_item["relevance"] == 3.0
        assert client_item == command_item
    finally:
        client.close()


def test_client_set_importance_wraps_command_layer(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = client.record(
            "Decision: client set importance should wrap commands.",
        )

        client_item = client.set_importance(item_id, 7)
        command_item = commands.recall(client.memory, item_id, count_access=False)

        assert client_item["relevance"] == 7.0
        assert client_item == command_item
    finally:
        client.close()


def test_client_context_manager_closes_and_blocks_later_calls(tmp_path: Path) -> None:
    with EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    ) as client:
        item_id = client.record("Decision: client context managers close handles.")
        client.process()
        assert client.recall(item_id, count_access=False) is not None
        assert client.context("context managers", max_tokens=64)

    with pytest.raises(EngramClosedError):
        client.search("context managers")


def test_client_close_is_idempotent_and_guards_public_methods(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    item_id = client.record("Decision: closed clients raise one public error.")
    client.process()

    client.close()
    client.close()

    guarded_calls = (
        lambda: client.record("after close"),
        lambda: client.set_importance(item_id, 2),
        lambda: client.context("closed"),
        lambda: client.search("closed"),
        lambda: client.recall(item_id),
        lambda: client.status(),
        lambda: client.process(),
        lambda: client.snapshot(tmp_path / "snapshot"),
        lambda: client.llm_tools(),
        lambda: client.memory,
        lambda: client.vault_path,
    )
    for call in guarded_calls:
        with pytest.raises(EngramClosedError):
            call()


def test_client_does_not_expose_removed_lookup_name() -> None:
    assert not hasattr(EngramClient, "lookup")


def test_client_recall_supports_scoped_summaries(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [client.record(text) for text in ARC_HISTORY]
        client.process()

        episode = client.recall(
            item_ids[0],
            scope="episode",
            count_access=False,
        )
        arc = client.recall(item_ids[0], scope="arc", count_access=False)

        assert episode is not None
        assert episode["tier"] == 1
        assert arc is not None
        assert arc["tier"] == 2
    finally:
        client.close()


def test_client_recall_supports_integer_tier_scopes(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [client.record(text) for text in ARC_HISTORY]
        client.process()

        episode = client.recall(item_ids[0], scope=1, count_access=False)
        arc = client.recall(item_ids[0], scope=2, count_access=False)

        assert episode is not None
        assert episode["tier"] == 1
        assert arc is not None
        assert arc["tier"] == 2
    finally:
        client.close()


def test_client_recall_rejects_invalid_scope(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = client.record("Decision: invalid client recall scope should fail.")

        with pytest.raises(ValueError, match="scope"):
            client.recall(item_id, scope="bad")
        with pytest.raises(ValueError, match="at least 1"):
            client.recall(item_id, scope=0)
    finally:
        client.close()


def test_client_retrieval_counts_access_by_default(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_id = client.record(
            "Decision: explicit client retrieval should count access by default.",
        )
        client.process()

        assert client.memory.recall(item_id, count_access=False).access == 1.0

        assert client.recall(item_id) is not None
        assert client.memory.recall(item_id, count_access=False).access == 2.0

        client.search("client retrieval", limit=5)
        assert client.memory.recall(item_id, count_access=False).access == 3.0
    finally:
        client.close()


def test_llm_tools_are_json_safe_and_read_only(tmp_path: Path) -> None:
    client = EngramClient.init(
        tmp_path / ".engram",
        embedder=DeterministicEmbedder(),
    )
    try:
        item_ids = [client.record(text) for text in ARC_HISTORY]
        item_id = item_ids[0]
        client.process()
        before_access = client.memory.recall(item_id, count_access=False).access
        before_arc = client.recall(item_id, scope="arc", count_access=False)
        assert before_arc is not None

        tools = {tool.name: tool for tool in client.llm_tools()}
        assert "engram_recall" in tools
        assert "engram_lookup" not in tools
        recall_scope_schema = tools["engram_recall"].input_schema["properties"]["scope"]  # type: ignore[union-attr,index]
        assert {"type": "integer", "minimum": 1} in recall_scope_schema["anyOf"]

        context_result = tools["engram_context"].implementation(  # type: ignore[union-attr]
            query="LLM tools",
            max_tokens=64,
        )
        search_result = tools["engram_search"].implementation(  # type: ignore[union-attr]
            query="score mutation",
            limit=5,
        )
        recall_result = tools["engram_recall"].implementation(  # type: ignore[union-attr]
            item_id=str(item_id),
        )
        arc_result = tools["engram_recall"].implementation(  # type: ignore[union-attr]
            item_id=str(item_id),
            scope="arc",
        )
        integer_scope_result = tools["engram_recall"].implementation(  # type: ignore[union-attr]
            item_id=str(item_id),
            scope=2,
        )

        assert isinstance(context_result, str)
        assert search_result
        assert recall_result is not None
        assert arc_result is not None
        assert integer_scope_result is not None
        assert arc_result["id"] == before_arc["id"]
        assert integer_scope_result["id"] == before_arc["id"]
        json.dumps(context_result)
        json.dumps(search_result)
        json.dumps(recall_result)
        json.dumps(arc_result)
        json.dumps(integer_scope_result)
        assert client.memory.recall(item_id, count_access=False).access == before_access
        after_arc = client.recall(before_arc["id"], count_access=False)
        assert after_arc is not None
        assert after_arc["access"] == before_arc["access"]
    finally:
        client.close()
