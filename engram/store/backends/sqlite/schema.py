"""SQLite schema initialization and migration for Engram.

Spec references:
- docs/specs/12-local-app-surface.md [LAS-4], [LAS-7]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

import time
from pathlib import Path

from engram._constants import (
    CURRENT_SQLITE_SCHEMA_VERSION,
    ENGRAM_STATE_MAGIC,
    MEMORY_ID_CLOCK_TABLE,
    STATE_MAGIC_KEY,
    VAULT_CREATED_AT_KEY,
    VAULT_SCHEMA_VERSION_KEY,
)
from engram._exceptions import (
    StoreIntegrityError,
    StoreVersionError,
    VaultNotInitializedError,
)
from engram.store._sql import sqlite as sqlite_sql
from engram.store.db import SQLRunner

_LEGACY_SCHEMA_VERSION_KEY = "vault_schema_version"
_REQUIRED_TABLES = {
    "vault_meta",
    "memory_items",
    "memory_edges",
    MEMORY_ID_CLOCK_TABLE,
}
_ENGRAM_TABLES = {
    "vault_meta",
    "memory_items",
    "memory_edges",
    MEMORY_ID_CLOCK_TABLE,
    "pending_tasks",
}
_MEMORY_EDGE_COLUMNS = ("parent_id", "child_id", "position")
_MEMORY_ID_CLOCK_COLUMNS = ("singleton", "last_memory_id")
_LEGACY_MEMORY_ITEM_COLUMNS = (
    "id",
    "tier",
    "text",
    "created_at",
    "access",
    "relevance",
    "indexed_at",
    "summary_terms_json",
)
_V3_MEMORY_ITEM_COLUMNS = (
    "id",
    "tier",
    "text",
    "created_at",
    "access",
    "relevance",
    "indexed_at",
    "summary_terms_json",
    "processing_status",
    "processing_attempts",
    "last_processing_error",
    "last_task_tid",
    "last_task_updated_at",
)


def initialize_or_migrate_schema(
    runner: SQLRunner,
    *,
    create: bool,
    vault_path: Path,
) -> None:
    """Create a new schema or migrate a known older Engram shape."""

    with runner.transaction():
        table_names = _table_names(runner)
        if not table_names:
            if not create:
                raise VaultNotInitializedError(str(vault_path))
            _create_current_schema(runner)
            _verify_current_schema(runner, vault_path=vault_path)
            return
        if not table_names & _ENGRAM_TABLES:
            raise VaultNotInitializedError(str(vault_path))
        if _is_current_schema(runner):
            _ensure_indexes(runner)
            _verify_current_schema(runner, vault_path=vault_path)
            return
        _migrate_known_schema(runner, vault_path=vault_path)
        _verify_current_schema(runner, vault_path=vault_path)


def select_metadata(runner: SQLRunner) -> dict[str, str]:
    """Return vault metadata as key/value strings."""

    if "vault_meta" not in _table_names(runner):
        return {}
    rows = runner.run(
        """
        SELECT key, value
        FROM vault_meta
        ORDER BY key ASC
        """
    )
    return {str(row[0]): str(row[1]) for row in rows}


def read_schema_version(runner: SQLRunner) -> int:
    """Return the current schema version from metadata."""

    version = _metadata_schema_version(select_metadata(runner))
    if version is None:
        raise StoreVersionError("Engram state store is missing schema_version")
    return version


def _migrate_known_schema(runner: SQLRunner, *, vault_path: Path) -> None:
    table_names = _table_names(runner)
    metadata = select_metadata(runner)
    magic = metadata.get(STATE_MAGIC_KEY)
    if magic is not None and magic != ENGRAM_STATE_MAGIC:
        raise VaultNotInitializedError(str(vault_path))

    version = _metadata_schema_version(metadata)
    if version is not None and version > CURRENT_SQLITE_SCHEMA_VERSION:
        raise StoreVersionError(
            "Engram state store schema is newer than this runtime: "
            f"{version} > {CURRENT_SQLITE_SCHEMA_VERSION}"
        )

    if "memory_items" not in table_names or "memory_edges" not in table_names:
        raise VaultNotInitializedError(str(vault_path))
    if _column_names(runner, "memory_edges") != _MEMORY_EDGE_COLUMNS:
        raise VaultNotInitializedError(str(vault_path))

    item_columns = _column_names(runner, "memory_items")
    if item_columns == sqlite_sql.MEMORY_ITEM_COLUMNS:
        _ensure_metadata(runner)
        _ensure_memory_edges_foreign_keys(runner)
        _ensure_memory_id_clock(runner)
        _ensure_indexes(runner)
        return
    if item_columns == _V3_MEMORY_ITEM_COLUMNS:
        _migrate_v3_queue_shape(runner)
        return
    if item_columns == _LEGACY_MEMORY_ITEM_COLUMNS:
        _migrate_legacy_no_meta_shape(runner)
        return
    raise VaultNotInitializedError(str(vault_path))


def _migrate_v3_queue_shape(runner: SQLRunner) -> None:
    if "processing_status" in _column_names(runner, "memory_items"):
        runner.run(
            "ALTER TABLE memory_items DROP COLUMN processing_status",
            fetch=False,
        )
    _ensure_metadata(runner)
    _ensure_memory_edges_foreign_keys(runner)
    _ensure_memory_id_clock(runner)
    _ensure_indexes(runner)


def _migrate_legacy_no_meta_shape(runner: SQLRunner) -> None:
    _add_missing_processing_columns(runner)
    _ensure_metadata(runner)
    _ensure_memory_edges_foreign_keys(runner)
    if "pending_tasks" in _table_names(runner):
        runner.run("DROP TABLE pending_tasks", fetch=False)
    _ensure_memory_id_clock(runner)
    _ensure_indexes(runner)


def _create_current_schema(runner: SQLRunner) -> None:
    runner.run(sqlite_sql.CREATE_VAULT_META, fetch=False)
    runner.run(sqlite_sql.CREATE_MEMORY_ITEMS, fetch=False)
    runner.run(sqlite_sql.CREATE_MEMORY_EDGES, fetch=False)
    runner.run(sqlite_sql.CREATE_MEMORY_ID_CLOCK, fetch=False)
    runner.run(sqlite_sql.INIT_MEMORY_ID_CLOCK_EMPTY, fetch=False)
    _ensure_metadata(runner)
    _ensure_indexes(runner)


def _ensure_metadata(runner: SQLRunner) -> None:
    runner.run(sqlite_sql.CREATE_VAULT_META, fetch=False)
    created_at = str(time.time_ns())
    runner.run(
        """
        INSERT OR IGNORE INTO vault_meta (key, value)
        VALUES (?, ?)
        """,
        (VAULT_CREATED_AT_KEY, created_at),
        fetch=False,
    )
    runner.run(
        """
        INSERT INTO vault_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (STATE_MAGIC_KEY, ENGRAM_STATE_MAGIC),
        fetch=False,
    )
    runner.run(
        """
        INSERT INTO vault_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (VAULT_SCHEMA_VERSION_KEY, str(CURRENT_SQLITE_SCHEMA_VERSION)),
        fetch=False,
    )


def _ensure_indexes(runner: SQLRunner) -> None:
    for statement in sqlite_sql.CREATE_INDEXES:
        runner.run(statement, fetch=False)


def _ensure_memory_id_clock(runner: SQLRunner) -> None:
    runner.run(sqlite_sql.CREATE_MEMORY_ID_CLOCK, fetch=False)
    runner.run(sqlite_sql.SEED_MEMORY_ID_CLOCK_FROM_ITEMS, fetch=False)


def _add_missing_processing_columns(runner: SQLRunner) -> None:
    columns = set(_column_names(runner, "memory_items"))
    additions = (
        ("processing_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("last_processing_error", "TEXT"),
        ("last_task_tid", "TEXT"),
        ("last_task_updated_at", "INTEGER"),
    )
    for name, definition in additions:
        if name not in columns:
            runner.run(
                f"ALTER TABLE memory_items ADD COLUMN {name} {definition}",
                fetch=False,
            )


def _ensure_memory_edges_foreign_keys(runner: SQLRunner) -> None:
    if runner.run("PRAGMA foreign_key_list(memory_edges)"):
        return
    runner.run("ALTER TABLE memory_edges RENAME TO memory_edges_old", fetch=False)
    runner.run(sqlite_sql.CREATE_MEMORY_EDGES, fetch=False)
    runner.run(
        """
        INSERT INTO memory_edges (parent_id, child_id, position)
        SELECT parent_id, child_id, position
        FROM memory_edges_old
        ORDER BY parent_id ASC, position ASC, child_id ASC
        """,
        fetch=False,
    )
    runner.run("DROP TABLE memory_edges_old", fetch=False)


def _verify_current_schema(runner: SQLRunner, *, vault_path: Path) -> None:
    table_names = _table_names(runner)
    if not _REQUIRED_TABLES.issubset(table_names):
        raise VaultNotInitializedError(str(vault_path))
    if _column_names(runner, "vault_meta") != ("key", "value"):
        raise VaultNotInitializedError(str(vault_path))
    if _column_names(runner, "memory_items") != sqlite_sql.MEMORY_ITEM_COLUMNS:
        raise VaultNotInitializedError(str(vault_path))
    if _column_names(runner, "memory_edges") != _MEMORY_EDGE_COLUMNS:
        raise VaultNotInitializedError(str(vault_path))
    if _column_names(runner, MEMORY_ID_CLOCK_TABLE) != _MEMORY_ID_CLOCK_COLUMNS:
        raise VaultNotInitializedError(str(vault_path))
    metadata = select_metadata(runner)
    if metadata.get(STATE_MAGIC_KEY) != ENGRAM_STATE_MAGIC:
        raise VaultNotInitializedError(str(vault_path))
    if metadata.get(VAULT_SCHEMA_VERSION_KEY) != str(CURRENT_SQLITE_SCHEMA_VERSION):
        raise VaultNotInitializedError(str(vault_path))
    if VAULT_CREATED_AT_KEY not in metadata:
        raise VaultNotInitializedError(str(vault_path))
    index_names = _index_names(runner)
    missing_indexes = set(sqlite_sql.REQUIRED_INDEXES) - index_names
    if missing_indexes:
        raise VaultNotInitializedError(str(vault_path))
    foreign_key_errors = runner.run("PRAGMA foreign_key_check")
    if foreign_key_errors:
        raise StoreIntegrityError("Engram state store has invalid foreign keys")
    if runner.run("SELECT id FROM memory_items WHERE id < 0 LIMIT 1"):
        raise StoreIntegrityError("Engram state store contains negative memory IDs")
    _verify_memory_id_clock(runner)


def _is_current_schema(runner: SQLRunner) -> bool:
    metadata = select_metadata(runner)
    return (
        _REQUIRED_TABLES.issubset(_table_names(runner))
        and metadata.get(STATE_MAGIC_KEY) == ENGRAM_STATE_MAGIC
        and metadata.get(VAULT_SCHEMA_VERSION_KEY) == str(CURRENT_SQLITE_SCHEMA_VERSION)
        and VAULT_CREATED_AT_KEY in metadata
        and _column_names(runner, "memory_items") == sqlite_sql.MEMORY_ITEM_COLUMNS
        and _column_names(runner, "memory_edges") == _MEMORY_EDGE_COLUMNS
        and _column_names(runner, MEMORY_ID_CLOCK_TABLE) == _MEMORY_ID_CLOCK_COLUMNS
    )


def _verify_memory_id_clock(runner: SQLRunner) -> None:
    rows = runner.run(
        f"""
        SELECT singleton, last_memory_id
        FROM {MEMORY_ID_CLOCK_TABLE}
        """
    )
    if len(rows) != 1:
        raise StoreIntegrityError("Engram state store memory ID clock is invalid")
    singleton, last_memory_id = rows[0]
    if int(singleton) != 1 or int(last_memory_id) < 0:
        raise StoreIntegrityError("Engram state store memory ID clock is invalid")
    max_rows = runner.run("SELECT COALESCE(MAX(id), 0) FROM memory_items")
    max_memory_id = int(max_rows[0][0]) if max_rows else 0
    if int(last_memory_id) < max_memory_id:
        raise StoreIntegrityError(
            "Engram state store memory ID clock is behind existing items"
        )


def _metadata_schema_version(metadata: dict[str, str]) -> int | None:
    raw = metadata.get(VAULT_SCHEMA_VERSION_KEY) or metadata.get(
        _LEGACY_SCHEMA_VERSION_KEY
    )
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise StoreVersionError(f"invalid Engram schema version: {raw!r}") from exc


def _table_names(runner: SQLRunner) -> set[str]:
    rows = runner.run(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    )
    return {str(row[0]) for row in rows}


def _column_names(runner: SQLRunner, table_name: str) -> tuple[str, ...]:
    rows = runner.run(f"PRAGMA table_info({table_name})")
    return tuple(str(row[1]) for row in rows)


def _index_names(runner: SQLRunner) -> set[str]:
    rows = runner.run(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
          AND name NOT LIKE 'sqlite_%'
        """
    )
    return {str(row[0]) for row in rows}
