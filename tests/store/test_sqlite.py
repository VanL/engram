from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from engram._constants import (
    CURRENT_SQLITE_SCHEMA_VERSION,
    DEFAULT_SQLITE_FILENAME,
    ENGRAM_STATE_MAGIC,
    MEMORY_ID_CLOCK_TABLE,
    STATE_MAGIC_KEY,
)
from engram._exceptions import (
    InvalidStorePathError,
    StoreBackendNotSupportedError,
    StoreIntegrityError,
    StoreOperationalError,
    StoreVersionError,
    VaultNotInitializedError,
)
from engram._models import MemoryItem
from engram.store.backends.sqlite.runtime import setup_sqlite_connection_phase
from engram.store.db import SQLiteRunner, execute_with_retry
from engram.store.factory import open_state_store
from engram.store.pathing import validate_safe_path_components
from engram.store.sqlite import SQLiteStateStore


def _memory_item_columns(db_path: Path) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("PRAGMA table_info(memory_items)").fetchall()
    finally:
        connection.close()
    return [str(row[1]) for row in rows]


def _metadata(db_path: Path) -> dict[str, str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT key, value
            FROM vault_meta
            ORDER BY key ASC
            """
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]): str(row[1]) for row in rows}


def _table_names(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def _index_names(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def _memory_id_clock_row(db_path: Path) -> tuple[int, int] | None:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT singleton, last_memory_id
            FROM {MEMORY_ID_CLOCK_TABLE}
            """
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        return None
    assert len(rows) == 1
    return int(rows[0][0]), int(rows[0][1])


def _db_path(vault_path: Path) -> Path:
    return vault_path / DEFAULT_SQLITE_FILENAME


def test_sqlite_store_persists_items_and_processing_state(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    created_at = time.time_ns()
    item = MemoryItem(
        id=created_at,
        tier=0,
        text="Decision: use SQLite for local state.",
        created_at=created_at,
    )
    store.put_item(item)

    stored_item = store.get_item(item.id)
    assert stored_item is not None
    assert stored_item.text == item.text

    next_item = store.get_next_repairable_item()
    assert next_item is not None
    assert next_item.id == item.id
    assert store.count_items_needing_processing() == 1
    assert store.count_unindexed_items() == 1

    store.update_indexed_at(item.id, indexed_at=time.time_ns())
    store.record_processing_success(item.id, updated_at=time.time_ns())
    assert store.count_items_needing_processing() == 0
    assert store.count_unindexed_items() == 0
    store.close()


def test_sqlite_store_prefers_pending_items_over_failed_retries(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    base = time.time_ns()
    failed_item = MemoryItem(
        id=base,
        tier=0,
        text="Decision: failed items should not starve pending items.",
        created_at=base,
    )
    pending_item = MemoryItem(
        id=base + 1,
        tier=0,
        text="Decision: pending items should run before failed retries.",
        created_at=base + 1,
    )
    store.put_item(failed_item)
    store.record_processing_failure(
        failed_item.id,
        updated_at=base + 10,
        error="boom",
    )
    store.put_item(pending_item)

    next_item = store.get_next_repairable_item()

    assert next_item is not None
    assert next_item.id == pending_item.id
    assert store.count_failed_processing_items() == 1
    store.close()


def test_sqlite_store_creates_ordered_episode_children(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    base = time.time_ns()
    child_ids = []
    for offset, text in enumerate(
        [
            "Decision: keep SQLite authoritative.",
            "Decision: keep LanceDB for retrieval.",
            "Decision: keep record non-blocking.",
        ]
    ):
        item = MemoryItem(
            id=base + offset,
            tier=0,
            text=text,
            created_at=base + offset,
        )
        store.put_item(item)
        child_ids.append(item.id)

    episode = store.create_episode(
        text="Episode: SQLite, LanceDB, record. Key terms: sqlite, lancedb, record.",
        summary_terms=("sqlite", "lancedb", "record"),
        child_ids=child_ids,
    )
    children = store.get_children(episode.id)

    assert episode.created_at == base + 2
    assert [child.id for child in children] == child_ids
    store.close()


def test_sqlite_store_requires_initialized_vault_when_create_false(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)

    with pytest.raises(VaultNotInitializedError):
        SQLiteStateStore(vault_path, create=False)


def test_sqlite_store_opens_current_vault_when_create_false(
    vault_path: Path,
) -> None:
    store = SQLiteStateStore(vault_path)
    store.close()

    reopened = SQLiteStateStore(vault_path, create=False)

    assert reopened.get_schema_version() == CURRENT_SQLITE_SCHEMA_VERSION
    metadata = reopened.get_metadata()
    assert metadata[STATE_MAGIC_KEY] == ENGRAM_STATE_MAGIC
    assert "vault_created_at" in metadata
    assert _required_indexes_present(_db_path(vault_path))
    assert _memory_id_clock_row(_db_path(vault_path)) == (1, 0)
    reopened.close()


def test_sqlite_store_initializes_memory_id_clock(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    store.close()

    assert _memory_id_clock_row(_db_path(vault_path)) == (1, 0)


def test_sqlite_runtime_connection_phase_enables_foreign_keys(tmp_path: Path) -> None:
    runner = SQLiteRunner(tmp_path / "runtime.db")
    try:
        setup_sqlite_connection_phase(runner)

        rows = runner.run("PRAGMA foreign_keys")

        assert rows == [(1,)]
    finally:
        runner.close()


def test_sqlite_store_uses_wal_journal_mode(vault_path: Path) -> None:
    store = SQLiteStateStore(vault_path)
    store.close()
    connection = sqlite3.connect(_db_path(vault_path))
    try:
        rows = connection.execute("PRAGMA journal_mode").fetchall()
    finally:
        connection.close()

    assert str(rows[0][0]).lower() == "wal"


def test_sqlite_store_migrates_legacy_vault_without_metadata(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE memory_items (
            id INTEGER PRIMARY KEY,
            tier INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            access REAL NOT NULL,
            relevance REAL NOT NULL,
            indexed_at INTEGER,
            summary_terms_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE memory_edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id)
        );

        CREATE TABLE pending_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO memory_items (
            id, tier, text, created_at, access, relevance, indexed_at,
            summary_terms_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            0,
            "Decision: legacy vaults should migrate forward.",
            1001,
            1.0,
            1.0,
            None,
            '["legacy"]',
        ),
    )
    connection.execute(
        """
        INSERT INTO memory_items (
            id, tier, text, created_at, access, relevance, indexed_at,
            summary_terms_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            2001,
            1,
            "Episode: legacy migration summary.",
            2001,
            1.0,
            1.0,
            3001,
            '["migration"]',
        ),
    )
    connection.execute(
        """
        INSERT INTO memory_edges (parent_id, child_id, position)
        VALUES (?, ?, ?)
        """,
        (2001, 1001, 0),
    )
    connection.commit()
    connection.close()

    store = SQLiteStateStore(vault_path, create=False)

    assert store.get_schema_version() == CURRENT_SQLITE_SCHEMA_VERSION
    assert store.get_metadata()[STATE_MAGIC_KEY] == ENGRAM_STATE_MAGIC
    assert "pending_tasks" not in _table_names(db_path)
    assert "processing_attempts" in _memory_item_columns(db_path)
    assert _required_indexes_present(db_path)
    migrated_item = store.get_item(1001)
    assert migrated_item is not None
    assert migrated_item.text == "Decision: legacy vaults should migrate forward."
    assert migrated_item.summary_terms == ("legacy",)
    assert [item.id for item in store.get_children(2001)] == [1001]
    assert _memory_id_clock_row(db_path) == (1, 2001)
    store.close()


def test_sqlite_store_migrates_v3_queue_shaped_schema_on_open(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    _create_v3_queue_shaped_database(db_path, with_metadata=False)

    store = SQLiteStateStore(vault_path, create=False)

    assert store.get_schema_version() == CURRENT_SQLITE_SCHEMA_VERSION
    assert store.get_metadata()[STATE_MAGIC_KEY] == ENGRAM_STATE_MAGIC
    assert "processing_status" not in _memory_item_columns(db_path)
    assert _required_indexes_present(db_path)
    failed_items = store.list_failed_items(limit=5)
    assert len(failed_items) == 1
    assert failed_items[0].id == 1001
    assert failed_items[0].processing_attempts == 2
    assert failed_items[0].error == "boom"
    assert _memory_id_clock_row(db_path) == (1, 1001)
    store.close()


def test_sqlite_store_init_migrates_v3_queue_shaped_schema(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    _create_v3_queue_shaped_database(db_path, with_metadata=True)

    store = SQLiteStateStore(vault_path, create=True)

    assert store.get_schema_version() == CURRENT_SQLITE_SCHEMA_VERSION
    assert "processing_status" not in _memory_item_columns(db_path)
    assert store.get_item(1001) is not None
    assert _memory_id_clock_row(db_path) == (1, 1001)
    store.close()


def test_sqlite_store_migrates_pre_plan_v4_metadata(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE vault_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE memory_items (
            id INTEGER PRIMARY KEY,
            tier INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            access REAL NOT NULL,
            relevance REAL NOT NULL,
            indexed_at INTEGER,
            summary_terms_json TEXT NOT NULL DEFAULT '[]',
            processing_attempts INTEGER NOT NULL DEFAULT 0,
            last_processing_error TEXT,
            last_task_tid TEXT,
            last_task_updated_at INTEGER
        );

        CREATE TABLE memory_edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id),
            FOREIGN KEY(parent_id) REFERENCES memory_items(id),
            FOREIGN KEY(child_id) REFERENCES memory_items(id)
        );
        """
    )
    connection.execute(
        """
        INSERT INTO vault_meta (key, value)
        VALUES ('schema_version', '4'), ('vault_created_at', '1001')
        """
    )
    connection.commit()
    connection.close()

    store = SQLiteStateStore(vault_path, create=False)

    metadata = store.get_metadata()
    assert metadata["schema_version"] == str(CURRENT_SQLITE_SCHEMA_VERSION)
    assert metadata[STATE_MAGIC_KEY] == ENGRAM_STATE_MAGIC
    assert metadata["vault_created_at"] == "1001"
    assert _required_indexes_present(db_path)
    assert _memory_id_clock_row(db_path) == (1, 0)
    store.close()


def test_sqlite_store_migrates_pre_clock_schema_and_seeds_max_id(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE vault_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE memory_items (
            id INTEGER PRIMARY KEY,
            tier INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            access REAL NOT NULL,
            relevance REAL NOT NULL,
            indexed_at INTEGER,
            summary_terms_json TEXT NOT NULL DEFAULT '[]',
            processing_attempts INTEGER NOT NULL DEFAULT 0,
            last_processing_error TEXT,
            last_task_tid TEXT,
            last_task_updated_at INTEGER
        );

        CREATE TABLE memory_edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id),
            FOREIGN KEY(parent_id) REFERENCES memory_items(id),
            FOREIGN KEY(child_id) REFERENCES memory_items(id)
        );
        """
    )
    connection.execute(
        """
        INSERT INTO vault_meta (key, value)
        VALUES
            ('schema_version', '5'),
            ('state_magic', ?),
            ('vault_created_at', '1001')
        """,
        (ENGRAM_STATE_MAGIC,),
    )
    connection.execute(
        """
        INSERT INTO memory_items (
            id, tier, text, created_at, access, relevance, indexed_at,
            summary_terms_json, processing_attempts, last_processing_error,
            last_task_tid, last_task_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            9001,
            0,
            "Decision: pre-clock vaults seed the allocation clock.",
            7001,
            1.0,
            1.0,
            None,
            "[]",
            0,
            None,
            None,
            None,
        ),
    )
    connection.commit()
    connection.close()

    store = SQLiteStateStore(vault_path, create=False)

    assert store.get_schema_version() == CURRENT_SQLITE_SCHEMA_VERSION
    assert store.get_item(9001) is not None
    assert _memory_id_clock_row(db_path) == (1, 9001)
    store.close()


def test_sqlite_store_rejects_negative_memory_ids(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE vault_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE memory_items (
            id INTEGER PRIMARY KEY,
            tier INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            access REAL NOT NULL,
            relevance REAL NOT NULL,
            indexed_at INTEGER,
            summary_terms_json TEXT NOT NULL DEFAULT '[]',
            processing_attempts INTEGER NOT NULL DEFAULT 0,
            last_processing_error TEXT,
            last_task_tid TEXT,
            last_task_updated_at INTEGER
        );

        CREATE TABLE memory_edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id),
            FOREIGN KEY(parent_id) REFERENCES memory_items(id),
            FOREIGN KEY(child_id) REFERENCES memory_items(id)
        );

        CREATE TABLE memory_id_clock (
            singleton INTEGER PRIMARY KEY,
            last_memory_id INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO vault_meta (key, value)
        VALUES
            ('schema_version', ?),
            ('state_magic', ?),
            ('vault_created_at', '1001')
        """,
        (str(CURRENT_SQLITE_SCHEMA_VERSION), ENGRAM_STATE_MAGIC),
    )
    connection.execute(
        """
        INSERT INTO memory_items (
            id, tier, text, created_at, access, relevance, indexed_at,
            summary_terms_json, processing_attempts, last_processing_error,
            last_task_tid, last_task_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            -1,
            0,
            "Decision: negative IDs are corrupt.",
            1001,
            1.0,
            1.0,
            None,
            "[]",
            0,
            None,
            None,
            None,
        ),
    )
    connection.execute(
        """
        INSERT INTO memory_id_clock (singleton, last_memory_id)
        VALUES (1, 0)
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(StoreIntegrityError):
        SQLiteStateStore(vault_path, create=False)


def test_sqlite_store_rejects_wrong_magic(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    store = SQLiteStateStore(vault_path, create=True)
    store.close()
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE vault_meta SET value = ? WHERE key = ?",
        ("simplebroker", STATE_MAGIC_KEY),
    )
    connection.commit()
    connection.close()

    with pytest.raises(VaultNotInitializedError):
        SQLiteStateStore(vault_path, create=False)


def test_sqlite_store_rejects_newer_schema_version(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    store = SQLiteStateStore(vault_path, create=True)
    store.close()
    db_path = _db_path(vault_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE vault_meta SET value = ? WHERE key = 'schema_version'",
        ("999",),
    )
    connection.commit()
    connection.close()

    with pytest.raises(StoreVersionError):
        SQLiteStateStore(vault_path, create=False)


def test_sqlite_store_rejects_non_sqlite_database_file(tmp_path: Path) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir(parents=True)
    db_path = _db_path(vault_path)
    db_path.write_bytes(b"not sqlite")

    with pytest.raises(VaultNotInitializedError):
        SQLiteStateStore(vault_path, create=False)


def test_open_state_store_rejects_pg_backend_until_implemented(
    vault_path: Path,
) -> None:
    with pytest.raises(StoreBackendNotSupportedError):
        open_state_store(vault_path, create=True, backend_name="pg")


def test_validate_safe_path_components_rejects_traversal_and_metacharacters() -> None:
    validate_safe_path_components(DEFAULT_SQLITE_FILENAME)

    with pytest.raises(InvalidStorePathError):
        validate_safe_path_components("../engram.db")
    with pytest.raises(InvalidStorePathError):
        validate_safe_path_components("bad name.db")
    with pytest.raises(InvalidStorePathError):
        validate_safe_path_components("bad;name.db")


def test_execute_with_retry_retries_locked_sqlite_operation() -> None:
    attempts = 0

    def _flaky_operation() -> int:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return 42

    assert execute_with_retry(_flaky_operation, initial_delay=0, max_delay=0) == 42
    assert attempts == 3


def test_execute_with_retry_raises_after_exhaustion() -> None:
    def _locked_operation() -> None:
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(StoreOperationalError):
        execute_with_retry(
            _locked_operation,
            attempts=2,
            initial_delay=0,
            max_delay=0,
        )


def _required_indexes_present(db_path: Path) -> bool:
    return {
        "idx_memory_items_tier_created_at",
        "idx_memory_edges_child_id",
        "idx_memory_edges_parent_position",
    }.issubset(_index_names(db_path))


def _create_v3_queue_shaped_database(db_path: Path, *, with_metadata: bool) -> None:
    connection = sqlite3.connect(db_path)
    if with_metadata:
        connection.executescript(
            """
            CREATE TABLE vault_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO vault_meta (key, value)
            VALUES ('vault_schema_version', '3'), ('vault_created_at', '1001')
            """
        )
    connection.executescript(
        """
        CREATE TABLE memory_items (
            id INTEGER PRIMARY KEY,
            tier INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            access REAL NOT NULL,
            relevance REAL NOT NULL,
            indexed_at INTEGER,
            summary_terms_json TEXT NOT NULL DEFAULT '[]',
            processing_status TEXT NOT NULL DEFAULT 'completed',
            processing_attempts INTEGER NOT NULL DEFAULT 0,
            last_processing_error TEXT,
            last_task_tid TEXT,
            last_task_updated_at INTEGER
        );

        CREATE TABLE memory_edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id),
            FOREIGN KEY(parent_id) REFERENCES memory_items(id),
            FOREIGN KEY(child_id) REFERENCES memory_items(id)
        );
        """
    )
    connection.execute(
        """
        INSERT INTO memory_items (
            id,
            tier,
            text,
            created_at,
            access,
            relevance,
            indexed_at,
            summary_terms_json,
            processing_status,
            processing_attempts,
            last_processing_error,
            last_task_tid,
            last_task_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            0,
            "Decision: v3 vaults should migrate forward.",
            1001,
            1.0,
            1.0,
            None,
            "[]",
            "failed",
            2,
            "boom",
            "task-123",
            2002,
        ),
    )
    connection.commit()
    connection.close()
