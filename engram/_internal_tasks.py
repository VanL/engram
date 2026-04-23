"""Code-owned internal Weft TaskSpec inventory for Engram.

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-5], [MWS-9.2]
- docs/specs/14-embedded-weft-execution-model.md [EWM-6], [EWM-7], [EWM-13]
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from weft.core.taskspec import TaskSpec

PROCESS_ITEM_TASK_NAME: Final[str] = "engram-process-item"
"""Stable internal TaskSpec name for one-shot item processing."""

_TASK_NAMES: Final[tuple[str, ...]] = (PROCESS_ITEM_TASK_NAME,)


def internal_taskspec_names() -> tuple[str, ...]:
    """Return the stable Engram-owned internal TaskSpec names."""
    return _TASK_NAMES


def resolve_internal_taskspec(name: str, *, weft_root: Path) -> TaskSpec:
    """Return a template TaskSpec for one Engram-owned internal task."""

    if name == PROCESS_ITEM_TASK_NAME:
        return _build_process_item_taskspec(weft_root=weft_root)
    raise ValueError(f"unknown Engram internal task name: {name}")


def _build_process_item_taskspec(*, weft_root: Path) -> TaskSpec:
    payload = {
        "name": PROCESS_ITEM_TASK_NAME,
        "spec": {
            "type": "function",
            "function_target": "engram.background:process_memory_task",
            "timeout": 300.0,
            "weft_context": str(weft_root),
        },
        "metadata": {
            "owner": "engram",
            "kind": "process_item",
            "internal_task_name": PROCESS_ITEM_TASK_NAME,
        },
    }
    return TaskSpec.model_validate(
        payload,
        context={"template": True, "auto_expand": False},
    )


__all__ = [
    "PROCESS_ITEM_TASK_NAME",
    "internal_taskspec_names",
    "resolve_internal_taskspec",
]
