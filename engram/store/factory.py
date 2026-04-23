"""State-store backend factory.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from pathlib import Path

from engram._constants import load_config
from engram._exceptions import StoreBackendNotSupportedError
from engram.store.base import StateStore
from engram.store.sqlite import SQLiteStateStore


def open_state_store(
    vault_path: Path,
    *,
    create: bool,
    backend_name: str | None = None,
) -> StateStore:
    """Open the configured Engram state store backend.

    PostgreSQL is intentionally not implemented yet. The factory exists so the
    rest of Engram stops hard-coding SQLite and so unsupported backend choices
    fail at the boundary with a clear error.
    """

    resolved_backend = (backend_name or str(load_config()["backend"])).lower()
    if resolved_backend == "sqlite":
        return SQLiteStateStore(vault_path, create=create)
    if resolved_backend in {"pg", "postgres", "postgresql"}:
        raise StoreBackendNotSupportedError(
            "PostgreSQL state backend is planned but not implemented"
        )
    raise StoreBackendNotSupportedError(
        f"Unsupported Engram state backend: {resolved_backend}"
    )
