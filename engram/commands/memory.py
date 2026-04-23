"""Shared memory commands for CLI, client, and tool surfaces.

This layer adapts the `Engram` domain object into command-shaped operations
with stable, JSON-serializable return values. It should not add domain
behavior; it delegates to `Engram` and owns argument/serialization glue.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-12], [MWS-23], [MWS-27]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12], [LAS-20], [LAS-29]
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engram._constants import (
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_IMPORTANCE,
    DEFAULT_SEARCH_LIMIT,
    RECALL_SCOPE_ITEM,
    normalize_recall_scope,
)
from engram._exceptions import MemoryItemNotFoundError
from engram._models import MemoryItem, ProcessResult, SearchResult
from engram.core.embeddings import EmbeddingModel
from engram.core.memory import Engram


def open_vault(
    path: str | Path | None = None,
    *,
    create: bool = False,
    embedder: EmbeddingModel | None = None,
    autostart: bool = True,
    submit_background: bool = True,
) -> Engram:
    """Open or initialize an Engram vault."""

    if create:
        return Engram.init(
            path,
            embedder=embedder,
            autostart=autostart,
            submit_background=submit_background,
        )
    return Engram.open(path, embedder=embedder, submit_background=submit_background)


def record(
    memory: Engram,
    text: str,
    *,
    importance: int = DEFAULT_IMPORTANCE,
) -> int:
    """Use record to store a new moment in the vault.

    Record is the write entry point for scripts, apps, and agents. It returns
    the new memory ID immediately after the authoritative state-store write.
    Retrieval indexing and higher-tier coalescing happen later through Engram's
    background processing path.
    """

    return memory.record(text, importance=importance)


def context(
    memory: Engram,
    *,
    term: str | None = None,
    total_tokens: int = DEFAULT_CONTEXT_TOKENS,
) -> str:
    """Use context to assemble a multi-horizon prompt from the vault.

    Context is for agent-facing prompt assembly, not exact retrieval. It mixes
    recent moments, summary tiers, and high-importance retained items into one
    token-budgeted view. Pass `term` when the context should lean toward a
    topic without replacing recent history.
    """

    return memory.build_context(term=term, total_tokens=total_tokens).render()


def search(
    memory: Engram,
    query: str,
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
    count_access: bool = True,
) -> list[dict[str, Any]]:
    """Use search when you know terms or concepts but not an exact ID.

    Search runs Engram's hybrid retrieval path and returns JSON-serializable
    result dictionaries. By default it counts access on returned items because
    search is explicit retrieval.
    """

    return [
        _search_result_to_dict(result)
        for result in memory.search(query, limit=limit, count_access=count_access)
    ]


def recall(
    memory: Engram,
    item_id: str | int,
    *,
    scope: str | int = RECALL_SCOPE_ITEM,
    count_access: bool = True,
) -> dict[str, Any] | None:
    """Use recall when you already have a memory ID or a timeline anchor.

    Omit the
    scope for exact item recall. Pass `"episode"` or `1` for the containing
    episode, `"arc"` or `2` for the containing arc, or a higher integer tier
    such as `3` to target a deeper summary. Command-layer callers receive
    `None` for missing items.

    Examples:
        `engram recall MID`
        `engram recall episode MID`
        `engram recall 2 MID`
    """

    normalized_scope = normalize_recall_scope(scope)
    normalized_id = _normalize_item_id(item_id)
    try:
        item = memory.recall(
            normalized_id,
            scope=normalized_scope,
            count_access=count_access,
        )
    except MemoryItemNotFoundError:
        return None
    return _memory_item_to_dict(item)


def set_importance(
    memory: Engram,
    item_id: str | int,
    *,
    importance: int,
) -> dict[str, Any]:
    """Use set-importance when a memory should stay influential longer.

    Importance updates the stored relevance multiplier after an item already
    exists. This is the explicit maintenance path for elevating decisions or
    background facts that should remain easier to surface over time.
    """

    item = memory.set_importance(_normalize_item_id(item_id), importance=importance)
    return _memory_item_to_dict(item)


def status(memory: Engram, *, failed_item_limit: int = 5) -> dict[str, Any]:
    """Use status to inspect vault health, lag, and repair state.

    Status is read-only. It reports durable paths, item counts, failed
    processing, and index drift so a human or agent can decide whether repair
    work is needed.
    """

    return memory.status(failed_item_limit=failed_item_limit).model_dump(mode="json")


def rebuild_index(memory: Engram) -> dict[str, Any]:
    """Use rebuild-index to restore the retrieval projection from SQLite.

    Rebuild is a one-way repair path. SQLite remains authoritative; LanceDB is
    discarded and rebuilt from current durable state.
    """

    return memory.rebuild_index().model_dump(mode="json")


def process_once(memory: Engram, *, max_items: int = 1) -> dict[str, Any]:
    """Use process-once to repair a bounded number of pending vault items.

    This is mainly for tests and narrow operator workflows that need one local
    repair pass without draining the whole vault.
    """

    return _process_result_to_dict(memory.process_once(max_items=max_items))


def process(memory: Engram, *, max_passes: int = 1000) -> dict[str, Any]:
    """Use process to locally repair pending or failed vault work.

    Process runs the same domain repair operation used by Engram's background
    path until the vault becomes idle or `max_passes` is hit. This is for
    maintenance and recovery, not the normal steady-state write path.
    """

    return _process_result_to_dict(memory.process(max_passes=max_passes))


def snapshot_vault(
    memory_or_path: Engram | str | Path, output_path: str | Path
) -> None:
    """Copy a processed vault directory to `output_path`.

    The caller owns closing active handles before relying on the snapshot for
    long-term storage. This helper processes open `Engram` handles before copying
    so local processing state is complete.
    """

    if isinstance(memory_or_path, Engram):
        process(memory_or_path)
        source_path = memory_or_path.vault_path
    else:
        source_path = Path(memory_or_path).expanduser().resolve(strict=False)
    target_path = Path(output_path).expanduser().resolve(strict=False)

    if source_path == target_path:
        raise ValueError("snapshot output path must differ from source vault")
    if source_path in target_path.parents:
        raise ValueError("snapshot output path must not be inside source vault")
    if target_path.exists() and any(target_path.iterdir()):
        raise FileExistsError(f"snapshot output directory is not empty: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_path, target_path, dirs_exist_ok=True)


def _normalize_item_id(item_id: str | int) -> int:
    if isinstance(item_id, int):
        return item_id
    try:
        return int(item_id)
    except ValueError as exc:
        raise ValueError(f"item_id must be an integer: {item_id!r}") from exc


def _memory_item_to_dict(item: MemoryItem) -> dict[str, Any]:
    return item.model_dump(mode="json")


def _search_result_to_dict(result: SearchResult) -> dict[str, Any]:
    return asdict(result)


def _process_result_to_dict(result: ProcessResult) -> dict[str, Any]:
    return {
        "processed_ids": list(result.processed_ids),
        "created_episode_ids": list(result.created_episode_ids),
        "failed_item_ids": list(result.failed_item_ids),
        "created_arc_ids": list(result.created_arc_ids),
        "processed_count": result.processed_count,
        "is_idle": result.is_idle,
    }


__all__ = [
    "context",
    "process",
    "process_once",
    "open_vault",
    "recall",
    "rebuild_index",
    "record",
    "search",
    "set_importance",
    "snapshot_vault",
    "status",
]
