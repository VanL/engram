"""SQLite SQL namespace for the Engram state store.

Spec references:
- docs/specs/10-minimum-memory-model.md [MM-13], [MM-19], [MM-20]
- docs/specs/11-minimum-write-search-context-slice.md [MWS-1], [MWS-5], [MWS-8]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-44]
"""

from __future__ import annotations

MEMORY_ITEM_COLUMNS: tuple[str, ...] = (
    "id",
    "tier",
    "text",
    "created_at",
    "access",
    "relevance",
    "indexed_at",
    "summary_terms_json",
    "processing_attempts",
    "last_processing_error",
    "last_task_tid",
    "last_task_updated_at",
)

FAILED_ITEM_COLUMNS: tuple[str, ...] = (
    "id",
    "tier",
    "text",
    "created_at",
    "indexed_at",
    "processing_attempts",
    "last_processing_error",
    "last_task_tid",
    "last_task_updated_at",
)

MEMORY_ITEM_SELECT: str = ", ".join(MEMORY_ITEM_COLUMNS)
FAILED_ITEM_SELECT: str = ", ".join(FAILED_ITEM_COLUMNS)

CREATE_VAULT_META: str = """
CREATE TABLE IF NOT EXISTS vault_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

CREATE_MEMORY_ITEMS: str = """
CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY CHECK (id >= 0),
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
)
"""

CREATE_MEMORY_EDGES: str = """
CREATE TABLE IF NOT EXISTS memory_edges (
    parent_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (parent_id, child_id),
    FOREIGN KEY(parent_id) REFERENCES memory_items(id),
    FOREIGN KEY(child_id) REFERENCES memory_items(id)
)
"""

CREATE_MEMORY_ID_CLOCK: str = """
CREATE TABLE IF NOT EXISTS memory_id_clock (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_memory_id INTEGER NOT NULL CHECK (last_memory_id >= 0)
)
"""

INIT_MEMORY_ID_CLOCK_EMPTY: str = """
INSERT OR IGNORE INTO memory_id_clock (singleton, last_memory_id)
VALUES (1, 0)
"""

SEED_MEMORY_ID_CLOCK_FROM_ITEMS: str = """
INSERT INTO memory_id_clock (singleton, last_memory_id)
VALUES (1, COALESCE((SELECT MAX(id) FROM memory_items), 0))
ON CONFLICT(singleton) DO UPDATE SET
    last_memory_id = MAX(memory_id_clock.last_memory_id, excluded.last_memory_id)
"""

CREATE_INDEXES: tuple[str, ...] = (
    """
    CREATE INDEX IF NOT EXISTS idx_memory_items_tier_created_at
    ON memory_items(tier, created_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_edges_child_id
    ON memory_edges(child_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_edges_parent_position
    ON memory_edges(parent_id, position)
    """,
)

REQUIRED_INDEXES: tuple[str, ...] = (
    "idx_memory_items_tier_created_at",
    "idx_memory_edges_child_id",
    "idx_memory_edges_parent_position",
)
