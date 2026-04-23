"""Embedded Weft runtime bootstrap and task submission.

Spec references:
- docs/specs/14-embedded-weft-execution-model.md [EWM-13], [EWM-15], [EWM-16]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-7]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from weft.client import WeftClient
from weft.commands import cmd_init as weft_cmd_init
from weft.context import build_context

from engram._constants import (
    load_embedded_weft_config,
    load_embedded_weft_overrides,
)
from engram._exceptions import EngramError
from engram._internal_tasks import (
    PROCESS_ITEM_TASK_NAME,
    resolve_internal_taskspec,
)


def _weft_runtime_root_and_config(vault_path: Path) -> tuple[Path, dict[str, Any]]:
    """Return the Weft project root and config Engram should use for one vault."""

    root = vault_path.parent
    return root, load_embedded_weft_config(vault_path)


def initialize_embedded_weft_project(
    vault_path: Path, *, autostart: bool = True
) -> None:
    """Initialize the embedded Weft project for one Engram vault."""

    resolved_vault_path = vault_path.expanduser().resolve()
    weft_root = resolved_vault_path.parent
    weft_root.mkdir(parents=True, exist_ok=True)
    overrides = load_embedded_weft_overrides(resolved_vault_path)
    exit_code = int(
        weft_cmd_init(
            weft_root,
            quiet=True,
            autostart=autostart,
            overrides=overrides,
        )
    )
    if exit_code != 0:
        raise EngramError(
            f"failed to initialize embedded Weft runtime for vault: {resolved_vault_path}"
        )


def submit_process_item_task(vault_path: Path, *, item_id: int) -> str:
    """Submit one Engram background-processing task through Weft."""

    return submit_internal_task(
        vault_path,
        task_name=PROCESS_ITEM_TASK_NAME,
        payload={
            "vault_path": str(vault_path),
            "item_id": item_id,
        },
    )


def submit_internal_task(
    vault_path: Path,
    *,
    task_name: str,
    payload: dict[str, Any],
) -> str:
    """Submit one Engram-owned internal task through the embedded Weft runtime."""

    weft_root, weft_config = _weft_runtime_root_and_config(vault_path)
    context = build_context(spec_context=weft_root, config=weft_config)

    taskspec = resolve_internal_taskspec(task_name, weft_root=weft_root)
    client = WeftClient.from_weft_context(context)
    task = client.submit(
        taskspec,
        payload={
            "payload": payload,
        },
    )
    return str(task.tid)


__all__ = [
    "initialize_embedded_weft_project",
    "submit_internal_task",
    "submit_process_item_task",
]
