"""SQLite backend adapter for Engram state stores.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4], [LAS-7]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

from pathlib import Path

from engram.store.backends.sqlite.runtime import (
    require_supported_sqlite_runtime,
    setup_sqlite_connection_phase,
    setup_sqlite_optimization_phase,
)
from engram.store.backends.sqlite.schema import initialize_or_migrate_schema
from engram.store.backends.sqlite.validation import validate_existing_database_file
from engram.store.db import SetupPhase, SQLiteRunner, SQLRunner


class SQLiteBackend:
    """SQLite backend adapter."""

    name = "sqlite"

    def create_runner(self, db_path: Path) -> SQLiteRunner:
        """Return a SQLite SQL runner for one database path."""

        return SQLiteRunner(db_path)

    def setup(self, runner: SQLRunner, *, create: bool, vault_path: Path) -> None:
        """Defensively open, initialize, or migrate an Engram SQLite vault."""

        if not isinstance(runner, SQLiteRunner):
            raise TypeError("SQLiteBackend requires SQLiteRunner")
        require_supported_sqlite_runtime()
        validate_existing_database_file(runner.db_path, vault_path=vault_path)
        with runner.setup_lock(SetupPhase.CONNECTION):
            setup_sqlite_connection_phase(runner)
            setup_sqlite_optimization_phase(runner)
            initialize_or_migrate_schema(runner, create=create, vault_path=vault_path)
