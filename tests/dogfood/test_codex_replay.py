from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from engram import Engram
from engram.dogfood.codex_replay import (
    CodexCheckpointOptions,
    CodexReplayOptions,
    export_codex_checkpoints,
    import_codex_pairs,
    run_mechanical_validation,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_importer_refuses_existing_vault_path(tmp_path: Path) -> None:
    root = _corpus_root(tmp_path)
    vault_path = tmp_path / "run" / ".engram"
    run_dir = tmp_path / "run"
    vault_path.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="vault path already exists"):
        import_codex_pairs(
            CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir)
        )


def test_importer_refuses_non_empty_run_directory(tmp_path: Path) -> None:
    root = _corpus_root(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="run directory is not empty"):
        import_codex_pairs(
            CodexReplayOptions(
                root=root,
                vault_path=run_dir / ".engram",
                run_dir=run_dir,
            )
        )


def test_importer_creates_fresh_vault_and_manifest(tmp_path: Path) -> None:
    root = _corpus_root(tmp_path)
    run_dir = tmp_path / "run"
    vault_path = run_dir / ".engram"

    result = import_codex_pairs(
        CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir)
    )

    assert result.imported_moment_count == 2
    assert result.manifest_path.exists()
    assert result.summary_path.exists()
    rows = _read_jsonl(result.manifest_path)
    assert len(rows) == 2
    assert [row["global_import_index"] for row in rows] == [0, 1]
    assert result.imported_moment_ids == tuple(row["engram_moment_id"] for row in rows)
    assert list(result.imported_moment_ids) == sorted(result.imported_moment_ids)

    memory = Engram.open(vault_path)
    try:
        imported = [
            memory.recall(item_id, count_access=False)
            for item_id in result.imported_moment_ids
        ]
    finally:
        memory.close()
    assert imported[0].text.startswith("User:\nCreate the corpus validation plan.")
    assert "Developer instructions" not in imported[0].text
    assert "function_call" not in imported[1].text
    assert imported[1].text == (
        "User:\n"
        "First user message.\n\n"
        "Second user message.\n\n"
        "Assistant:\n"
        "Grouped reply."
    )


def test_manifest_rows_map_back_to_memory_text(tmp_path: Path) -> None:
    root = _corpus_root(tmp_path)
    run_dir = tmp_path / "run"
    vault_path = run_dir / ".engram"

    result = import_codex_pairs(
        CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir)
    )

    memory = Engram.open(vault_path)
    try:
        for row in _read_jsonl(result.manifest_path):
            item = memory.recall(row["engram_moment_id"], count_access=False)
            assert row["moment_text_sha256"] == _sha256_text(item.text)
            assert row["source_kind"] == "codex-session-jsonl"
    finally:
        memory.close()


def test_mechanical_validation_writes_report_and_context_snapshots(
    tmp_path: Path,
) -> None:
    root = _mechanical_corpus_root(tmp_path)
    run_dir = tmp_path / "mechanical"
    vault_path = run_dir / ".engram"

    result = run_mechanical_validation(
        CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir),
        snapshot_every=5,
        tokens=512,
    )

    assert result.report_path.exists()
    assert result.context_snapshot_paths
    assert all(
        path.read_text(encoding="utf-8").strip()
        for path in result.context_snapshot_paths
    )
    report = result.report
    assert report["imported_moment_count"] == 18
    assert report["moment_count"] == 18
    assert report["episode_count"] > 0
    assert report["arc_count"] > 0
    assert report["items_needing_processing"] == 0
    assert report["failed_processing_count"] == 0
    assert report["unindexed_item_count"] == 0
    assert report["index_row_count"] == report["total_item_count"]
    assert report["needs_rebuild"] is False
    assert report["mechanical_gate_passed"] is True


def test_mechanical_context_snapshots_do_not_increment_access_scores(
    tmp_path: Path,
) -> None:
    root = _mechanical_corpus_root(tmp_path)
    run_dir = tmp_path / "mechanical"
    vault_path = run_dir / ".engram"

    result = run_mechanical_validation(
        CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir),
        snapshot_every=6,
        tokens=512,
    )

    memory = Engram.open(vault_path)
    try:
        sampled = memory.recall(
            result.replay.imported_moment_ids[0],
            count_access=False,
        )
    finally:
        memory.close()
    assert sampled.access == 1.0


def test_checkpoint_export_writes_prior_only_prompts_and_oracle(
    tmp_path: Path,
) -> None:
    root = _mechanical_corpus_root(tmp_path)
    run_dir = tmp_path / "mechanical"
    vault_path = run_dir / ".engram"
    mechanical = run_mechanical_validation(
        CodexReplayOptions(root=root, vault_path=vault_path, run_dir=run_dir),
        snapshot_every=6,
        tokens=512,
    )

    output_dir = tmp_path / "checkpoints"
    result = export_codex_checkpoints(
        CodexCheckpointOptions(
            manifest_path=mechanical.replay.manifest_path,
            output_dir=output_dir,
            indices=(4,),
            min_prior_pairs=4,
            oracle_pairs=2,
            tokens=512,
        )
    )

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert metadata["checkpoint_id"] == "checkpoint-000004"
    assert metadata["prefix_pair_count"] == 4
    assert metadata["oracle_pair_count"] == 2
    assert metadata["status"]["failed_processing_items"] == 0
    assert metadata["status"]["needs_rebuild"] is False

    memory = Engram.open(artifact.vault_path)
    try:
        status = memory.status()
    finally:
        memory.close()
    assert status.item_counts["moment"] == 4

    baseline = artifact.baseline_path.read_text(encoding="utf-8")
    treatment = artifact.treatment_path.read_text(encoding="utf-8")
    oracle = artifact.oracle_path.read_text(encoding="utf-8")
    context = artifact.context_path.read_text(encoding="utf-8")
    assert "Question 1 about bravo retrieval index." in baseline
    assert "Question 1 about bravo retrieval index." in treatment
    assert "Answer 1 about bravo retrieval index." not in baseline
    assert "Answer 1 about bravo retrieval index." not in treatment
    assert "Answer 1 about bravo retrieval index." in oracle
    assert "Question 2 about bravo retrieval index." in oracle
    assert "Question 0 about alpha memory schema." in context
    assert artifact.scorecard_path.exists()
    assert result.summary_path.exists()


def test_checkpoint_export_refuses_non_empty_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "checkpoints"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="checkpoint output directory"):
        export_codex_checkpoints(
            CodexCheckpointOptions(
                manifest_path=tmp_path / "missing.jsonl",
                output_dir=output_dir,
            )
        )


def _corpus_root(tmp_path: Path) -> Path:
    root = tmp_path / ".codex"
    sessions_dir = root / "sessions"
    sessions_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURE_DIR / "current_event_log.jsonl",
        sessions_dir / "2026-current.jsonl",
    )
    shutil.copyfile(
        FIXTURE_DIR / "mixed_noise_event_log.jsonl",
        sessions_dir / "2026-mixed.jsonl",
    )
    return root


def _mechanical_corpus_root(tmp_path: Path) -> Path:
    root = tmp_path / ".codex"
    sessions_dir = root / "sessions"
    sessions_dir.mkdir(parents=True)
    path = sessions_dir / "mechanical.jsonl"
    lines = [
        {"type": "session_meta", "payload": {"id": "mechanical-session"}},
    ]
    topics = (
        "alpha memory schema",
        "bravo retrieval index",
        "charlie context budget",
        "delta background weft",
        "echo practical evaluation",
        "foxtrot checkpoint protocol",
    )
    minute = 0
    for topic_index, topic in enumerate(topics):
        for turn_index in range(3):
            minute += 1
            lines.append(
                {
                    "type": "response_item",
                    "timestamp": f"2026-04-20T13:{minute:02d}:00Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": f"Question {turn_index} about {topic}.",
                    },
                }
            )
            minute += 1
            lines.append(
                {
                    "type": "response_item",
                    "timestamp": f"2026-04-20T13:{minute:02d}:00Z",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": f"Answer {turn_index} about {topic}.",
                    },
                }
            )
        del topic_index
    path.write_text(
        "\n".join(json.dumps(line, sort_keys=True) for line in lines) + "\n",
        encoding="utf-8",
    )
    return root


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
