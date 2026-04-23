from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engram.dogfood.codex_jsonl import (
    discover_codex_jsonl_files,
    inspect_codex_corpus,
    parse_codex_jsonl,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parser_extracts_user_assistant_pairs_from_current_event_log() -> None:
    parsed = parse_codex_jsonl(FIXTURE_DIR / "current_event_log.jsonl")

    assert parsed.session_id == "session-current"
    assert parsed.thread_name == "Codex corpus validation"
    assert len(parsed.pairs) == 1
    pair = parsed.pairs[0]
    assert pair.user_text == "Create the corpus validation plan."
    assert pair.assistant_text == "I will build parser fixtures first, then replay."
    assert pair.to_moment_text() == (
        "User:\n"
        "Create the corpus validation plan.\n\n"
        "Assistant:\n"
        "I will build parser fixtures first, then replay."
    )
    assert parsed.stats.message_records == 3
    assert parsed.stats.eligible_messages == 2
    assert parsed.stats.skipped_ineligible_messages == 1


def test_parser_groups_consecutive_user_messages_before_assistant() -> None:
    parsed = parse_codex_jsonl(FIXTURE_DIR / "mixed_noise_event_log.jsonl")

    assert len(parsed.pairs) == 1
    pair = parsed.pairs[0]
    assert pair.user_text == "First user message.\n\nSecond user message."
    assert pair.assistant_text == "Grouped reply."
    assert pair.source_user_timestamps == (
        "2026-04-20T11:01:00Z",
        "2026-04-20T11:02:00Z",
    )
    assert pair.source_assistant_timestamp == "2026-04-20T11:05:00Z"


def test_parser_excludes_developer_tool_reasoning_and_telemetry_records() -> None:
    current = parse_codex_jsonl(FIXTURE_DIR / "current_event_log.jsonl")
    mixed = parse_codex_jsonl(FIXTURE_DIR / "mixed_noise_event_log.jsonl")

    assert "Developer instructions" not in current.pairs[0].to_moment_text()
    assert mixed.stats.skipped_non_message_records == 4
    assert "token count event" not in mixed.pairs[0].to_moment_text()
    assert "hidden reasoning" not in mixed.pairs[0].to_moment_text()
    assert "function_call" not in mixed.pairs[0].to_moment_text()


def test_parser_counts_incomplete_and_unmatched_messages() -> None:
    parsed = parse_codex_jsonl(FIXTURE_DIR / "mixed_noise_event_log.jsonl")

    assert parsed.stats.ignored_unmatched_assistant_messages == 1
    assert parsed.stats.incomplete_user_messages == 1


def test_parser_reports_unsupported_legacy_shape_without_ingesting_it() -> None:
    parsed = parse_codex_jsonl(FIXTURE_DIR / "unsupported_legacy_shape.jsonl")

    assert parsed.pairs == ()
    assert parsed.stats.unsupported_records == 1
    assert parsed.stats.unsupported_lines == (1,)


def test_parser_counts_malformed_jsonl_lines() -> None:
    parsed = parse_codex_jsonl(FIXTURE_DIR / "malformed_event_log.jsonl")

    assert len(parsed.pairs) == 1
    assert parsed.stats.malformed_records == 1
    assert parsed.stats.malformed_lines == (3,)


def test_discovery_uses_sessions_by_default_and_archived_only_when_requested(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".codex"
    sessions_file = root / "sessions" / "2026" / "current.jsonl"
    archived_file = root / "archived_sessions" / "archived.jsonl"
    recovery_file = root / "recovery-20260420" / "ignored.jsonl"
    history_file = root / "history.jsonl"
    index_file = root / "session_index.jsonl"
    for path in (sessions_file, archived_file, recovery_file, history_file, index_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_DIR / "current_event_log.jsonl", path)

    default_files = discover_codex_jsonl_files(root)
    all_files = discover_codex_jsonl_files(root, include_archived=True)

    assert default_files == (sessions_file.resolve(),)
    assert all_files == (archived_file.resolve(), sessions_file.resolve())
    assert recovery_file.resolve() not in all_files
    assert history_file.resolve() not in all_files
    assert index_file.resolve() not in all_files


def test_discovery_deduplicates_resolved_paths(tmp_path: Path) -> None:
    root = tmp_path / ".codex"
    sessions_file = root / "sessions" / "current.jsonl"
    archived_link = root / "archived_sessions" / "current-link.jsonl"
    sessions_file.parent.mkdir(parents=True, exist_ok=True)
    archived_link.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_DIR / "current_event_log.jsonl", sessions_file)
    try:
        archived_link.symlink_to(sessions_file)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    files = discover_codex_jsonl_files(root, include_archived=True)

    assert files == (sessions_file.resolve(),)


def test_inspection_reports_unsupported_files_without_failing(tmp_path: Path) -> None:
    root = tmp_path / ".codex"
    supported = root / "sessions" / "supported.jsonl"
    unsupported = root / "sessions" / "unsupported.jsonl"
    supported.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_DIR / "current_event_log.jsonl", supported)
    shutil.copyfile(FIXTURE_DIR / "unsupported_legacy_shape.jsonl", unsupported)

    inspection = inspect_codex_corpus(root)

    assert inspection.file_count == 2
    assert inspection.supported_file_count == 1
    assert inspection.unsupported_file_count == 1
    assert inspection.pair_count == 1
    assert inspection.stats.unsupported_records == 1
