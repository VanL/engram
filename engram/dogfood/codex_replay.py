"""Replay Codex JSONL corpus pairs into fresh Engram vaults.

The module command is internal dogfood tooling:

``python -m engram.dogfood.codex_replay inspect --root ~/.codex``
``python -m engram.dogfood.codex_replay mechanical ...``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engram import EngramClient
from engram._constants import (
    COALESCE_MIN_WINDOW,
    DEFAULT_CONTEXT_TOKENS,
    TIER_ARC,
    TIER_EPISODE,
    TIER_MOMENT,
    tier_name,
)
from engram.dogfood.codex_jsonl import (
    CodexConversationPair,
    CodexParseStats,
    aggregate_parse_stats,
    discover_codex_jsonl_files,
    inspect_codex_corpus,
    parse_codex_jsonl,
)

MANIFEST_SCHEMA_VERSION = 1
SOURCE_KIND = "codex-session-jsonl"


@dataclass(frozen=True, slots=True)
class CodexReplayOptions:
    """Options for replaying a Codex JSONL corpus into a fresh vault."""

    root: Path
    vault_path: Path
    run_dir: Path
    limit_files: int | None = None
    limit_pairs: int | None = None
    include_archived: bool = False
    include_sessions: bool = True
    run_id: str | None = None
    autostart_weft: bool = False
    submit_background: bool = False


@dataclass(frozen=True, slots=True)
class CodexManifestRow:
    """Sidecar mapping from one source conversation pair to an Engram moment."""

    schema_version: int
    run_id: str
    source_kind: str
    source_path: Path
    session_id: str | None
    thread_name: str | None
    pair_index: int
    global_import_index: int
    source_user_timestamps: tuple[str, ...]
    source_assistant_timestamp: str | None
    engram_moment_id: int
    moment_text_sha256: str
    user_preview: str
    assistant_preview: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "source_kind": self.source_kind,
            "source_path": str(self.source_path),
            "session_id": self.session_id,
            "thread_name": self.thread_name,
            "pair_index": self.pair_index,
            "global_import_index": self.global_import_index,
            "source_user_timestamps": list(self.source_user_timestamps),
            "source_assistant_timestamp": self.source_assistant_timestamp,
            "engram_moment_id": self.engram_moment_id,
            "moment_text_sha256": self.moment_text_sha256,
            "user_preview": self.user_preview,
            "assistant_preview": self.assistant_preview,
        }


@dataclass(frozen=True, slots=True)
class CodexReplayResult:
    """Result of replaying pairs into a fresh Engram vault."""

    run_id: str
    vault_path: Path
    run_dir: Path
    manifest_path: Path
    summary_path: Path
    source_file_count: int
    parsed_pair_count: int
    imported_moment_ids: tuple[int, ...]
    parser_stats: CodexParseStats

    @property
    def imported_moment_count(self) -> int:
        """Return the number of moments imported into Engram."""
        return len(self.imported_moment_ids)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "run_id": self.run_id,
            "vault_path": str(self.vault_path),
            "run_dir": str(self.run_dir),
            "manifest_path": str(self.manifest_path),
            "summary_path": str(self.summary_path),
            "source_file_count": self.source_file_count,
            "parsed_pair_count": self.parsed_pair_count,
            "imported_moment_count": self.imported_moment_count,
            "imported_moment_ids": list(self.imported_moment_ids),
            "parser_stats": self.parser_stats.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CodexMechanicalResult:
    """Result of mechanical validation after replay and local processing."""

    replay: CodexReplayResult
    report_path: Path
    context_snapshot_paths: tuple[Path, ...]
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CodexCheckpointOptions:
    """Options for exporting practical-evaluation checkpoint artifacts."""

    manifest_path: Path
    output_dir: Path
    indices: tuple[int, ...] = ()
    limit: int = 5
    min_prior_pairs: int = 20
    oracle_pairs: int = 3
    tokens: int = DEFAULT_CONTEXT_TOKENS
    max_passes: int = 1000
    autostart_weft: bool = False
    submit_background: bool = False


@dataclass(frozen=True, slots=True)
class CodexCheckpointArtifact:
    """One exported checkpoint artifact directory."""

    checkpoint_id: str
    global_import_index: int
    output_dir: Path
    vault_path: Path
    metadata_path: Path
    baseline_path: Path
    treatment_path: Path
    oracle_path: Path
    context_path: Path
    scorecard_path: Path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "global_import_index": self.global_import_index,
            "output_dir": str(self.output_dir),
            "vault_path": str(self.vault_path),
            "metadata_path": str(self.metadata_path),
            "baseline_path": str(self.baseline_path),
            "treatment_path": str(self.treatment_path),
            "oracle_path": str(self.oracle_path),
            "context_path": str(self.context_path),
            "scorecard_path": str(self.scorecard_path),
        }


@dataclass(frozen=True, slots=True)
class CodexCheckpointExportResult:
    """Result of exporting practical-evaluation checkpoint artifacts."""

    output_dir: Path
    summary_path: Path
    artifacts: tuple[CodexCheckpointArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "output_dir": str(self.output_dir),
            "summary_path": str(self.summary_path),
            "checkpoint_count": len(self.artifacts),
            "checkpoints": [artifact.to_dict() for artifact in self.artifacts],
        }


def import_codex_pairs(options: CodexReplayOptions) -> CodexReplayResult:
    """Replay parsed Codex conversation pairs into a fresh Engram vault."""
    return _run_import(options, after_import=None).replay


def run_mechanical_validation(
    options: CodexReplayOptions,
    *,
    snapshot_every: int = 50,
    tokens: int = DEFAULT_CONTEXT_TOKENS,
    max_passes: int = 1000,
) -> CodexMechanicalResult:
    """Import, process processing, snapshot context, and write a report."""
    if snapshot_every <= 0:
        raise ValueError("snapshot_every must be positive")
    if tokens <= 0:
        raise ValueError("tokens must be positive")

    snapshot_paths: list[Path] = []
    run_dir = options.run_dir.expanduser().resolve(strict=False)
    snapshot_dir = run_dir / "context-snapshots"

    def after_import(imported_count: int, client: EngramClient) -> None:
        if imported_count % snapshot_every != 0:
            return
        client.process(max_passes=max_passes)
        snapshot_paths.append(
            _write_context_snapshot(
                client,
                snapshot_dir=snapshot_dir,
                imported_count=imported_count,
                tokens=tokens,
            )
        )

    result = _run_import(options, after_import=after_import)
    replay = result.replay
    status = result.final_status
    if replay.imported_moment_count > 0:
        client = EngramClient.open(replay.vault_path)
        try:
            client.process(max_passes=max_passes)
            if not snapshot_paths or replay.imported_moment_count % snapshot_every != 0:
                snapshot_paths.append(
                    _write_context_snapshot(
                        client,
                        snapshot_dir=snapshot_dir,
                        imported_count=replay.imported_moment_count,
                        tokens=tokens,
                    )
                )
            status = client.status()
        finally:
            client.close()

    report = _build_mechanical_report(
        replay=replay,
        status=status,
        context_snapshot_count=len(snapshot_paths),
    )
    report_path = replay.run_dir / "mechanical-report.json"
    _write_json(report_path, report)
    return CodexMechanicalResult(
        replay=replay,
        report_path=report_path,
        context_snapshot_paths=tuple(snapshot_paths),
        report=report,
    )


def export_codex_checkpoints(
    options: CodexCheckpointOptions,
) -> CodexCheckpointExportResult:
    """Export prior-only checkpoint prompts for practical validation."""
    if options.limit < 0:
        raise ValueError("limit must be non-negative")
    if options.min_prior_pairs < 0:
        raise ValueError("min_prior_pairs must be non-negative")
    if options.oracle_pairs <= 0:
        raise ValueError("oracle_pairs must be positive")
    if options.tokens <= 0:
        raise ValueError("tokens must be positive")

    manifest_path = options.manifest_path.expanduser().resolve(strict=False)
    output_dir = options.output_dir.expanduser().resolve(strict=False)
    _require_empty_or_missing_dir(output_dir, label="checkpoint output directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_manifest_rows(manifest_path)
    selected_indices = _select_checkpoint_indices(
        rows,
        explicit_indices=options.indices,
        limit=options.limit,
        min_prior_pairs=options.min_prior_pairs,
        oracle_pairs=options.oracle_pairs,
    )
    row_by_index = {row.global_import_index: row for row in rows}
    pair_cache: dict[Path, tuple[CodexConversationPair, ...]] = {}
    artifacts: list[CodexCheckpointArtifact] = []

    for checkpoint_index in selected_indices:
        current_row = row_by_index[checkpoint_index]
        prior_rows = tuple(
            row
            for row in rows
            if row.global_import_index < current_row.global_import_index
        )
        oracle_rows = tuple(
            row
            for row in rows
            if row.global_import_index > current_row.global_import_index
        )[: options.oracle_pairs]
        artifact = _export_one_checkpoint(
            manifest_path=manifest_path,
            output_dir=output_dir,
            current_row=current_row,
            prior_rows=prior_rows,
            oracle_rows=oracle_rows,
            pair_cache=pair_cache,
            tokens=options.tokens,
            max_passes=options.max_passes,
            autostart_weft=options.autostart_weft,
            submit_background=options.submit_background,
        )
        artifacts.append(artifact)

    summary_path = output_dir / "checkpoints-summary.json"
    result = CodexCheckpointExportResult(
        output_dir=output_dir,
        summary_path=summary_path,
        artifacts=tuple(artifacts),
    )
    _write_json(summary_path, result.to_dict())
    return result


@dataclass(frozen=True, slots=True)
class _ImportRunResult:
    replay: CodexReplayResult
    final_status: Any


def _run_import(
    options: CodexReplayOptions,
    *,
    after_import: Callable[[int, EngramClient], None] | None,
) -> _ImportRunResult:
    root = options.root.expanduser().resolve(strict=False)
    vault_path = options.vault_path.expanduser().resolve(strict=False)
    run_dir = options.run_dir.expanduser().resolve(strict=False)
    run_id = options.run_id or _default_run_id()

    _require_fresh_run_paths(vault_path=vault_path, run_dir=run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    pairs, parser_stats, source_file_count, parsed_pair_count = _load_pairs(
        root=root,
        limit_files=options.limit_files,
        limit_pairs=options.limit_pairs,
        include_archived=options.include_archived,
        include_sessions=options.include_sessions,
    )
    manifest_path = run_dir / "manifest.jsonl"
    summary_path = run_dir / "run-summary.json"

    client: EngramClient | None = None
    imported_ids: tuple[int, ...] = ()
    try:
        client = EngramClient.init(
            vault_path,
            autostart=options.autostart_weft,
            submit_background=options.submit_background,
        )
        imported_ids = _import_pairs(
            client=client,
            pairs=pairs,
            manifest_path=manifest_path,
            run_id=run_id,
            after_import=after_import,
        )
        client.process(max_passes=1000)
        status = client.status()
    finally:
        if client is not None:
            client.close()

    replay = CodexReplayResult(
        run_id=run_id,
        vault_path=vault_path,
        run_dir=run_dir,
        manifest_path=manifest_path,
        summary_path=summary_path,
        source_file_count=source_file_count,
        parsed_pair_count=parsed_pair_count,
        imported_moment_ids=imported_ids,
        parser_stats=parser_stats,
    )
    _write_json(summary_path, replay.to_dict())
    return _ImportRunResult(replay=replay, final_status=status)


def _load_pairs(
    *,
    root: Path,
    limit_files: int | None,
    limit_pairs: int | None,
    include_archived: bool,
    include_sessions: bool,
) -> tuple[
    tuple[CodexConversationPair, ...],
    CodexParseStats,
    int,
    int,
]:
    files = discover_codex_jsonl_files(
        root,
        include_sessions=include_sessions,
        include_archived=include_archived,
    )
    if limit_files is not None:
        if limit_files < 0:
            raise ValueError("limit_files must be non-negative")
        files = files[:limit_files]
    parsed_sessions = tuple(parse_codex_jsonl(path) for path in files)
    pairs = tuple(
        sorted(
            (pair for parsed in parsed_sessions for pair in parsed.pairs),
            key=_pair_sort_key,
        )
    )
    parsed_pair_count = len(pairs)
    if limit_pairs is not None:
        if limit_pairs < 0:
            raise ValueError("limit_pairs must be non-negative")
        pairs = pairs[:limit_pairs]
    parser_stats = aggregate_parse_stats(parsed.stats for parsed in parsed_sessions)
    return pairs, parser_stats, len(files), parsed_pair_count


def _read_manifest_rows(path: Path) -> tuple[CodexManifestRow, ...]:
    rows: list[CodexManifestRow] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"manifest has malformed JSON at line {line_number}: {path}"
                ) from exc
            rows.append(_manifest_row_from_dict(payload, line_number=line_number))
    rows.sort(key=lambda row: row.global_import_index)
    if not rows:
        raise ValueError(f"manifest contains no rows: {path}")
    return tuple(rows)


def _manifest_row_from_dict(
    payload: Any,
    *,
    line_number: int,
) -> CodexManifestRow:
    if not isinstance(payload, dict):
        raise ValueError(f"manifest row {line_number} is not an object")
    return CodexManifestRow(
        schema_version=int(payload["schema_version"]),
        run_id=str(payload["run_id"]),
        source_kind=str(payload["source_kind"]),
        source_path=Path(str(payload["source_path"]))
        .expanduser()
        .resolve(strict=False),
        session_id=_optional_string(payload.get("session_id")),
        thread_name=_optional_string(payload.get("thread_name")),
        pair_index=int(payload["pair_index"]),
        global_import_index=int(payload["global_import_index"]),
        source_user_timestamps=tuple(
            str(value) for value in payload.get("source_user_timestamps", ())
        ),
        source_assistant_timestamp=_optional_string(
            payload.get("source_assistant_timestamp")
        ),
        engram_moment_id=int(payload["engram_moment_id"]),
        moment_text_sha256=str(payload["moment_text_sha256"]),
        user_preview=str(payload["user_preview"]),
        assistant_preview=str(payload["assistant_preview"]),
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _select_checkpoint_indices(
    rows: Sequence[CodexManifestRow],
    *,
    explicit_indices: Sequence[int],
    limit: int,
    min_prior_pairs: int,
    oracle_pairs: int,
) -> tuple[int, ...]:
    row_indices = {row.global_import_index for row in rows}
    if explicit_indices:
        selected = tuple(dict.fromkeys(explicit_indices))
        missing = [index for index in selected if index not in row_indices]
        if missing:
            raise ValueError(f"checkpoint indices are not in manifest: {missing}")
    else:
        eligible = [
            row.global_import_index
            for position, row in enumerate(rows)
            if position >= min_prior_pairs and position + oracle_pairs < len(rows)
        ]
        selected = tuple(eligible[:limit])

    for index in selected:
        prior_count = sum(1 for row in rows if row.global_import_index < index)
        oracle_count = sum(1 for row in rows if row.global_import_index > index)
        if prior_count < min_prior_pairs:
            raise ValueError(
                f"checkpoint {index} has {prior_count} prior pairs; "
                f"requires {min_prior_pairs}"
            )
        if oracle_count <= 0:
            raise ValueError(f"checkpoint {index} has no future oracle pairs")
    return selected


def _export_one_checkpoint(
    *,
    manifest_path: Path,
    output_dir: Path,
    current_row: CodexManifestRow,
    prior_rows: Sequence[CodexManifestRow],
    oracle_rows: Sequence[CodexManifestRow],
    pair_cache: dict[Path, tuple[CodexConversationPair, ...]],
    tokens: int,
    max_passes: int,
    autostart_weft: bool,
    submit_background: bool,
) -> CodexCheckpointArtifact:
    checkpoint_id = f"checkpoint-{current_row.global_import_index:06d}"
    checkpoint_dir = output_dir / checkpoint_id
    _require_empty_or_missing_dir(checkpoint_dir, label=f"{checkpoint_id} directory")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    current_pair = _pair_for_manifest_row(current_row, pair_cache)
    prior_pairs = tuple(_pair_for_manifest_row(row, pair_cache) for row in prior_rows)
    oracle_pairs = tuple(_pair_for_manifest_row(row, pair_cache) for row in oracle_rows)

    vault_path = checkpoint_dir / ".engram"
    client = EngramClient.init(
        vault_path,
        autostart=autostart_weft,
        submit_background=submit_background,
    )
    try:
        for pair in prior_pairs:
            client.record(pair.to_moment_text())
        client.process(max_passes=max_passes)
        rendered_context = client.context(max_tokens=tokens) or "(empty context)"
        status = client.status()
    finally:
        client.close()

    if (
        status["items_needing_processing"] != 0
        or status["failed_processing_items"] != 0
        or status["needs_rebuild"]
    ):
        raise RuntimeError(
            f"{checkpoint_id} prefix vault did not reach a clean mechanical state"
        )

    context_path = checkpoint_dir / "context.md"
    baseline_path = checkpoint_dir / "baseline.md"
    treatment_path = checkpoint_dir / "treatment-phase-a.md"
    oracle_path = checkpoint_dir / "oracle.md"
    scorecard_path = checkpoint_dir / "scorecard.md"
    metadata_path = checkpoint_dir / "metadata.json"

    context_path.write_text(rendered_context + "\n", encoding="utf-8")
    baseline_path.write_text(
        _render_baseline_prompt(current_pair),
        encoding="utf-8",
    )
    treatment_path.write_text(
        _render_treatment_prompt(current_pair, rendered_context),
        encoding="utf-8",
    )
    oracle_path.write_text(
        _render_oracle(current_pair=current_pair, oracle_pairs=oracle_pairs),
        encoding="utf-8",
    )
    scorecard_path.write_text(_render_scorecard(), encoding="utf-8")

    artifact = CodexCheckpointArtifact(
        checkpoint_id=checkpoint_id,
        global_import_index=current_row.global_import_index,
        output_dir=checkpoint_dir,
        vault_path=vault_path,
        metadata_path=metadata_path,
        baseline_path=baseline_path,
        treatment_path=treatment_path,
        oracle_path=oracle_path,
        context_path=context_path,
        scorecard_path=scorecard_path,
    )
    _write_json(
        metadata_path,
        {
            "schema_version": 1,
            "checkpoint_id": checkpoint_id,
            "manifest_path": str(manifest_path),
            "manifest_run_id": current_row.run_id,
            "global_import_index": current_row.global_import_index,
            "source_path": str(current_row.source_path),
            "source_pair_index": current_row.pair_index,
            "prefix_pair_count": len(prior_pairs),
            "oracle_pair_count": len(oracle_pairs),
            "tokens": tokens,
            "vault_path": str(vault_path),
            "status": status,
            "files": artifact.to_dict(),
        },
    )
    return artifact


def _pair_for_manifest_row(
    row: CodexManifestRow,
    cache: dict[Path, tuple[CodexConversationPair, ...]],
) -> CodexConversationPair:
    if row.source_path not in cache:
        parsed = parse_codex_jsonl(row.source_path)
        cache[row.source_path] = parsed.pairs
    pairs = cache[row.source_path]
    if row.pair_index < 0 or row.pair_index >= len(pairs):
        raise ValueError(
            f"manifest pair_index {row.pair_index} out of range for {row.source_path}"
        )
    pair = pairs[row.pair_index]
    digest = _sha256_text(pair.to_moment_text())
    if digest != row.moment_text_sha256:
        raise ValueError(
            f"manifest hash mismatch for {row.source_path} pair {row.pair_index}"
        )
    return pair


def _render_baseline_prompt(pair: CodexConversationPair) -> str:
    return (
        "# Baseline Prompt\n\n"
        "Answer this fresh-start user message without Engram context, future "
        "turns, or direct Engram recall.\n\n"
        "## User Message\n\n"
        f"{pair.user_text}\n"
    )


def _render_treatment_prompt(
    pair: CodexConversationPair,
    rendered_context: str,
) -> str:
    return (
        "# Treatment Phase A Prompt\n\n"
        "Answer this user message using only the prior-only Engram context below. "
        "Do not call Engram search or direct recall. Do not use oracle turns.\n\n"
        "## Engram Context\n\n"
        f"{rendered_context}\n\n"
        "## User Message\n\n"
        f"{pair.user_text}\n"
    )


def _render_oracle(
    *,
    current_pair: CodexConversationPair,
    oracle_pairs: Sequence[CodexConversationPair],
) -> str:
    lines = [
        "# Oracle Evidence",
        "",
        "Do not read this before writing the baseline and treatment answers.",
        "",
        "## Historical Assistant Response To Current User",
        "",
        current_pair.assistant_text,
        "",
    ]
    for index, pair in enumerate(oracle_pairs, start=1):
        lines.extend(
            [
                f"## Future Pair {index}",
                "",
                "### User",
                "",
                pair.user_text,
                "",
                "### Assistant",
                "",
                pair.assistant_text,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_scorecard() -> str:
    return (
        "# Checkpoint Scorecard\n\n"
        "- Score: helpful | neutral | harmful\n"
        "- Did Engram context improve correctness, continuity, or reduce user "
        "restatement?\n"
        "- Which context item helped or hurt?\n"
        "- What oracle evidence supports the score?\n"
        "- Notes:\n"
    )


def _import_pairs(
    *,
    client: EngramClient,
    pairs: Sequence[CodexConversationPair],
    manifest_path: Path,
    run_id: str,
    after_import: Callable[[int, EngramClient], None] | None,
) -> tuple[int, ...]:
    imported_ids: list[int] = []
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for global_index, pair in enumerate(pairs):
            moment_text = pair.to_moment_text()
            moment_id = client.record(moment_text)
            imported_ids.append(moment_id)
            row = CodexManifestRow(
                schema_version=MANIFEST_SCHEMA_VERSION,
                run_id=run_id,
                source_kind=SOURCE_KIND,
                source_path=pair.source_path,
                session_id=pair.session_id,
                thread_name=pair.thread_name,
                pair_index=pair.pair_index,
                global_import_index=global_index,
                source_user_timestamps=pair.source_user_timestamps,
                source_assistant_timestamp=pair.source_assistant_timestamp,
                engram_moment_id=moment_id,
                moment_text_sha256=_sha256_text(moment_text),
                user_preview=_preview(pair.user_text),
                assistant_preview=_preview(pair.assistant_text),
            )
            handle.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
            if after_import is not None:
                after_import(len(imported_ids), client)
    return tuple(imported_ids)


def _build_mechanical_report(
    *,
    replay: CodexReplayResult,
    status: Mapping[str, Any],
    context_snapshot_count: int,
) -> dict[str, Any]:
    item_counts = dict(status["item_counts"])
    moment_name = tier_name(TIER_MOMENT)
    episode_name = tier_name(TIER_EPISODE)
    arc_name = tier_name(TIER_ARC)
    moment_count = int(item_counts.get(moment_name, 0))
    episode_count = int(item_counts.get(episode_name, 0))
    arc_count = int(item_counts.get(arc_name, 0))
    total_item_count = sum(int(count) for count in item_counts.values())
    gate = _mechanical_gate_passed(
        imported_moments=replay.imported_moment_count,
        total_item_count=total_item_count,
        indexed_items=int(status["indexed_items"]),
        index_row_count=int(status["index_rows"]),
        items_needing_processing=int(status["items_needing_processing"]),
        failed_processing_items=int(status["failed_processing_items"]),
        needs_rebuild=bool(status["needs_rebuild"]),
        episode_count=episode_count,
        arc_count=arc_count,
        context_snapshot_count=context_snapshot_count,
    )
    return {
        "run_id": replay.run_id,
        "imported_moment_count": replay.imported_moment_count,
        "total_item_count": total_item_count,
        "moment_count": moment_count,
        "episode_count": episode_count,
        "arc_count": arc_count,
        "indexed_items": int(status["indexed_items"]),
        "index_row_count": int(status["index_rows"]),
        "items_needing_processing": int(status["items_needing_processing"]),
        "failed_processing_count": int(status["failed_processing_items"]),
        "unindexed_item_count": int(status["unindexed_items"]),
        "context_snapshot_count": context_snapshot_count,
        "parser_skipped_count": replay.parser_stats.skipped_records,
        "parser_malformed_count": replay.parser_stats.malformed_records,
        "parser_unsupported_count": replay.parser_stats.unsupported_records,
        "needs_rebuild": bool(status["needs_rebuild"]),
        "mechanical_gate_passed": gate,
    }


def _mechanical_gate_passed(
    *,
    imported_moments: int,
    total_item_count: int,
    indexed_items: int,
    index_row_count: int,
    items_needing_processing: int,
    failed_processing_items: int,
    needs_rebuild: bool,
    episode_count: int,
    arc_count: int,
    context_snapshot_count: int,
) -> bool:
    episode_required = imported_moments >= COALESCE_MIN_WINDOW + 1
    arc_required = imported_moments >= COALESCE_MIN_WINDOW * (COALESCE_MIN_WINDOW + 2)
    if imported_moments <= 0:
        return False
    if indexed_items <= 0:
        return False
    if needs_rebuild:
        return False
    if indexed_items != total_item_count or index_row_count != total_item_count:
        return False
    if items_needing_processing != 0 or failed_processing_items != 0:
        return False
    if context_snapshot_count <= 0:
        return False
    if episode_required and episode_count <= 0:
        return False
    if arc_required and arc_count <= 0:
        return False
    return True


def _write_context_snapshot(
    client: EngramClient,
    *,
    snapshot_dir: Path,
    imported_count: int,
    tokens: int,
) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"context-{imported_count:06d}.md"
    rendered = client.context(max_tokens=tokens) or "(empty context)"
    text = f"# Context Snapshot {imported_count}\n\n{rendered}\n"
    path.write_text(text, encoding="utf-8")
    return path


def _require_fresh_run_paths(*, vault_path: Path, run_dir: Path) -> None:
    if vault_path.exists():
        raise FileExistsError(f"vault path already exists: {vault_path}")
    _require_empty_or_missing_dir(run_dir, label="run directory")


def _require_empty_or_missing_dir(path: Path, *, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"{label} is not empty: {path}")


def _pair_sort_key(pair: CodexConversationPair) -> tuple[str, str, int]:
    return (
        pair.sort_timestamp or "",
        str(pair.source_path),
        pair.pair_index,
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preview(text: str, *, limit: int = 160) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 3] + "..."


def _default_run_id() -> str:
    return time.strftime("codex-%Y%m%d-%H%M%S", time.localtime())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the internal dogfood module CLI."""
    parser = argparse.ArgumentParser(prog="python -m engram.dogfood.codex_replay")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--root", type=Path, default=Path("~/.codex"))
    inspect_parser.add_argument("--include-archived", action="store_true")
    inspect_parser.add_argument("--no-sessions", action="store_true")

    mechanical_parser = subparsers.add_parser("mechanical")
    mechanical_parser.add_argument("--root", type=Path, default=Path("~/.codex"))
    mechanical_parser.add_argument("--vault", type=Path, required=True)
    mechanical_parser.add_argument("--run-dir", type=Path, required=True)
    mechanical_parser.add_argument("--limit-files", type=int, default=None)
    mechanical_parser.add_argument("--limit-pairs", type=int, default=None)
    mechanical_parser.add_argument("--include-archived", action="store_true")
    mechanical_parser.add_argument("--no-sessions", action="store_true")
    mechanical_parser.add_argument("--autostart-weft", action="store_true")
    mechanical_parser.add_argument("--submit-background", action="store_true")
    mechanical_parser.add_argument("--snapshot-every", type=int, default=50)
    mechanical_parser.add_argument("--tokens", type=int, default=2048)
    mechanical_parser.add_argument("--max-passes", type=int, default=1000)

    checkpoints_parser = subparsers.add_parser("checkpoints")
    checkpoints_parser.add_argument("--manifest", type=Path, required=True)
    checkpoints_parser.add_argument("--output", type=Path, required=True)
    checkpoints_parser.add_argument("--indices", type=str, default="")
    checkpoints_parser.add_argument("--limit", type=int, default=5)
    checkpoints_parser.add_argument("--min-prior-pairs", type=int, default=20)
    checkpoints_parser.add_argument("--oracle-pairs", type=int, default=3)
    checkpoints_parser.add_argument("--tokens", type=int, default=2048)
    checkpoints_parser.add_argument("--max-passes", type=int, default=1000)
    checkpoints_parser.add_argument("--autostart-weft", action="store_true")
    checkpoints_parser.add_argument("--submit-background", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        inspection = inspect_codex_corpus(
            args.root,
            include_archived=args.include_archived,
            include_sessions=not args.no_sessions,
        )
        print(json.dumps(inspection.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "mechanical":
        options = CodexReplayOptions(
            root=args.root,
            vault_path=args.vault,
            run_dir=args.run_dir,
            limit_files=args.limit_files,
            limit_pairs=args.limit_pairs,
            include_archived=args.include_archived,
            include_sessions=not args.no_sessions,
            autostart_weft=args.autostart_weft,
            submit_background=args.submit_background,
        )
        mechanical_result = run_mechanical_validation(
            options,
            snapshot_every=args.snapshot_every,
            tokens=args.tokens,
            max_passes=args.max_passes,
        )
        print(json.dumps(mechanical_result.report, indent=2, sort_keys=True))
        return 0
    if args.command == "checkpoints":
        checkpoint_result = export_codex_checkpoints(
            CodexCheckpointOptions(
                manifest_path=args.manifest,
                output_dir=args.output,
                indices=_parse_indices(args.indices),
                limit=args.limit,
                min_prior_pairs=args.min_prior_pairs,
                oracle_pairs=args.oracle_pairs,
                tokens=args.tokens,
                max_passes=args.max_passes,
                autostart_weft=args.autostart_weft,
                submit_background=args.submit_background,
            )
        )
        print(json.dumps(checkpoint_result.to_dict(), indent=2, sort_keys=True))
        return 0
    return 1


def _parse_indices(value: str) -> tuple[int, ...]:
    stripped = value.strip()
    if not stripped:
        return ()
    indices: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            continue
        indices.append(int(token))
    return tuple(indices)


if __name__ == "__main__":  # pragma: no cover - module CLI
    raise SystemExit(main())
