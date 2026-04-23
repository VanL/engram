"""Engram constants, defaults, and environment variable loading.

All constants and configuration for the engram memory system live here.
Grouped by purpose. Environment variables are resolved in load_config().

Spec references: (specs not yet written -- will be added as they appear)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

__version__: Final[str] = "0.5.1"
PROG_NAME: Final[str] = "engram"


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS: Final[int] = 0
EXIT_ERROR: Final[int] = 1
EXIT_NOT_FOUND: Final[int] = 2


# ---------------------------------------------------------------------------
# Tier system
# ---------------------------------------------------------------------------

TIER_MOMENT: Final[int] = 0
"""Tier 0: raw unit of experience -- timestamp + text."""

TIER_EPISODE: Final[int] = 1
"""Tier 1: LLM-generated summary of a semantically coherent moment sequence."""

TIER_ARC: Final[int] = 2
"""Tier 2: summary-of-summaries spanning multiple episodes."""

TIER_NAMES: Final[dict[int, str]] = {
    TIER_MOMENT: "moment",
    TIER_EPISODE: "episode",
    TIER_ARC: "arc",
}
"""Human-readable names for built-in tiers.  Tiers above 2 are extensible;
higher tiers use 'epoch', or fall back to 'tier-{n}'."""

MAX_BUILTIN_TIER: Final[int] = 2
"""Highest tier with a built-in name.  The system supports arbitrary depth."""

RECALL_SCOPE_ITEM: Final[str] = "item"
"""Recall scope for exact memory item recall."""

RECALL_SCOPE_EPISODE: Final[str] = "episode"
"""Recall scope for the episode containing an anchor MID."""

RECALL_SCOPE_ARC: Final[str] = "arc"
"""Recall scope for the arc containing an anchor MID."""

RECALL_SCOPE_TIERS: Final[dict[str, int]] = {
    RECALL_SCOPE_EPISODE: TIER_EPISODE,
    RECALL_SCOPE_ARC: TIER_ARC,
}
"""Named summary recall scopes mapped to their target tier depth."""


def tier_name(depth: int) -> str:
    """Return the human-readable name for a tier depth.

    Built-in tiers (0-2) return their canonical names.  Tier 3 returns
    'epoch'.  Higher tiers return 'tier-{n}'.
    """
    if depth in TIER_NAMES:
        return TIER_NAMES[depth]
    if depth == 3:
        return "epoch"
    return f"tier-{depth}"


def normalize_recall_scope(scope: str | int) -> str | int:
    """Return the canonical recall scope.

    Exact item recall stays on the string scope `"item"`. Summary recall scopes
    normalize to a positive integer tier depth.
    """

    if isinstance(scope, bool):
        raise ValueError(
            "recall scope must be 'item', a named tier, or an integer tier"
        )
    if isinstance(scope, int):
        if scope < 1:
            raise ValueError("integer recall scope must be at least 1")
        return scope

    normalized = scope.strip().lower()
    if normalized == RECALL_SCOPE_ITEM:
        return RECALL_SCOPE_ITEM
    if normalized in RECALL_SCOPE_TIERS:
        return RECALL_SCOPE_TIERS[normalized]
    try:
        parsed_tier = int(normalized)
    except ValueError as exc:
        raise ValueError(
            f"invalid recall scope: {scope!r}; use 'item', a named tier, or an integer tier"
        ) from exc
    if parsed_tier < 1:
        raise ValueError("integer recall scope must be at least 1")
    return parsed_tier


def recall_scope_tier(scope: str | int) -> int | None:
    """Return the target tier for a recall scope, or `None` for exact item recall."""

    normalized = normalize_recall_scope(scope)
    if normalized == RECALL_SCOPE_ITEM:
        return None
    return int(normalized)


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

TID_LENGTH: Final[int] = 19
"""Expected display length for current `time.time_ns()`-compatible memory IDs."""

MEMORY_ID_LOGICAL_COUNTER_BITS: Final[int] = 12
"""Low-order timestamp bits reserved for the per-time-slice logical counter.
Most clocks expose coarser-than-nanosecond precision, so these bits are usually
zero or low-signal physical time."""

MEMORY_ID_LOGICAL_COUNTER_MASK: Final[int] = (1 << MEMORY_ID_LOGICAL_COUNTER_BITS) - 1
"""Bit mask for the logical counter portion of a memory ID."""

MEMORY_ID_MAX_LOGICAL_COUNTER: Final[int] = 1 << MEMORY_ID_LOGICAL_COUNTER_BITS
"""Exclusive upper bound for logical counter values."""

MEMORY_ID_WAIT_FOR_NEXT_INCREMENT: Final[float] = 0.000_001
"""Maximum sleep interval while waiting for the physical clock to advance."""

MEMORY_ID_MAX_WAIT_ITERATIONS: Final[int] = 100_000
"""Maximum wait iterations before memory ID generation fails clearly."""

SQLITE_MAX_INT64: Final[int] = 2**63
"""Exclusive upper bound for SQLite signed 64-bit integer storage."""


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL: Final[str] = "sentence-transformers/all-MiniLM-L6-v2"
"""Default sentence-transformers model for vector embeddings.
Compact, widely available, and works without model-specific extra packages."""

DEFAULT_EMBEDDING_DIM: Final[int] = 384
"""Default embedding dimensionality. Matches all-MiniLM-L6-v2."""

DEFAULT_SUMMARIZER_MODEL: Final[str] = "gemini/gemini-3.1-flash-lite-preview"
"""Default model for summary and keyword extraction tasks."""

EMBEDDING_SEARCH_PREFIX: Final[str] = "search_query: "
"""Prefix prepended to query text before embedding (nomic convention)."""

EMBEDDING_DOCUMENT_PREFIX: Final[str] = "search_document: "
"""Prefix prepended to document text before embedding (nomic convention)."""


# ---------------------------------------------------------------------------
# Coalescing
# ---------------------------------------------------------------------------

COALESCE_SIMILARITY_THRESHOLD: Final[float] = 0.65
"""Cosine similarity to running centroid below which an episode boundary
is detected.  Lower = fewer, larger episodes.  Higher = more, smaller.
This is the semantic boundary trigger."""

COALESCE_MAX_WINDOW: Final[int] = 20
"""Maximum number of items in a coalescing window before forcing a boundary,
regardless of semantic similarity.  Acts as a ceiling."""

COALESCE_MIN_WINDOW: Final[int] = 3
"""Minimum items before a semantic boundary can trigger.  Prevents
single-item episodes from noise."""

COALESCE_CHECK_INTERVAL: Final[int] = 5
"""Check for coalescing opportunity every N new moments.  Not every moment
triggers a coalescing check -- this amortizes the cost."""

DEFAULT_COALESCE_TIERS: Final[int] = 2
"""Number of coalesced tiers above moments to maintain.  Can be increased
via configuration."""


# ---------------------------------------------------------------------------
# Access scoring and decay
# ---------------------------------------------------------------------------

DEFAULT_IMPORTANCE: Final[int] = 1
"""Default write-time importance. Maps to relevance 1.0."""

DEFAULT_ACCESS_SCORE: Final[float] = 1.0
"""Initial access score for a new item."""

DEFAULT_RELEVANCE_FLOOR: Final[float] = 1.0
"""Default relevance multiplier. Items with relevance > 1.0 have higher
stored importance. Score = access * relevance."""

BLOB_RELEVANCE_FLOOR: Final[float] = 2.0
"""Default relevance floor for blob-backed moments.  Explicit attachment
is a stronger importance signal than conversation flow."""

DECAY_FACTOR: Final[float] = 0.95
"""Multiplicative decay applied to access scores periodically.
0.95 means 5% decay per sweep.  After 20 sweeps, score is ~36% of peak."""

DECAY_FLOOR: Final[float] = 0.1
"""Minimum access score after decay.  Prevents items from decaying to zero.
Structurally important items should use the importance multiplier, but this
provides a safety net for everything."""

DECAY_INTERVAL: Final[int] = 50
"""Run a decay sweep every N new moments stored.  Balances freshness
against sweep cost."""


# ---------------------------------------------------------------------------
# Context assembly budgets (fraction of total context window)
# ---------------------------------------------------------------------------

CONTEXT_BUDGET_IMMEDIATE: Final[float] = 0.40
"""Fraction of context window for recent moments (verbatim)."""

CONTEXT_BUDGET_SHORT_TERM: Final[float] = 0.25
"""Fraction of context window for recent episodes."""

CONTEXT_BUDGET_MEDIUM_TERM: Final[float] = 0.20
"""Fraction of context window for relevant arcs."""

CONTEXT_BUDGET_LONG_TERM: Final[float] = 0.15
"""Fraction of context window for high-importance retained items."""

DEFAULT_CONTEXT_TOKENS: Final[int] = 8192
"""Default total context budget in tokens.  The agent's actual context
window is larger; this is the memory portion."""


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

DEFAULT_SEARCH_LIMIT: Final[int] = 20
"""Default number of results returned by hybrid search."""

DEFAULT_RRF_K: Final[int] = 60
"""Reciprocal Rank Fusion constant.  Higher k reduces the impact of
individual ranking position.  60 is the standard default from the
RRF paper (Cormack et al. 2009)."""


# ---------------------------------------------------------------------------
# Distinctive term extraction (for coalescing prompts)
# ---------------------------------------------------------------------------

TERM_EXTRACTION_TOP_K: Final[int] = 8
"""Number of distinctive terms to extract from a coalescing window.
These terms are included in the summarization prompt to anchor the
LLM on specific vocabulary.

Early on (small corpus), the LLM suggests terms directly -- TF-IDF needs
meaningful document frequencies to be useful.  As the corpus grows, TF-IDF
can supplement the LLM as an additional signal."""

TFIDF_MINIMUM_CORPUS_SIZE: Final[int] = 100
"""Minimum number of indexed items before TF-IDF term extraction is
used as a supplementary signal alongside LLM-suggested terms.  Below
this threshold, IDF scores are too noisy to be useful."""

SUMMARY_AGENT_TIMEOUT_SECONDS: Final[float] = 45.0
"""Per-window timeout for LLM-backed summary extraction."""

SUMMARY_AGENT_MAX_OUTPUT_TOKENS: Final[int] = 384
"""Maximum model output tokens for summary extraction tasks."""

SUMMARY_AGENT_MAX_TURNS: Final[int] = 2
"""Maximum llm conversation turns for summary extraction tasks.

The llm backend needs a chain limit above one even for a single no-tool model
response. Keep this low so summary extraction remains a one-shot operation."""


# ---------------------------------------------------------------------------
# Tags / associative links
# ---------------------------------------------------------------------------

MAX_TAGS_PER_ITEM: Final[int] = 10
"""Maximum tags per moment/episode/arc.  Keeps the tag space manageable."""

TAG_HINDSIGHT_INTERVAL: Final[int] = 100
"""Re-evaluate tags with hindsight every N moments.  Only items that
appeared in recent retrieval results are re-tagged, not the full corpus."""


# ---------------------------------------------------------------------------
# Blob handling
# ---------------------------------------------------------------------------

BLOB_SUMMARY_MAX_TOKENS: Final[int] = 256
"""Maximum tokens for an LLM-generated blob summary."""


# ---------------------------------------------------------------------------
# Vault and storage paths
# ---------------------------------------------------------------------------

DEFAULT_VAULT_DIR_NAME: Final[str] = ".engram"
"""Default vault directory name, created in the current project directory.
A vault is an isolated memory namespace with its own state store and
retrieval index.  Project-scoped (like .weft/, .git/)."""

DEFAULT_SQLITE_FILENAME: Final[str] = "engram.db"
"""SQLite database filename within the vault directory."""

DEFAULT_LANCE_DIR_NAME: Final[str] = "lance"
"""LanceDB directory name within the vault directory."""

LANCE_TABLE_NAME: Final[str] = "memories"
"""LanceDB table name for the retrieval index."""

CURRENT_SQLITE_SCHEMA_VERSION: Final[int] = 6
"""Current SQLite schema version for local vaults.

Version 6 adds the `memory_id_clock` allocation table. Version 5 added explicit
Engram state-store magic and state-store indexes. Known older Engram
development vault shapes are migrated forward in place on open; unknown,
corrupted, wrong-store, or newer vaults are rejected clearly.
"""

MEMORY_ID_CLOCK_TABLE: Final[str] = "memory_id_clock"
"""SQLite table that stores the last allocated hybrid memory ID."""

VAULT_CREATED_AT_KEY: Final[str] = "vault_created_at"
"""Metadata key storing the vault creation timestamp in nanoseconds."""

VAULT_SCHEMA_VERSION_KEY: Final[str] = "schema_version"
"""Metadata key storing the current vault schema version."""

STATE_MAGIC_KEY: Final[str] = "state_magic"
"""Metadata key storing the state-store identity marker."""

ENGRAM_STATE_MAGIC: Final[str] = "engram-state-v1"
"""State-store identity marker for Engram SQLite/PG vault metadata."""

MIN_SQLITE_VERSION: Final[tuple[int, int, int]] = (3, 35, 0)
"""Minimum SQLite runtime version.

Engram requires `ALTER TABLE DROP COLUMN` for known development-vault
migrations and follows the same conservative version floor as simplebroker.
"""

SQLITE_BUSY_TIMEOUT_MS: Final[int] = 5000
"""SQLite busy timeout in milliseconds for local state-store operations."""

SQLITE_WAL_AUTOCHECKPOINT: Final[int] = 1000
"""SQLite WAL autocheckpoint page threshold for Engram state stores."""


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

ENV_VAULT_DIR: Final[str] = "ENGRAM_VAULT"
"""Override the vault directory path."""

ENV_BACKEND: Final[str] = "ENGRAM_BACKEND"
"""State store backend: 'sqlite' (default) or 'pg'."""

ENV_PG_DSN: Final[str] = "ENGRAM_PG_DSN"
"""PostgreSQL connection string when backend is 'pg'."""

ENV_EMBEDDING_MODEL: Final[str] = "ENGRAM_EMBEDDING_MODEL"
"""Override the default embedding model."""

ENV_SUMMARIZER_MODEL: Final[str] = "ENGRAM_SUMMARIZER_MODEL"
"""Override the default summary-extraction model."""

ENV_DEBUG: Final[str] = "ENGRAM_DEBUG"
"""Enable debug logging."""

ENV_WEFT_DEBUG: Final[str] = "ENGRAM_WEFT_DEBUG"
"""Override embedded Weft debug logging."""

ENV_WEFT_LOGGING_ENABLED: Final[str] = "ENGRAM_LOGGING_ENABLED"
"""Override embedded Weft logging enablement."""

ENV_WEFT_REDACT_TASKSPEC_FIELDS: Final[str] = "ENGRAM_REDACT_TASKSPEC_FIELDS"
"""Override embedded Weft TaskSpec redaction settings."""

ENV_WEFT_DIRECTORY_NAME: Final[str] = "ENGRAM_DIRECTORY_NAME"
"""Override embedded Weft metadata directory name.

Mirrored for completeness. The embedded vault path still wins when Engram builds
its runtime config.
"""

ENV_WEFT_MANAGER_LIFETIME_TIMEOUT: Final[str] = "ENGRAM_MANAGER_LIFETIME_TIMEOUT"
"""Override the embedded Weft manager idle lifetime timeout."""

ENV_WEFT_MANAGER_REUSE_ENABLED: Final[str] = "ENGRAM_MANAGER_REUSE_ENABLED"
"""Override embedded Weft manager reuse behavior."""

ENV_WEFT_AUTOSTART_TASKS: Final[str] = "ENGRAM_AUTOSTART_TASKS"
"""Override embedded Weft auto-start behavior."""

ENV_WEFT_BUSY_TIMEOUT: Final[str] = "ENGRAM_BUSY_TIMEOUT"
ENV_WEFT_CACHE_MB: Final[str] = "ENGRAM_CACHE_MB"
ENV_WEFT_SYNC_MODE: Final[str] = "ENGRAM_SYNC_MODE"
ENV_WEFT_WAL_AUTOCHECKPOINT: Final[str] = "ENGRAM_WAL_AUTOCHECKPOINT"
ENV_WEFT_MAX_MESSAGE_SIZE: Final[str] = "ENGRAM_MAX_MESSAGE_SIZE"
ENV_WEFT_READ_COMMIT_INTERVAL: Final[str] = "ENGRAM_READ_COMMIT_INTERVAL"
ENV_WEFT_GENERATOR_BATCH_SIZE: Final[str] = "ENGRAM_GENERATOR_BATCH_SIZE"
ENV_WEFT_AUTO_VACUUM: Final[str] = "ENGRAM_AUTO_VACUUM"
ENV_WEFT_AUTO_VACUUM_INTERVAL: Final[str] = "ENGRAM_AUTO_VACUUM_INTERVAL"
ENV_WEFT_VACUUM_THRESHOLD: Final[str] = "ENGRAM_VACUUM_THRESHOLD"
ENV_WEFT_VACUUM_BATCH_SIZE: Final[str] = "ENGRAM_VACUUM_BATCH_SIZE"
ENV_WEFT_VACUUM_LOCK_TIMEOUT: Final[str] = "ENGRAM_VACUUM_LOCK_TIMEOUT"
ENV_WEFT_SKIP_IDLE_CHECK: Final[str] = "ENGRAM_SKIP_IDLE_CHECK"
ENV_WEFT_JITTER_FACTOR: Final[str] = "ENGRAM_JITTER_FACTOR"
ENV_WEFT_INITIAL_CHECKS: Final[str] = "ENGRAM_INITIAL_CHECKS"
ENV_WEFT_MAX_INTERVAL: Final[str] = "ENGRAM_MAX_INTERVAL"
ENV_WEFT_BURST_SLEEP: Final[str] = "ENGRAM_BURST_SLEEP"
ENV_WEFT_DEFAULT_DB_LOCATION: Final[str] = "ENGRAM_DEFAULT_DB_LOCATION"
ENV_WEFT_DEFAULT_DB_NAME: Final[str] = "ENGRAM_DEFAULT_DB_NAME"
ENV_WEFT_PROJECT_SCOPE: Final[str] = "ENGRAM_PROJECT_SCOPE"
ENV_WEFT_BACKEND: Final[str] = "ENGRAM_WEFT_BACKEND"
ENV_WEFT_BACKEND_HOST: Final[str] = "ENGRAM_BACKEND_HOST"
ENV_WEFT_BACKEND_PORT: Final[str] = "ENGRAM_BACKEND_PORT"
ENV_WEFT_BACKEND_USER: Final[str] = "ENGRAM_BACKEND_USER"
ENV_WEFT_BACKEND_PASSWORD: Final[str] = "ENGRAM_BACKEND_PASSWORD"
ENV_WEFT_BACKEND_DATABASE: Final[str] = "ENGRAM_BACKEND_DATABASE"
ENV_WEFT_BACKEND_SCHEMA: Final[str] = "ENGRAM_BACKEND_SCHEMA"
ENV_WEFT_BACKEND_TARGET: Final[str] = "ENGRAM_BACKEND_TARGET"

EMBEDDED_WEFT_ENV_MAPPING: Final[dict[str, str]] = {
    ENV_WEFT_DEBUG: "WEFT_DEBUG",
    ENV_WEFT_LOGGING_ENABLED: "WEFT_LOGGING_ENABLED",
    ENV_WEFT_REDACT_TASKSPEC_FIELDS: "WEFT_REDACT_TASKSPEC_FIELDS",
    ENV_WEFT_DIRECTORY_NAME: "WEFT_DIRECTORY_NAME",
    ENV_WEFT_MANAGER_LIFETIME_TIMEOUT: "WEFT_MANAGER_LIFETIME_TIMEOUT",
    ENV_WEFT_MANAGER_REUSE_ENABLED: "WEFT_MANAGER_REUSE_ENABLED",
    ENV_WEFT_AUTOSTART_TASKS: "WEFT_AUTOSTART_TASKS",
    ENV_WEFT_BUSY_TIMEOUT: "WEFT_BUSY_TIMEOUT",
    ENV_WEFT_CACHE_MB: "WEFT_CACHE_MB",
    ENV_WEFT_SYNC_MODE: "WEFT_SYNC_MODE",
    ENV_WEFT_WAL_AUTOCHECKPOINT: "WEFT_WAL_AUTOCHECKPOINT",
    ENV_WEFT_MAX_MESSAGE_SIZE: "WEFT_MAX_MESSAGE_SIZE",
    ENV_WEFT_READ_COMMIT_INTERVAL: "WEFT_READ_COMMIT_INTERVAL",
    ENV_WEFT_GENERATOR_BATCH_SIZE: "WEFT_GENERATOR_BATCH_SIZE",
    ENV_WEFT_AUTO_VACUUM: "WEFT_AUTO_VACUUM",
    ENV_WEFT_AUTO_VACUUM_INTERVAL: "WEFT_AUTO_VACUUM_INTERVAL",
    ENV_WEFT_VACUUM_THRESHOLD: "WEFT_VACUUM_THRESHOLD",
    ENV_WEFT_VACUUM_BATCH_SIZE: "WEFT_VACUUM_BATCH_SIZE",
    ENV_WEFT_VACUUM_LOCK_TIMEOUT: "WEFT_VACUUM_LOCK_TIMEOUT",
    ENV_WEFT_SKIP_IDLE_CHECK: "WEFT_SKIP_IDLE_CHECK",
    ENV_WEFT_JITTER_FACTOR: "WEFT_JITTER_FACTOR",
    ENV_WEFT_INITIAL_CHECKS: "WEFT_INITIAL_CHECKS",
    ENV_WEFT_MAX_INTERVAL: "WEFT_MAX_INTERVAL",
    ENV_WEFT_BURST_SLEEP: "WEFT_BURST_SLEEP",
    ENV_WEFT_DEFAULT_DB_LOCATION: "WEFT_DEFAULT_DB_LOCATION",
    ENV_WEFT_DEFAULT_DB_NAME: "WEFT_DEFAULT_DB_NAME",
    ENV_WEFT_PROJECT_SCOPE: "WEFT_PROJECT_SCOPE",
    ENV_WEFT_BACKEND: "WEFT_BACKEND",
    ENV_WEFT_BACKEND_HOST: "WEFT_BACKEND_HOST",
    ENV_WEFT_BACKEND_PORT: "WEFT_BACKEND_PORT",
    ENV_WEFT_BACKEND_USER: "WEFT_BACKEND_USER",
    ENV_WEFT_BACKEND_PASSWORD: "WEFT_BACKEND_PASSWORD",
    ENV_WEFT_BACKEND_DATABASE: "WEFT_BACKEND_DATABASE",
    ENV_WEFT_BACKEND_SCHEMA: "WEFT_BACKEND_SCHEMA",
    ENV_WEFT_BACKEND_TARGET: "WEFT_BACKEND_TARGET",
}
"""Embedded-Weft environment surface for Engram.

Engram uses plain `ENGRAM_*` names where they do not collide with Engram's own
app-level env surface, and keeps `ENGRAM_WEFT_*` only for conflicting names
such as `BACKEND` and `DEBUG`. The selected vault path still wins for the
embedded metadata directory name and default sqlite broker path.
"""


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load configuration from environment variables.

    Environment Variables:
        ENGRAM_VAULT: Override vault directory (default: ~/.engram)
        ENGRAM_BACKEND: State store backend, 'sqlite' or 'pg' (default: sqlite)
        ENGRAM_PG_DSN: PostgreSQL DSN when backend is 'pg'
        ENGRAM_EMBEDDING_MODEL: Override embedding model
        ENGRAM_SUMMARIZER_MODEL: Override summary model
        ENGRAM_DEBUG: Enable debug logging (1/true)

    Returns:
        Configuration dictionary with resolved values.
    """
    vault_dir = os.environ.get(ENV_VAULT_DIR, str(Path.cwd() / DEFAULT_VAULT_DIR_NAME))

    return {
        "vault_dir": vault_dir,
        "backend": os.environ.get(ENV_BACKEND, "sqlite").lower(),
        "pg_dsn": os.environ.get(ENV_PG_DSN, ""),
        "sqlite_path": str(Path(vault_dir) / DEFAULT_SQLITE_FILENAME),
        "lance_dir": str(Path(vault_dir) / DEFAULT_LANCE_DIR_NAME),
        "embedding_model": os.environ.get(ENV_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL),
        "summarizer_model": os.environ.get(
            ENV_SUMMARIZER_MODEL, DEFAULT_SUMMARIZER_MODEL
        ),
        "debug": os.environ.get(ENV_DEBUG, "").lower() in ("1", "true"),
    }


def _translate_embedded_weft_env_vars() -> dict[str, str]:
    """Translate Engram-owned embedded-Weft env vars to raw WEFT_* overrides."""

    translated: dict[str, str] = {}
    for engram_key, weft_key in EMBEDDED_WEFT_ENV_MAPPING.items():
        value = os.environ.get(engram_key)
        if value is not None:
            translated[weft_key] = value
    return translated


def load_embedded_weft_overrides(vault_path: str | Path) -> dict[str, Any]:
    """Return WEFT_* overrides Engram should apply for one vault.

    The vault path is authoritative for the embedded Weft metadata directory and
    default sqlite broker path, even if matching Engram env overrides are set.
    """

    resolved_vault_path = Path(vault_path).expanduser().resolve()
    overrides: dict[str, Any] = _translate_embedded_weft_env_vars()
    overrides["WEFT_DIRECTORY_NAME"] = resolved_vault_path.name
    overrides["WEFT_DEFAULT_DB_LOCATION"] = ""
    overrides["WEFT_DEFAULT_DB_NAME"] = f"{resolved_vault_path.name}/broker.db"
    return overrides


def load_embedded_weft_config(vault_path: str | Path) -> dict[str, Any]:
    """Return canonical embedded-Weft config for one Engram vault."""

    from weft._constants import (
        load_config as load_weft_config,
    )

    resolved_vault_path = Path(vault_path).expanduser().resolve()
    overrides = load_embedded_weft_overrides(resolved_vault_path)
    return load_weft_config(overrides)
