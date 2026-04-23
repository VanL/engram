from __future__ import annotations

import json
from pathlib import Path

import pytest

from engram._constants import EXIT_ERROR, EXIT_NOT_FOUND
from engram.cli import main
from tests.conftest import ARC_HISTORY
from tests.fixtures.state_inspection import delete_index_item, recent_items

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


def test_cli_init_record_process_and_search(tmp_path: Path, capsys):
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    assert (vault / "broker.db").exists()
    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "Decision: use SQLite for each local vault.",
            ]
        )
        == 0
    )
    assert main(["--vault", str(vault), "vault", "process"]) == 0
    assert main(["--vault", str(vault), "search", "SQLite", "--limit", "5"]) == 0

    output = capsys.readouterr().out
    assert "SQLite" in output


def test_cli_json_output_contracts(tmp_path: Path, capsys) -> None:
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init", "--json"]) == 0
    init_output = json.loads(capsys.readouterr().out)
    assert set(init_output) == {"vault_path"}
    assert init_output["vault_path"] == str(vault)

    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "Decision: CLI JSON should use command-layer shapes.",
                "--json",
            ]
        )
        == 0
    )
    record_output = json.loads(capsys.readouterr().out)
    assert set(record_output) == {"id"}
    item_id = record_output["id"]

    assert main(["--vault", str(vault), "vault", "process", "--json"]) == 0
    process_output = json.loads(capsys.readouterr().out)
    assert set(process_output) == PROCESS_KEYS
    assert item_id in process_output["processed_ids"]

    assert main(["--vault", str(vault), "search", "CLI JSON", "--json"]) == 0
    search_output = json.loads(capsys.readouterr().out)
    assert search_output
    assert set(search_output[0]) == SEARCH_KEYS

    assert main(["--vault", str(vault), "context", "--tokens", "64", "--json"]) == 0
    context_output = json.loads(capsys.readouterr().out)
    assert set(context_output) == {"context", "term", "total_tokens"}
    assert context_output["term"] is None
    assert context_output["total_tokens"] == 64
    assert "CLI JSON" in context_output["context"]

    assert main(["--vault", str(vault), "recall", str(item_id), "--json"]) == 0
    recall_output = json.loads(capsys.readouterr().out)
    assert set(recall_output) == ITEM_KEYS
    assert recall_output["relevance"] == 1.0

    assert (
        main(["--vault", str(vault), "set-importance", str(item_id), "2", "--json"])
        == 0
    )
    set_importance_output = json.loads(capsys.readouterr().out)
    assert set(set_importance_output) == ITEM_KEYS
    assert set_importance_output["relevance"] == 2.0

    assert main(["--vault", str(vault), "vault", "status", "--json"]) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert set(status_output) == STATUS_KEYS

    assert main(["--vault", str(vault), "vault", "rebuild-index", "--json"]) == 0
    rebuild_output = json.loads(capsys.readouterr().out)
    assert set(rebuild_output) == REBUILD_KEYS


def test_cli_rejects_removed_public_command_names(tmp_path: Path) -> None:
    vault = tmp_path / ".engram"

    for argv in (
        ["--vault", str(vault), "work", "once"],
        ["--vault", str(vault), "pin", "1", "2"],
        ["--vault", str(vault), "status"],
        ["--vault", str(vault), "process"],
        ["--vault", str(vault), "rebuild-index"],
        ["--vault", str(vault), "moment", "1"],
        ["--vault", str(vault), "episode", "1"],
        ["--vault", str(vault), "arc", "1"],
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2


def test_cli_record_importance_sets_relevance(tmp_path: Path, capsys) -> None:
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "--importance",
                "6",
                "Decision: CLI record importance should set relevance.",
                "--json",
            ]
        )
        == 0
    )
    record_output = json.loads(capsys.readouterr().out)
    assert set(record_output) == {"id"}
    item_id = record_output["id"]

    assert main(["--vault", str(vault), "recall", str(item_id), "--json"]) == 0
    recall_output = json.loads(capsys.readouterr().out)
    assert set(recall_output) == ITEM_KEYS
    assert recall_output["relevance"] == 6.0


def test_cli_record_importance_accepts_flag_after_text(
    tmp_path: Path,
    capsys,
) -> None:
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "Decision: CLI record importance should allow flag after text.",
                "--importance",
                "7",
                "--json",
            ]
        )
        == 0
    )
    record_output = json.loads(capsys.readouterr().out)
    assert set(record_output) == {"id"}
    item_id = record_output["id"]

    assert main(["--vault", str(vault), "recall", str(item_id), "--json"]) == 0
    recall_output = json.loads(capsys.readouterr().out)
    assert set(recall_output) == ITEM_KEYS
    assert recall_output["relevance"] == 7.0


def test_cli_record_rejects_zero_importance(tmp_path: Path, capsys) -> None:
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "--importance",
                "0",
                "Decision: invalid CLI importance should not store.",
            ]
        )
        == EXIT_ERROR
    )
    assert "importance must be at least 1" in capsys.readouterr().out

    assert main(["--vault", str(vault), "vault", "status", "--json"]) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert status_output["item_counts"].get("moment", 0) == 0


def test_cli_exposes_context_set_importance_and_recall(
    tmp_path: Path,
    capsys,
):
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    recorded_ids: list[int] = []
    for text in (
        "Decision: use SQLite for the local state store.",
        "Reason: keep LanceDB focused on retrieval.",
        "Rule: keep record non-blocking for callers.",
        "Poster review: adjust typography and colors.",
    ):
        assert main(["--vault", str(vault), "record", text]) == 0
        recorded_ids.append(int(capsys.readouterr().out.strip()))

    assert main(["--vault", str(vault), "vault", "process", "--max-passes", "10"]) == 0
    capsys.readouterr()

    assert (
        main(["--vault", str(vault), "set-importance", str(recorded_ids[0]), "5"]) == 0
    )
    set_importance_output = json.loads(capsys.readouterr().out)
    assert set_importance_output["relevance"] == 5.0

    assert main(["--vault", str(vault), "recall", str(recorded_ids[0])]) == 0
    moment_output = json.loads(capsys.readouterr().out)
    assert moment_output["tier"] == 0

    assert main(["--vault", str(vault), "recall", "episode", str(recorded_ids[0])]) == 0
    episode_output = json.loads(capsys.readouterr().out)
    assert episode_output["tier"] == 1
    assert main(["--vault", str(vault), "recall", "1", str(recorded_ids[0])]) == 0
    integer_episode_output = json.loads(capsys.readouterr().out)
    assert integer_episode_output["tier"] == 1

    assert (
        main(["--vault", str(vault), "context", "--term", "SQLite", "--tokens", "64"])
        == 0
    )
    context_output = capsys.readouterr().out
    assert "[immediate]" in context_output or "[short-term]" in context_output


def test_cli_status_and_rebuild_index(tmp_path: Path, capsys):
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--vault",
                str(vault),
                "record",
                "Decision: status should expose processing state and index drift.",
            ]
        )
        == 0
    )
    item_id = int(capsys.readouterr().out.strip())
    assert main(["--vault", str(vault), "vault", "process"]) == 0
    capsys.readouterr()

    assert main(["--vault", str(vault), "vault", "status"]) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert status_output["schema_version"] >= 1
    assert status_output["item_counts"]["moment"] == 1
    assert Path(status_output["broker_path"]) == vault / "broker.db"
    assert status_output["items_needing_processing"] == 0

    delete_index_item(vault, item_id)

    assert main(["--vault", str(vault), "vault", "rebuild-index"]) == 0
    rebuild_output = json.loads(capsys.readouterr().out)
    assert rebuild_output["rebuilt_items"] >= 1

    assert main(["--vault", str(vault), "search", "index drift", "--limit", "5"]) == 0
    assert str(item_id) in capsys.readouterr().out


def test_cli_status_requires_initialized_vault(tmp_path: Path, capsys):
    vault = tmp_path / ".engram"
    vault.mkdir()

    assert main(["--vault", str(vault), "vault", "status"]) == 1
    assert "Vault is not initialized" in capsys.readouterr().out


def test_cli_arc_recall(tmp_path: Path, capsys):
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()
    recorded_ids: list[int] = []
    for text in ARC_HISTORY:
        assert main(["--vault", str(vault), "record", text]) == 0
        recorded_ids.append(int(capsys.readouterr().out.strip()))
    assert main(["--vault", str(vault), "vault", "process", "--max-passes", "50"]) == 0
    capsys.readouterr()

    arc_item = recent_items(vault, tier=2, limit=1)[0]

    assert main(["--vault", str(vault), "recall", "arc", str(recorded_ids[0])]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["tier"] == 2
    assert output["id"] == arc_item.id

    assert main(["--vault", str(vault), "recall", "arc", str(arc_item.id)]) == 0
    exact_output = json.loads(capsys.readouterr().out)
    assert exact_output["id"] == arc_item.id


def test_cli_integer_tier_arc_recall(tmp_path: Path, capsys):
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()
    recorded_ids: list[int] = []
    for text in ARC_HISTORY:
        assert main(["--vault", str(vault), "record", text]) == 0
        recorded_ids.append(int(capsys.readouterr().out.strip()))
    assert main(["--vault", str(vault), "vault", "process", "--max-passes", "50"]) == 0
    capsys.readouterr()

    assert main(["--vault", str(vault), "recall", "2", str(recorded_ids[0])]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["tier"] == 2


def test_cli_recall_rejects_invalid_argument_shapes(
    tmp_path: Path,
    capsys,
) -> None:
    vault = tmp_path / ".engram"
    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    for argv in (
        ["--vault", str(vault), "recall"],
        ["--vault", str(vault), "recall", "episode"],
        ["--vault", str(vault), "recall", "arc"],
        ["--vault", str(vault), "recall", "moment", "1"],
        ["--vault", str(vault), "recall", "item", "1"],
        ["--vault", str(vault), "recall", "0", "1"],
        ["--vault", str(vault), "recall", "1", "extra"],
        ["--vault", str(vault), "recall", "not-an-int"],
        ["--vault", str(vault), "recall", "episode", "not-an-int"],
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2


def test_cli_recall_returns_not_found_for_missing_item(
    tmp_path: Path,
    capsys,
) -> None:
    vault = tmp_path / ".engram"

    assert main(["--vault", str(vault), "init"]) == 0
    capsys.readouterr()

    assert main(["--vault", str(vault), "recall", "999"]) == EXIT_NOT_FOUND
    assert main(["--vault", str(vault), "recall", "episode", "999"]) == EXIT_NOT_FOUND


def test_cli_help_has_useful_preambles(capsys) -> None:
    def assert_help(argv: list[str], expected_preamble: str) -> str:
        with pytest.raises(SystemExit) as exc_info:
            main([*argv, "--help"])
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert expected_preamble in output
        return output

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    top_level_help = capsys.readouterr().out
    assert "Use the CLI when you want to record text" in top_level_help
    assert "The common path is:" in top_level_help
    assert (
        "Use recall when you already have a memory ID or a timeline anchor."
        in " ".join(top_level_help.split())
    )

    assert_help(
        ["init"],
        "Use init to create a new Engram vault.",
    )
    assert_help(
        ["version"],
        "Use version when you need the installed Engram build string.",
    )
    assert_help(
        ["record"],
        "Use record to store a new moment in the vault.",
    )
    assert_help(
        ["search"],
        "Use search when you know terms or concepts but not an exact ID.",
    )
    assert_help(
        ["context"],
        "Use context to assemble a multi-horizon prompt from the vault.",
    )
    recall_help = assert_help(
        ["recall"],
        "Use recall when you already have a memory ID or a timeline anchor.",
    )
    assert "CLI callers exit with the not-found code for missing items." in " ".join(
        recall_help.split()
    )
    assert "engram recall 2 MID" in recall_help
    assert "`SCOPE` may be `episode`, `arc`, or an integer" in recall_help

    assert_help(
        ["set-importance"],
        "Use set-importance when a memory should stay influential longer.",
    )
    assert_help(
        ["vault"],
        "Use vault subcommands when you need inspection or maintenance.",
    )
    assert_help(
        ["vault", "status"],
        "Use status to inspect vault health, lag, and repair state.",
    )
    assert_help(
        ["vault", "process"],
        "Use process to locally repair pending or failed vault work.",
    )
    assert_help(
        ["vault", "rebuild-index"],
        "Use rebuild-index to restore the retrieval projection from SQLite.",
    )
