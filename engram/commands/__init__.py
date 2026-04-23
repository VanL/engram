"""Shared command-layer operations for Engram surfaces.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-27], [MWS-28]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12], [LAS-20], [LAS-29]
"""

from __future__ import annotations

from engram.commands.memory import (
    context,
    open_vault,
    process,
    process_once,
    rebuild_index,
    recall,
    record,
    search,
    set_importance,
    snapshot_vault,
    status,
)

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
