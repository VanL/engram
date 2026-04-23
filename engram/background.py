"""Weft-backed background task entry points for Engram.

Spec references:
- docs/specs/14-embedded-weft-execution-model.md [EWM-16], [EWM-18], [EWM-22]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-7]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def process_memory_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one Engram background-processing task inside a Weft worker."""

    vault_path = Path(str(payload["vault_path"])).expanduser().resolve()
    item_id = int(payload["item_id"])

    memory = None
    try:
        from engram.core.memory import Engram

        memory = Engram.open(vault_path)
        result = memory.repair_item(item_id)
        return {
            "processed_ids": list(result.processed_ids),
            "created_episode_ids": list(result.created_episode_ids),
            "created_arc_ids": list(result.created_arc_ids),
            "failed_item_ids": list(result.failed_item_ids),
            "processed_count": result.processed_count,
            "is_idle": result.is_idle,
        }
    except Exception as exc:
        if memory is None:
            try:
                from engram.core.memory import Engram

                Engram.record_processing_failure_for_vault(
                    vault_path,
                    item_id=item_id,
                    error=str(exc),
                )
            except Exception:  # pragma: no cover - defensive best effort
                logger.debug(
                    "Failed to record background task failure",
                    extra={"vault_path": str(vault_path), "item_id": item_id},
                    exc_info=True,
                )
        raise
    finally:
        if memory is not None:
            memory.close()


__all__ = [
    "process_memory_task",
]
