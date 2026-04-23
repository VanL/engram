"""SQLite runtime setup for Engram state stores.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

import sqlite3

from engram._constants import (
    MIN_SQLITE_VERSION,
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_WAL_AUTOCHECKPOINT,
)
from engram._exceptions import StoreOperationalError
from engram.store.db import SQLRunner


def require_supported_sqlite_runtime() -> None:
    """Raise if the linked SQLite runtime is too old for Engram migrations."""

    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        found = ".".join(str(part) for part in sqlite3.sqlite_version_info)
        required = ".".join(str(part) for part in MIN_SQLITE_VERSION)
        raise StoreOperationalError(
            f"SQLite {required} or newer is required; found {found}"
        )


def setup_sqlite_connection_phase(runner: SQLRunner) -> None:
    """Apply per-connection SQLite settings."""

    runner.run("PRAGMA foreign_keys = ON", fetch=False)
    runner.run(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}", fetch=False)
    runner.run(
        f"PRAGMA wal_autocheckpoint = {SQLITE_WAL_AUTOCHECKPOINT}",
        fetch=False,
    )


def setup_sqlite_optimization_phase(runner: SQLRunner) -> None:
    """Apply database-level SQLite settings that can require a write lock."""

    journal_mode = runner.run("PRAGMA journal_mode = WAL")
    if journal_mode and str(journal_mode[0][0]).lower() not in {"wal", "memory"}:
        raise StoreOperationalError("failed to enable SQLite WAL journal mode")
