"""Codex JSONL corpus parsing for Engram dogfood validation.

This module is intentionally read-only. It extracts conversation-shaped pairs
from supported Codex event logs and reports diagnostics for unsupported shapes
without mutating Engram vault state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MessageRole = Literal["user", "assistant"]

TEXT_PART_KEYS = ("text", "input_text", "output_text")
EXCLUDED_ROOT_FILENAMES = {"history.jsonl", "session_index.jsonl"}


@dataclass(frozen=True, slots=True)
class CodexMessage:
    """A parsed user or assistant message from a Codex event log."""

    role: MessageRole
    text: str
    timestamp: str | None
    source_path: Path
    source_line: int
    session_id: str | None


@dataclass(frozen=True, slots=True)
class CodexConversationPair:
    """One imported conversation unit: pending user text plus next assistant."""

    source_path: Path
    pair_index: int
    session_id: str | None
    thread_name: str | None
    user_messages: tuple[CodexMessage, ...]
    assistant_message: CodexMessage

    @property
    def source_user_timestamps(self) -> tuple[str, ...]:
        """Return source timestamps from the user side of the pair."""
        return tuple(
            message.timestamp
            for message in self.user_messages
            if message.timestamp is not None
        )

    @property
    def source_assistant_timestamp(self) -> str | None:
        """Return the source timestamp from the assistant side of the pair."""
        return self.assistant_message.timestamp

    @property
    def sort_timestamp(self) -> str | None:
        """Return the best available timestamp for global replay ordering."""
        if self.source_user_timestamps:
            return self.source_user_timestamps[0]
        return self.source_assistant_timestamp

    @property
    def user_text(self) -> str:
        """Return grouped user text for the moment body."""
        return "\n\n".join(message.text for message in self.user_messages)

    @property
    def assistant_text(self) -> str:
        """Return assistant text for the moment body."""
        return self.assistant_message.text

    def to_moment_text(self) -> str:
        """Render this pair as the first-pass Engram moment text."""
        return f"User:\n{self.user_text}\n\nAssistant:\n{self.assistant_text}"


@dataclass(frozen=True, slots=True)
class CodexParseStats:
    """Diagnostics collected while parsing one Codex JSONL file."""

    total_records: int = 0
    message_records: int = 0
    eligible_messages: int = 0
    pairs: int = 0
    skipped_non_message_records: int = 0
    skipped_ineligible_messages: int = 0
    skipped_non_text_messages: int = 0
    ignored_unmatched_assistant_messages: int = 0
    incomplete_user_messages: int = 0
    malformed_records: int = 0
    unsupported_records: int = 0
    malformed_lines: tuple[int, ...] = ()
    unsupported_lines: tuple[int, ...] = ()

    @property
    def skipped_records(self) -> int:
        """Return the aggregate recoverably skipped record count."""
        return (
            self.skipped_non_message_records
            + self.skipped_ineligible_messages
            + self.skipped_non_text_messages
            + self.ignored_unmatched_assistant_messages
            + self.incomplete_user_messages
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "total_records": self.total_records,
            "message_records": self.message_records,
            "eligible_messages": self.eligible_messages,
            "pairs": self.pairs,
            "skipped_non_message_records": self.skipped_non_message_records,
            "skipped_ineligible_messages": self.skipped_ineligible_messages,
            "skipped_non_text_messages": self.skipped_non_text_messages,
            "ignored_unmatched_assistant_messages": (
                self.ignored_unmatched_assistant_messages
            ),
            "incomplete_user_messages": self.incomplete_user_messages,
            "malformed_records": self.malformed_records,
            "unsupported_records": self.unsupported_records,
            "malformed_lines": list(self.malformed_lines),
            "unsupported_lines": list(self.unsupported_lines),
            "skipped_records": self.skipped_records,
        }


@dataclass(frozen=True, slots=True)
class ParsedCodexSession:
    """Parsed result for one Codex JSONL file."""

    source_path: Path
    session_id: str | None
    thread_name: str | None
    pairs: tuple[CodexConversationPair, ...]
    stats: CodexParseStats


@dataclass(frozen=True, slots=True)
class CodexCorpusInspection:
    """Aggregate corpus inspection result before replay."""

    root: Path
    files: tuple[Path, ...]
    file_count: int
    supported_file_count: int
    unsupported_file_count: int
    pair_count: int
    stats: CodexParseStats
    first_timestamp: str | None
    last_timestamp: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "root": str(self.root),
            "file_count": self.file_count,
            "supported_file_count": self.supported_file_count,
            "unsupported_file_count": self.unsupported_file_count,
            "pair_count": self.pair_count,
            "stats": self.stats.to_dict(),
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
        }


@dataclass(slots=True)
class _StatsBuilder:
    total_records: int = 0
    message_records: int = 0
    eligible_messages: int = 0
    skipped_non_message_records: int = 0
    skipped_ineligible_messages: int = 0
    skipped_non_text_messages: int = 0
    ignored_unmatched_assistant_messages: int = 0
    incomplete_user_messages: int = 0
    malformed_records: int = 0
    unsupported_records: int = 0
    malformed_lines: list[int] | None = None
    unsupported_lines: list[int] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable line lists."""
        if self.malformed_lines is None:
            self.malformed_lines = []
        if self.unsupported_lines is None:
            self.unsupported_lines = []

    def freeze(self, *, pair_count: int) -> CodexParseStats:
        """Return an immutable stats snapshot."""
        malformed_lines = tuple(self.malformed_lines or ())
        unsupported_lines = tuple(self.unsupported_lines or ())
        return CodexParseStats(
            total_records=self.total_records,
            message_records=self.message_records,
            eligible_messages=self.eligible_messages,
            pairs=pair_count,
            skipped_non_message_records=self.skipped_non_message_records,
            skipped_ineligible_messages=self.skipped_ineligible_messages,
            skipped_non_text_messages=self.skipped_non_text_messages,
            ignored_unmatched_assistant_messages=(
                self.ignored_unmatched_assistant_messages
            ),
            incomplete_user_messages=self.incomplete_user_messages,
            malformed_records=self.malformed_records,
            unsupported_records=self.unsupported_records,
            malformed_lines=malformed_lines,
            unsupported_lines=unsupported_lines,
        )


def parse_codex_jsonl(path: Path) -> ParsedCodexSession:
    """Parse supported Codex event-log JSONL into conversation pairs."""
    source_path = path.expanduser().resolve(strict=False)
    session_id: str | None = None
    thread_name: str | None = None
    messages: list[CodexMessage] = []
    stats = _StatsBuilder()

    with source_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            stats.total_records += 1
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                stats.malformed_records += 1
                if stats.malformed_lines is not None:
                    stats.malformed_lines.append(line_number)
                continue
            if not isinstance(record, dict):
                stats.unsupported_records += 1
                if stats.unsupported_lines is not None:
                    stats.unsupported_lines.append(line_number)
                continue

            metadata = _extract_session_metadata(record)
            if metadata is not None:
                session_id = metadata[0] or session_id
                thread_name = metadata[1] or thread_name
                stats.skipped_non_message_records += 1
                continue

            if _is_unsupported_message_shape(record):
                stats.unsupported_records += 1
                if stats.unsupported_lines is not None:
                    stats.unsupported_lines.append(line_number)
                continue

            message_record = _extract_message_record(record)
            if message_record is None:
                stats.skipped_non_message_records += 1
                continue

            stats.message_records += 1
            role = message_record.get("role")
            if role not in ("user", "assistant"):
                stats.skipped_ineligible_messages += 1
                continue
            text = extract_message_text(message_record.get("content"))
            if text is None:
                stats.skipped_non_text_messages += 1
                continue
            stats.eligible_messages += 1
            messages.append(
                CodexMessage(
                    role=role,
                    text=text,
                    timestamp=_extract_timestamp(record, message_record),
                    source_path=source_path,
                    source_line=line_number,
                    session_id=session_id,
                )
            )

    pairs = _group_messages_into_pairs(
        messages,
        source_path=source_path,
        session_id=session_id,
        thread_name=thread_name,
        stats=stats,
    )
    return ParsedCodexSession(
        source_path=source_path,
        session_id=session_id,
        thread_name=thread_name,
        pairs=pairs,
        stats=stats.freeze(pair_count=len(pairs)),
    )


def extract_message_text(content: Any) -> str | None:
    """Extract textual content from a Codex message content field."""
    if isinstance(content, str):
        return _non_empty(content)
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            text = _non_empty(part)
            if text is not None:
                parts.append(text)
            continue
        if not isinstance(part, dict):
            continue
        for key in TEXT_PART_KEYS:
            value = part.get(key)
            if isinstance(value, str):
                text = _non_empty(value)
                if text is not None:
                    parts.append(text)
                break
    if not parts:
        return None
    return "\n".join(parts)


def discover_codex_jsonl_files(
    root: Path,
    *,
    include_sessions: bool = True,
    include_archived: bool = False,
) -> tuple[Path, ...]:
    """Discover supported Codex JSONL corpus candidates under ``root``."""
    corpus_root = root.expanduser().resolve(strict=False)
    candidates: list[Path] = []
    if include_sessions:
        candidates.extend(sorted((corpus_root / "sessions").rglob("*.jsonl")))
    if include_archived:
        candidates.extend(sorted((corpus_root / "archived_sessions").glob("*.jsonl")))

    seen: dict[Path, Path] = {}
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if _is_excluded_candidate(resolved, corpus_root):
            continue
        if resolved not in seen:
            seen[resolved] = resolved
    return tuple(sorted(seen.values(), key=lambda path: str(path)))


def inspect_codex_corpus(
    root: Path,
    *,
    include_sessions: bool = True,
    include_archived: bool = False,
) -> CodexCorpusInspection:
    """Parse-discoverable corpus files and return aggregate diagnostics."""
    corpus_root = root.expanduser().resolve(strict=False)
    files = discover_codex_jsonl_files(
        corpus_root,
        include_sessions=include_sessions,
        include_archived=include_archived,
    )
    parsed_sessions = tuple(parse_codex_jsonl(path) for path in files)
    stats = aggregate_parse_stats(session.stats for session in parsed_sessions)
    timestamps = sorted(
        timestamp
        for session in parsed_sessions
        for pair in session.pairs
        for timestamp in (pair.sort_timestamp,)
        if timestamp is not None
    )
    supported_file_count = sum(1 for session in parsed_sessions if session.pairs)
    unsupported_file_count = sum(
        1
        for session in parsed_sessions
        if not session.pairs and session.stats.unsupported_records > 0
    )
    return CodexCorpusInspection(
        root=corpus_root,
        files=files,
        file_count=len(files),
        supported_file_count=supported_file_count,
        unsupported_file_count=unsupported_file_count,
        pair_count=sum(len(session.pairs) for session in parsed_sessions),
        stats=stats,
        first_timestamp=timestamps[0] if timestamps else None,
        last_timestamp=timestamps[-1] if timestamps else None,
    )


def aggregate_parse_stats(stats: Any) -> CodexParseStats:
    """Aggregate multiple parse-stat snapshots."""
    total_records = 0
    message_records = 0
    eligible_messages = 0
    pairs = 0
    skipped_non_message_records = 0
    skipped_ineligible_messages = 0
    skipped_non_text_messages = 0
    ignored_unmatched_assistant_messages = 0
    incomplete_user_messages = 0
    malformed_records = 0
    unsupported_records = 0
    malformed_lines: list[int] = []
    unsupported_lines: list[int] = []

    for item in stats:
        total_records += item.total_records
        message_records += item.message_records
        eligible_messages += item.eligible_messages
        pairs += item.pairs
        skipped_non_message_records += item.skipped_non_message_records
        skipped_ineligible_messages += item.skipped_ineligible_messages
        skipped_non_text_messages += item.skipped_non_text_messages
        ignored_unmatched_assistant_messages += (
            item.ignored_unmatched_assistant_messages
        )
        incomplete_user_messages += item.incomplete_user_messages
        malformed_records += item.malformed_records
        unsupported_records += item.unsupported_records
        malformed_lines.extend(item.malformed_lines)
        unsupported_lines.extend(item.unsupported_lines)

    return CodexParseStats(
        total_records=total_records,
        message_records=message_records,
        eligible_messages=eligible_messages,
        pairs=pairs,
        skipped_non_message_records=skipped_non_message_records,
        skipped_ineligible_messages=skipped_ineligible_messages,
        skipped_non_text_messages=skipped_non_text_messages,
        ignored_unmatched_assistant_messages=ignored_unmatched_assistant_messages,
        incomplete_user_messages=incomplete_user_messages,
        malformed_records=malformed_records,
        unsupported_records=unsupported_records,
        malformed_lines=tuple(malformed_lines),
        unsupported_lines=tuple(unsupported_lines),
    )


def _extract_session_metadata(
    record: dict[str, Any],
) -> tuple[str | None, str | None] | None:
    if record.get("type") != "session_meta":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    session_id = _string_or_none(payload.get("id") or payload.get("session_id"))
    thread_name = _string_or_none(
        payload.get("thread_name") or payload.get("title") or payload.get("name")
    )
    return session_id, thread_name


def _extract_message_record(record: dict[str, Any]) -> dict[str, Any] | None:
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "message":
        return None
    return payload


def _is_unsupported_message_shape(record: dict[str, Any]) -> bool:
    record_type = record.get("type")
    if record_type == "message":
        return True
    return "role" in record and "content" in record and record_type != "response_item"


def _group_messages_into_pairs(
    messages: list[CodexMessage],
    *,
    source_path: Path,
    session_id: str | None,
    thread_name: str | None,
    stats: _StatsBuilder,
) -> tuple[CodexConversationPair, ...]:
    pending_user_messages: list[CodexMessage] = []
    pairs: list[CodexConversationPair] = []

    for message in messages:
        if message.role == "user":
            pending_user_messages.append(message)
            continue
        if not pending_user_messages:
            stats.ignored_unmatched_assistant_messages += 1
            continue
        pairs.append(
            CodexConversationPair(
                source_path=source_path,
                pair_index=len(pairs),
                session_id=session_id,
                thread_name=thread_name,
                user_messages=tuple(pending_user_messages),
                assistant_message=message,
            )
        )
        pending_user_messages = []

    if pending_user_messages:
        stats.incomplete_user_messages += len(pending_user_messages)
    return tuple(pairs)


def _extract_timestamp(
    record: dict[str, Any],
    message_record: dict[str, Any],
) -> str | None:
    value = record.get("timestamp") or message_record.get("timestamp")
    return _string_or_none(value)


def _is_excluded_candidate(path: Path, root: Path) -> bool:
    if path.name in EXCLUDED_ROOT_FILENAMES:
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith("recovery-") for part in relative.parts)


def _non_empty(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
