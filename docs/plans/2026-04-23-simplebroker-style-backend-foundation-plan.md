# 2026-04-23 Simplebroker-Style Backend Foundation Plan

Status: Proposed

## 1. Goal

Rebuild Engram's state-store foundation around a simplebroker-style database
layer: a small `SQLRunner` abstraction, backend-owned schema bootstrap and
forward migrations, defensive SQLite opening, SQLite lock retry handling, path
hardening, explicit metadata and magic validation, and a store core that can be
used by SQLite now and Postgres later. The intent is to port simplebroker's
battle-tested ideas and selected code structure into Engram's domain, not to
copy queue-specific code or force simplebroker's product model onto Engram.

This plan is a foundation change. It should not add new memory features,
change retrieval semantics, change Weft ownership, or implement a production
Postgres backend. It should make the Postgres backend straightforward to add
later using the same runner/backend/schema pattern.

## 2. Source Documents

Source specs that currently govern Engram state storage:

- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-3], [MM-4],
  [MM-5], [MM-6], [MM-7], [MM-12], [MM-13], [MM-15], [MM-19],
  [MM-20], [MM-21], [MM-25], [MM-26]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1],
  [MWS-2], [MWS-3], [MWS-8], [MWS-9], [MWS-18], [MWS-19],
  [MWS-20], [MWS-21], [MWS-22], [MWS-30], [MWS-31]
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-2], [LAS-3],
  [LAS-4], [LAS-5], [LAS-6], [LAS-7], [LAS-9], [LAS-22],
  [LAS-24], [LAS-26], [LAS-27], [LAS-28]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1],
  [FCI-2], [FCI-21], [FCI-32], [FCI-35], [FCI-36], [FCI-38],
  [FCI-39], [FCI-44]

Important spec conflict to resolve before code:

- `docs/specs/12-local-app-surface.md` [LAS-4] says legacy vault shapes fail
  open clearly and that Engram does not keep backwards-compatible migration
  paths in this slice.
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-44] says SQLite
  schema changes must reject older shapes clearly and must not add schema
  rewrite or metadata backfill paths.
- This plan intentionally replaces that policy with explicit, ordered,
  forward-only migrations for known Engram schema versions. The spec update is
  part of the work, not optional cleanup.

Repository workflow and style guidance:

- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/lessons.md`

Simplebroker reference material. These are read-only calibration sources.
Port concepts and code shape where they fit Engram; do not import private
simplebroker modules from Engram.

- `../simplebroker/simplebroker/_runner.py`
  - `SQLRunner`, `SQLiteRunner`, setup phases, fork detection,
    thread-local SQLite connections, explicit transaction control, exception
    translation, cross-thread cleanup.
- `../simplebroker/simplebroker/helpers.py`
  - `_execute_with_retry`, `interruptible_sleep`, filesystem helpers, path
    validation patterns.
- `../simplebroker/simplebroker/_constants.py`
  - magic string, schema version, setup phases, safe path component validation.
- `../simplebroker/simplebroker/_backends/sqlite/runtime.py`
  - SQLite version check, defensive opening, WAL setup, busy timeout,
    connection PRAGMAs.
- `../simplebroker/simplebroker/_backends/sqlite/validation.py`
  - SQLite file header validation, read-only open validation, magic checking.
- `../simplebroker/simplebroker/_backends/sqlite/schema.py`
  - backend-owned schema initialization and ordered migrations.
- `../simplebroker/simplebroker/_backends/sqlite/plugin.py`
  - backend adapter methods for meta reads/writes and migrations.
- `../simplebroker/simplebroker/_backend_plugins.py`
  - plugin protocol and resolver pattern. Engram should adapt this to an
    internal backend registry, not copy entry-point plugin discovery yet.
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/runner.py`
  - Postgres runner pattern, SQL placeholder adaptation, transaction control,
    typed error translation, schema bootstrap cache.
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/schema.py`
  - Postgres typed singleton meta row, schema bootstrap, forward migrations.
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/plugin.py`
  - PG backend adapter shape, meta caching hooks, schema-scoped target handling.
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/_sql.py`
  - backend-specific SQL namespace with the same high-level operations expressed
    in a different dialect.

Simplebroker tests to port or adapt. These are part of the source material,
not optional inspiration:

- `../simplebroker/tests/test_runner_validation.py`
  - Port invalid-file, empty-file, nonexistent-file, and corrupted-header cases
    into Engram SQLite validation/runner tests.
- `../simplebroker/tests/test_pragma_settings.py`
  - Port applicable WAL, busy timeout, and connection PRAGMA assertions.
- `../simplebroker/tests/test_path_security.py`
  - Port safe path component validation tests, adapted so absolute Engram vault
    paths remain valid.
- `../simplebroker/tests/test_message_claim.py`
  - Port the schema migration add-column/idempotence test pattern, adapted to
    Engram's memory schema and `processing_status` removal.
- `../simplebroker/tests/test_edge_cases.py`
  - Port the concurrent schema migration test pattern, adapted to opening an
    old Engram vault from multiple processes.
- `../simplebroker/tests/test_backend_plugin_resolution.py`
  - Adapt the backend contract checks to Engram's smaller internal
    `StateBackend` protocol. Do not port entry-point discovery tests because
    external backend plugins are out of scope.
- `../simplebroker/extensions/simplebroker_pg/tests/test_pg_ownership.py`
  - Do not port as an executable PG test in this plan. Use it as design
    calibration for the future PG typed singleton meta row.

## 3. Audience Assumptions

Assume the implementer is a skilled developer with zero Engram context and
questionable taste. Assume they will:

- add abstractions because they feel elegant unless this plan says no
- mock the database rather than test real persistence unless this plan forbids it
- copy simplebroker queue-specific code unless this plan names the Engram shape
- add Postgres prematurely unless this plan says where the seam ends
- change public CLI or client shapes unless this plan names compatibility gates
- treat docs as cleanup unless docs are listed as required files to touch
- write `SELECT *` because it works locally unless this plan bans it
- leave old constants and aliases behind unless this plan says to move users
  to the canonical name in the same change

Follow this plan literally. If the implementation starts moving materially
away from "port simplebroker's backend foundation into Engram's state store,"
stop and re-plan. Do not turn this into an ORM migration, SQLAlchemy adoption,
hosted Postgres product work, retrieval redesign, or Weft execution change.

## 4. Current Context And Key Files

Read these before editing. Do not infer behavior from filenames.

### Engram Storage Today

- `engram/store/sqlite.py`
  - Current SQLite state store.
  - Opens `engram.db` directly with `sqlite3.connect`.
  - Sets `PRAGMA foreign_keys = ON`.
  - Owns schema creation in `_initialize_schema()`.
  - Owns metadata in `_ensure_metadata()`.
  - Uses `_has_current_schema()` to reject non-current shapes.
  - Uses direct `sqlite3.Row` access and many raw SQL strings inline.
  - Uses `SELECT *` in several places.
  - Has no runner, backend adapter, retry helper, defensive file validation,
    magic string, WAL setup, or ordered migration layer.

- `engram/store/base.py`
  - Current `StateStore` protocol for memory operations.
  - This protocol should remain the domain contract that `Engram` relies on.
  - It should not grow SQL-runner details; those belong below the store
    boundary.

- `engram/core/memory.py`
  - Constructs `SQLiteStateStore` directly at line-level context around
    `self._store = SQLiteStateStore(...)`.
  - Status reports `sqlite_path` from `self._store.db_path`.
  - This plan should reduce direct SQLite coupling by adding an internal store
    factory, while keeping the current local app behavior SQLite-backed.

- `engram/_constants.py`
  - Holds `CURRENT_SQLITE_SCHEMA_VERSION = 4`.
  - Holds `VAULT_CREATED_AT_KEY = "vault_created_at"`.
  - Holds `VAULT_SCHEMA_VERSION_KEY = "schema_version"`.
  - Contains a stale docstring saying earlier development vaults are rewritten
    in place on open. Current code rejects old shapes. This must be corrected
    while implementing real migrations.
  - Holds `ENV_BACKEND = "ENGRAM_BACKEND"` and `ENV_PG_DSN = "ENGRAM_PG_DSN"`,
    but the runtime does not yet use these for state-store construction.

- `engram/_exceptions.py`
  - Has public Engram errors.
  - Does not yet have store-level translated database errors such as
    `StoreOperationalError`, `StoreIntegrityError`, or `StoreVersionError`.

- `tests/store/test_sqlite.py`
  - Current SQLite store tests.
  - Verifies current metadata and rejection of legacy shapes.
  - Several tests must change from "reject old shape" to "migrate known old
    shape and preserve data."

### Current Schema Shape

Current SQLite schema is:

```text
vault_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
)

memory_items(
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
)

memory_edges(
  parent_id INTEGER NOT NULL,
  child_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  PRIMARY KEY (parent_id, child_id),
  FOREIGN KEY(parent_id) REFERENCES memory_items(id),
  FOREIGN KEY(child_id) REFERENCES memory_items(id)
)
```

Known old development shapes visible in tests:

- Current pre-plan v4 shape with `vault_meta`, `schema_version`, and
  `vault_created_at`, but without `state_magic` and without the new store
  indexes. This must migrate to the new current schema.
- Legacy shape without `vault_meta`, with `memory_items`, `memory_edges`, and
  old `pending_tasks`.
- Queue-shaped v3 `memory_items` with `processing_status` plus processing
  attempt and task columns.
- Metadata key drift in tests: some fixtures use `vault_schema_version`, while
  current code uses `schema_version`. Treat this as a historical fixture shape
  to detect intentionally; do not leave both keys as a new canonical contract.

### Simplebroker Shape To Port

Simplebroker's relevant pattern is:

```text
Domain core
  -> SQLRunner protocol
  -> backend adapter
  -> backend SQL namespace
  -> backend schema/runtime/validation helpers
```

Engram should adapt that to:

```text
Engram domain object
  -> StateStore protocol
  -> StateStoreCore using SQLRunner and StateBackend
  -> SQLiteStateStore thin wrapper
  -> SQLite backend runtime/schema/validation/sql
```

Future Postgres should become:

```text
Engram domain object
  -> StateStore protocol
  -> StateStoreCore using SQLRunner and StateBackend
  -> PostgresStateStore or backend factory target
  -> Postgres backend runtime/schema/validation/sql
```

### Code Style Required In New Files

Follow the repository house style:

- `from __future__ import annotations` in every Python file.
- Module docstring with spec references where the module owns behavior.
- Imports grouped stdlib, third-party, local; alphabetized within groups.
- Use `Path` from `pathlib`, not `os.path`.
- Use `collections.abc` for `Callable`, `Iterable`, `Mapping`, `Sequence`,
  `Iterator`.
- Use `X | None`, `list[T]`, `dict[K, V]`; do not import `Optional`, `List`,
  `Dict`, or `Set`.
- Keep constants in `engram/_constants.py`, even if used by storage modules.
- Prefer small protocols and dataclasses over broad class hierarchies.
- Add comments only where they explain a non-obvious invariant or migration
  safety point.
- Do not add new dependencies.
- Do not add SQLAlchemy, Alembic, or an external migration framework.
- Do not add entry-point plugin discovery for Engram state backends in this
  plan. An internal registry is enough.
- Do not import from `../simplebroker` at runtime.
- Do not use `SELECT *` in new store code. Select explicit columns in a fixed
  order and map rows by position.

### Required Reading Comprehension Questions

Before editing, the implementer must be able to answer these:

1. Why does SQLite/PG own access scores, parent-child edges, decay, metadata,
   and processing projections while LanceDB owns retrieval?
2. Why is LanceDB rebuildable from SQLite/PG and not a peer source of truth?
3. What current spec clauses must be changed before adding migrations?
4. What is the difference between a magic identifier and a schema version?
5. Which old schemas are known Engram schemas and which should be rejected as
   unrelated SQLite files?
6. Which migration steps are additive, and which are one-way schema changes?
7. Why should store behavior tests use a real SQLite database instead of mocks?
8. Why should `StateStoreCore` not import `sqlite3`?
9. Why is a future PG backend easier if store methods select explicit columns
   instead of `SELECT *`?
10. What would be a one-way door in this plan?

If any answer is unclear, stop and read the source files again.

## 5. Target Architecture

### New Modules

Create these modules unless implementation review finds a strictly smaller
equivalent that preserves the same boundaries:

```text
engram/store/db.py
engram/store/pathing.py
engram/store/core.py
engram/store/_sql/__init__.py
engram/store/_sql/base.py
engram/store/_sql/sqlite.py
engram/store/backends/__init__.py
engram/store/backends/base.py
engram/store/backends/sqlite/__init__.py
engram/store/backends/sqlite/backend.py
engram/store/backends/sqlite/runtime.py
engram/store/backends/sqlite/schema.py
engram/store/backends/sqlite/validation.py
engram/store/factory.py
```

Keep `engram/store/sqlite.py`, but reduce it to the public SQLite-backed store
wrapper over the new core. Do not leave two independent SQLite implementations.

### Runtime Ownership

- `engram/store/db.py`
  - Owns `SQLRunner`, `SetupPhase`, `SQLiteRunner`, `execute_with_retry`,
    `interruptible_sleep`, and translated database exception use.
  - May import `sqlite3`.
  - Must not import `Engram`, CLI, client, background, dogfood, or LanceDB.

- `engram/store/backends/base.py`
  - Owns a small `StateBackend` protocol.
  - Protocol should include only what `StateStoreCore` needs:
    `name`, `schema_version`, `sql`, `create_runner`, `initialize_database`,
    `meta_table_exists`, `read_magic`, `read_schema_version`,
    `write_schema_version`, `select_metadata`, and `migrate_schema`.
  - Do not copy simplebroker's queue, alias, vacuum, watcher, or activity
    waiter hooks.

- `engram/store/_sql/base.py`
  - Owns a typed SQL namespace protocol for Engram memory state operations.
  - This is not a generic query builder. It is a list of SQL statements and
    small helpers that the state core needs.

- `engram/store/_sql/sqlite.py`
  - Owns SQLite SQL statement constants and tiny SQLite SQL helpers.
  - Should use `?` placeholders.
  - Should expose ordered column lists for `memory_items` and failure rows.
  - Should not import `sqlite3`.

- `engram/store/backends/sqlite/runtime.py`
  - Owns SQLite version check, WAL setup, `busy_timeout`, `foreign_keys`,
    `wal_autocheckpoint`, and other SQLite PRAGMAs.
  - Validate an existing non-empty file before opening it as a DB.

- `engram/store/backends/sqlite/validation.py`
  - Owns SQLite file validation and optional Engram magic validation.
  - Must distinguish:
    - missing file when create is false
    - empty file or missing file when create is true
    - invalid non-SQLite file
    - SQLite file that is not an Engram vault
    - Engram DB with unsupported newer schema

- `engram/store/backends/sqlite/schema.py`
  - Owns schema initialization and forward migrations for known SQLite schemas.
  - No domain methods here. This module creates tables, validates shape, and
    migrates schema only.

- `engram/store/core.py`
  - Owns backend-neutral implementation of the `StateStore` protocol using
    `SQLRunner` and `StateBackend`.
  - Must not import `sqlite3`.
  - Must not know the vault filesystem layout except through the backend/store
    wrapper.
  - Must use explicit ordered column mapping.

- `engram/store/factory.py`
  - Owns state-store backend selection.
  - For this plan, only SQLite is implemented.
  - If `ENGRAM_BACKEND=pg`, fail clearly with a not-yet-supported error unless
    a later plan implements PG.

### Metadata Contract

Use the existing SQLite `vault_meta(key, value)` table for SQLite. Add a magic
key and keep the canonical schema version key:

```text
state_magic = "engram-state-v1"
schema_version = "<current sqlite schema version>"
vault_created_at = "<nanoseconds>"
```

Constants to add or update in `engram/_constants.py`:

```text
ENGRAM_STATE_MAGIC
STATE_MAGIC_KEY
VAULT_SCHEMA_VERSION_KEY
VAULT_CREATED_AT_KEY
CURRENT_SQLITE_SCHEMA_VERSION
SQLITE_BUSY_TIMEOUT_MS
SQLITE_WAL_AUTOCHECKPOINT
```

Do not use the package version as the database magic. A package can release
without changing storage identity. The magic identifies "this is an Engram
state database." The schema version identifies which migration state the DB is
in.

For future Postgres, prefer simplebroker's typed singleton meta row pattern:

```text
meta(
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
  magic TEXT NOT NULL,
  schema_version BIGINT NOT NULL,
  vault_created_at BIGINT NOT NULL
)
```

Do not build the PG backend in this plan, but keep the SQLite core from making
the future PG shape impossible.

## 6. Invariants And Constraints

### State And Retrieval

- SQLite remains authoritative for local memory state in this plan.
- LanceDB remains a rebuildable retrieval projection.
- No migration may read from LanceDB to reconstruct SQLite state.
- No migration may delete or rewrite moment text, embeddings, created_at, item
  IDs, access, relevance, parent-child edges, summary terms, processing
  attempts, processing errors, or task correlation data except where a
  documented old schema has no equivalent field.
- Coalescing remains additive. Migrations must not delete tier-0 moments.

### Migration Policy

- Migrations are forward-only.
- Migrations run on open after defensive file validation and before normal
  state operations.
- Migrations must be idempotent.
- Migrations must be transactional.
- Migrations must be ordered.
- Migrations must reject newer schema versions with a clear upgrade message.
- Migrations may adopt old Engram development schemas only when their table
  signatures match known Engram shapes.
- Migrations must reject unrelated SQLite files, wrong magic values, corrupted
  files, and unknown table shapes.
- A known legacy DB without magic can be migrated only if known Engram table
  signatures prove it is an Engram DB. Do not treat any SQLite file with a
  `memory_items` table as Engram unless the required columns match a known
  historical shape.

### Backend Portability

- `StateStoreCore` must not import `sqlite3`.
- `engram/core/memory.py` should construct stores through a factory, not by
  importing SQLite internals directly.
- Backend-specific SQL belongs in backend SQL namespace modules.
- Backend-specific connection setup belongs in backend runtime modules.
- Backend-specific schema migration belongs in backend schema modules.
- Backend-specific validation belongs in backend validation modules.
- Do not introduce an external plugin system yet. Internal backend registry is
  sufficient and easier to test.

### SQLite Runtime Safety

- Existing non-empty DB files must be validated before use.
- SQLite WAL setup should happen in a controlled setup phase before normal
  operations.
- `PRAGMA foreign_keys = ON` must be applied for every connection.
- `PRAGMA busy_timeout` must be applied for every connection.
- SQLite lock/busy retry must wrap schema setup and write transactions where
  lock contention is expected.
- Retry must be limited. Infinite retry loops are forbidden.
- Retry must only retry lock/busy operational errors. Integrity and data errors
  should fail immediately.

### Public Surface Compatibility

- `Engram.record`, `Engram.search`, `Engram.lookup`, `Engram.pin`,
  `Engram.build_context`, `Engram.status`, `Engram.rebuild_index`, and
  `Engram.work_once` behavior must remain the same except for improved open
  and migration behavior.
- CLI default output must not change in this plan.
- CLI `--json` shapes must not silently change. If status needs generic store
  fields, update specs and tests in the same task.
- `SQLiteStateStore` may remain importable as the SQLite store class, but it
  must be a wrapper over the new implementation, not a second path.

### Path Hardening

- Port safe path component validation for database filenames and relative
  components.
- Do not apply simplebroker's filename validation blindly to user-provided
  absolute vault paths. Absolute paths with spaces are valid user paths and
  must not be rejected just because they contain a shell-sensitive character.
- Validate generated SQLite filenames and relative DB target components.
- Resolve vault paths with `Path.expanduser().resolve()`.
- Reject path traversal in relative database filenames.
- Keep path validation errors clear and user-actionable.

### Error Priorities

- Fatal:
  - database corruption
  - invalid SQLite file at the expected DB path
  - wrong magic for an initialized DB
  - schema version newer than supported
  - unknown old schema shape
  - failed migration verification after a migration step
  - integrity failures during item/edge writes
- Retriable:
  - SQLite "database is locked", "database table is locked", "database schema
    is locked", and busy equivalents.
- Best-effort:
  - cleanup of temporary lock marker files if marker files are used.
  - logging/debug metadata; do not downgrade a successful core transaction
    because optional diagnostic cleanup failed.

### Out Of Scope

- Do not implement a production Postgres backend.
- Do not add SQLAlchemy, Alembic, or any external migration framework.
- Do not replace LanceDB.
- Do not change Weft ownership of deferred work.
- Do not introduce deletion or forget semantics.
- Do not redesign context assembly.
- Do not introduce hosted or multi-user behavior.
- Do not add external backend plugin discovery.
- Do not add a second durable queue.
- Do not rewrite unrelated CLI/client surfaces.
- Do not do drive-by refactors in `engram/index`, `engram/dogfood`, or
  `engram/core` beyond what the store factory requires.

### One-Way Doors

Schema migrations are the one-way door in this plan. Treat them with a higher
bar:

- Write migration tests before implementation.
- Preserve data in tests with non-empty old-schema DBs.
- Verify exact post-migration schema and metadata.
- Verify opening a newer schema fails and does not rewrite it.
- Verify failed migration rolls back.
- Do not claim done until the old rejection tests have been replaced with
  positive migration tests.

## 7. Rollback And Sequencing

Do this work in ordered phases. Do not jump straight to rewriting
`SQLiteStateStore`.

Rollback policy:

- Spec-only changes can be reverted independently before code starts.
- New helper modules can be reverted before they are wired into
  `SQLiteStateStore`.
- Once migrations are wired into open, rollback requires reverting code and
  accepting that any local DB already migrated to the new schema may not open
  on the old code. This is why migration tests and review happen before wiring.
- Do not ship a migration step that cannot be described in both directions at
  the data level, even if application rollback is forward-only.

Sequencing:

1. Update specs and docs to allow forward migrations.
2. Add low-level helpers and tests without changing `SQLiteStateStore`.
3. Add backend/schema modules and migration tests.
4. Add `StateStoreCore` and run it behind `SQLiteStateStore`.
5. Add store factory and remove direct domain coupling to SQLite.
6. Add architecture guardrails.
7. Run final verification and fresh review.

Stop if the plan starts requiring PG implementation to prove SQLite behavior.
That means the abstraction is too broad for this phase.

## 8. Tasks

### 1. Update specs to replace rejection-only schema policy with migration policy

Outcome:

- The authoritative specs allow explicit, forward-only migrations for known
  Engram state-store schemas.
- The specs still reject unknown, corrupted, newer, or wrong-identity stores.

Files to touch:

- `docs/specs/12-local-app-surface.md`
- `docs/specs/15-foundation-contracts-and-invariants.md`
- Possibly `docs/specs/10-minimum-memory-model.md` if a storage-format
  invariant needs clarification.
- Possibly `docs/specs/11-minimum-write-search-context-slice.md` if deferred
  processing projection wording mentions SQLite version behavior.
- Add this plan to related-plan backlinks in touched specs.

Read first:

- `docs/specs/12-local-app-surface.md` [LAS-4], [LAS-5], [LAS-6], [LAS-7]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-44]
- `docs/agent-context/runbooks/maintaining-traceability.md`

Implementation notes:

- Replace "reject older shapes clearly" with "migrate known older Engram
  shapes forward; reject unknown or newer shapes clearly."
- Keep "opening a vault and recovering a vault are different actions" from
  [LAS-24]. Migration on open is normal version alignment, not manual recovery
  from corruption.
- Say migrations must be source-of-truth only: SQLite/PG state, never LanceDB.
- Say migrations must be idempotent, ordered, transactional, and tested with
  real SQLite.

Tests:

- No runtime tests in this task.
- Verification is inspection: spec text no longer conflicts with this plan.

Stop and re-evaluate if:

- The spec update starts permitting arbitrary unknown-shape adoption.
- The spec update weakens SQLite/PG source-of-truth ownership.
- The spec update implies LanceDB participates in migrations.

Done signal:

- The migration policy in specs matches this plan.
- Related plans list includes this plan.

### 2. Add store-level exceptions and constants

Outcome:

- Engram has explicit store/database errors and constants needed by the DB
  layer.

Files to touch:

- `engram/_exceptions.py`
- `engram/_constants.py`
- `engram/__init__.py` if any new errors are intended to be public.
- `tests/test_constants.py`
- New or updated exception tests if public behavior requires them.

Read first:

- `engram/_exceptions.py`
- `engram/_constants.py`
- `../simplebroker/simplebroker/_exceptions.py`
- `../simplebroker/simplebroker/_constants.py`

Implementation notes:

- Add Engram-owned errors such as:
  - `StoreError`
  - `StoreOperationalError`
  - `StoreIntegrityError`
  - `StoreDataError`
  - `StoreVersionError`
  - `StoreBackendNotSupportedError`
  - `InvalidStorePathError`
- Keep these exceptions backend-neutral. Do not make public Engram errors
  inherit from `sqlite3` exceptions; the SQLite runner translates concrete
  `sqlite3` failures into Engram store errors.
- Add constants:
  - `ENGRAM_STATE_MAGIC = "engram-state-v1"`
  - `STATE_MAGIC_KEY = "state_magic"`
  - `CURRENT_SQLITE_SCHEMA_VERSION = 5`
  - `MIN_SQLITE_VERSION = (3, 35, 0)` because this plan uses
    `ALTER TABLE ... DROP COLUMN` for the v3-to-v5 migration.
  - SQLite PRAGMA defaults such as busy timeout and WAL autocheckpoint.
- Fix stale comments in `_constants.py` so they describe real migration
  behavior.
- Do not add compatibility aliases for renamed constants. If a constant is
  renamed, update all repo users in the same change.

Tests:

- Update `tests/test_constants.py` to assert the new constants and config
  behavior where relevant.
- If errors are public, add import/export assertions in the existing public
  API tests or a small new test.

Stop and re-evaluate if:

- New exceptions start duplicating existing public errors with no clearer
  boundary.
- Constants drift into backend modules instead of `_constants.py`.

Done signal:

- Constants and errors exist, are typed, are exported only if useful, and tests
  cover the expected public surface.

### 3. Port the SQLite retry helper and interruptible sleep

Outcome:

- SQLite lock/busy operations have a bounded retry helper that Engram owns.

Files to touch:

- `engram/store/db.py`
- `tests/store/test_db_retry.py`

Read first:

- `../simplebroker/simplebroker/helpers.py` `interruptible_sleep`
- `../simplebroker/simplebroker/helpers.py` `_execute_with_retry`
- `docs/agent-context/runbooks/testing-patterns.md`

Implementation notes:

- Port the logic, not the names with leading underscores.
- Suggested Engram names:
  - `interruptible_sleep`
  - `execute_with_retry`
- Retry only translated `StoreOperationalError` messages containing lock/busy
  markers.
- Include bounded exponential backoff plus small jitter.
- Support an optional `threading.Event`.
- Preserve interruption behavior with a clear Engram-owned stop exception or
  store operational error. Do not import simplebroker's `StopException`.

Tests:

- Red-green first:
  - Write a test where an operation raises `StoreOperationalError("database is
    locked")` once and then succeeds. Assert it returns success and operation
    was called twice.
  - Write a test where an operation raises `StoreOperationalError("syntax
    error")`. Assert no retry happens.
  - Write a test where max retries are exhausted. Assert the last error is
    raised.
  - Write a test where a stop event interrupts retry sleep.
- These helper tests may use fake callables. That is acceptable because the
  helper's contract is retry behavior, not SQLite persistence.

Stop and re-evaluate if:

- The helper catches all exceptions.
- The helper sleeps unboundedly.
- The helper starts owning transaction semantics. Transactions belong in the
  runner/store methods.

Done signal:

- Retry helper is tested in isolation and has no dependency on simplebroker.

### 4. Port path hardening for generated DB names and relative components

Outcome:

- Engram validates database filename/relative path components without
  rejecting legitimate absolute vault paths.

Files to touch:

- `engram/store/pathing.py`
- `engram/_constants.py` if path length or allowed component constants are
  needed.
- `tests/store/test_pathing.py`

Read first:

- `../simplebroker/simplebroker/_constants.py` `_validate_safe_path_components`
- `../simplebroker/simplebroker/helpers.py` path helper functions around
  database parent directories and symlink resolution
- `../simplebroker/tests/test_path_security.py`

Implementation notes:

- Port a function equivalent to `validate_safe_path_components(path, context)`.
- Apply this function to relative DB filenames and generated DB target
  components, not to every user-provided absolute vault path.
- Keep `DEFAULT_SQLITE_FILENAME = "engram.db"` validated by tests.
- Reject:
  - empty strings
  - null bytes and control characters
  - `..`
  - `.`
  - shell metacharacters in relative DB names
  - path components starting or ending with spaces
  - path components longer than filesystem limits
- Allow:
  - normal project paths
  - hidden filenames such as `.engram` where used as vault directories
  - absolute vault paths with spaces after normal `Path` resolution
- If Windows-specific validation is ported, keep tests platform-gated like
  simplebroker does.

Tests:

- Red-green first:
  - Valid simple names pass: `engram.db`, `data-2026.db`.
  - Valid compound relative names pass if the helper is intended to allow them.
  - Parent traversal fails.
  - Control characters fail.
  - Shell metacharacters fail for relative DB components.
  - Absolute vault path with spaces is not rejected by the store-open path.
- Use real temporary paths for integration with `SQLiteStateStore`.

Stop and re-evaluate if:

- The validator rejects common valid user vault paths.
- The validator is used as a substitute for SQLite file validation. These are
  separate checks.

Done signal:

- Path component validation exists and tests prove both rejection and allowed
  vault-path behavior.

### 5. Add SQLite file validation and defensive connection setup

Outcome:

- Engram refuses invalid DB files before normal SQLite open and applies
  connection PRAGMAs consistently.

Files to touch:

- `engram/store/backends/sqlite/validation.py`
- `engram/store/backends/sqlite/runtime.py`
- `engram/store/db.py`
- `tests/store/test_sqlite_validation.py`
- `tests/store/test_sqlite_runtime.py`

Read first:

- `../simplebroker/simplebroker/_backends/sqlite/validation.py`
- `../simplebroker/simplebroker/_backends/sqlite/runtime.py`
- `../simplebroker/tests/test_runner_validation.py`
- `../simplebroker/tests/test_pragma_settings.py`

Implementation notes:

- Validate existing non-empty files:
  - file exists
  - is regular file
  - parent directory is readable/writable
  - file is readable/writable
  - first 16 bytes are `SQLite format 3\0`
  - read-only SQLite open can execute `PRAGMA schema_version`
  - optional magic check can read Engram metadata once metadata exists
- Permit missing files and empty files only in create/init paths.
- Apply per-connection settings:
  - `PRAGMA foreign_keys = ON`
  - `PRAGMA busy_timeout = <constant>`
  - `PRAGMA wal_autocheckpoint = <constant>`
- Apply connection-phase setup:
  - Require SQLite 3.35.0 or newer and fail clearly if unavailable.
  - `PRAGMA journal_mode=WAL` and verify the result.
  - Set auto-vacuum only if we intentionally want it for Engram. Default to no
    auto-vacuum unless a specific Engram need is documented.
- Keep SQLite setup code in SQLite runtime modules.

Tests:

- Red-green first:
  - Invalid text file at `engram.db` fails with an Engram store error.
  - Empty file with `create=True` opens and initializes.
  - Missing DB with `create=False` still fails as an uninitialized vault.
  - Existing valid SQLite file with wrong magic fails after magic validation is
    active.
  - WAL mode is enabled on initialized SQLite DB.
  - `foreign_keys` is on for the active connection.
  - `busy_timeout` is set.
- Use real SQLite files. Do not mock `sqlite3.connect` except for one narrow
  test that simulates WAL failure if real failure cannot be induced.

Stop and re-evaluate if:

- Validation opens the DB read-write before deciding it is safe.
- A corrupted file gets overwritten in create mode.
- Runtime setup creates tables. Table creation belongs in schema bootstrap.

Done signal:

- Defensive validation/runtime helpers exist, use real files in tests, and are
  not yet required to replace `SQLiteStateStore` until the runner task wires
  them in.

### 6. Add `SQLRunner` and `SQLiteRunner`

Outcome:

- Engram has a database execution layer that can run SQLite now and support PG
  later.

Files to touch:

- `engram/store/db.py`
- `tests/store/test_sql_runner.py`

Read first:

- `../simplebroker/simplebroker/_runner.py`
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/runner.py`
- `engram/store/sqlite.py`

Implementation notes:

- Define `SetupPhase` with at least:
  - `CONNECTION`
  - `OPTIMIZATION`
- Define `SQLRunner` protocol:
  - `run(sql: str, params: tuple[Any, ...] = (), *, fetch: bool = False)`
  - `begin_immediate()`
  - `commit()`
  - `rollback()`
  - `close()`
  - `setup(phase: SetupPhase)`
  - `is_setup_complete(phase: SetupPhase)`
- Implement `SQLiteRunner`:
  - thread-local connection
  - autocommit mode (`isolation_level=None`) so explicit transactions are real
  - process ID/fork detection that discards inherited connections
  - all-connection tracking and cleanup
  - translated errors into Engram store errors
  - connection setup via SQLite runtime helpers
  - setup lock and marker-file coordination for connection setup, ported from
    simplebroker's phase-lock pattern and scoped to the SQLite DB path.
    Marker files must persist for real databases so short-lived handles do not
    break cross-process setup coordination.
- Keep runner generic. It should not know about memory items.

Tests:

- Red-green first:
  - `SQLiteRunner.run(..., fetch=True)` returns rows from a real DB.
  - Explicit `begin_immediate`, write, `commit` persists.
  - Explicit `begin_immediate`, write, `rollback` does not persist.
  - Integrity errors translate to `StoreIntegrityError`.
  - Invalid SQL operational errors translate to `StoreOperationalError`.
  - `setup(CONNECTION)` is idempotent.
  - `close()` closes all created connections and can be called repeatedly.
- Use real SQLite.
- Do not use mocks for transaction behavior.

Stop and re-evaluate if:

- `SQLiteRunner` starts importing Engram domain models.
- Transaction control is split between runner and callers in a way that causes
  implicit commits.
- The runner creates schema tables. That belongs in backend schema helpers.

Done signal:

- Runner tests pass with real SQLite and no `SQLiteStateStore` refactor yet.

### 7. Add backend protocol, SQLite backend adapter, and SQL namespace

Outcome:

- Store core can ask a backend for SQL, schema setup, metadata, and migration
  behavior without knowing the concrete database.

Files to touch:

- `engram/store/backends/base.py`
- `engram/store/backends/__init__.py`
- `engram/store/backends/sqlite/backend.py`
- `engram/store/backends/sqlite/__init__.py`
- `engram/store/_sql/base.py`
- `engram/store/_sql/sqlite.py`
- `engram/store/_sql/__init__.py`
- `tests/store/test_backend_contract.py`
- `tests/store/test_sql_namespace.py`

Read first:

- `../simplebroker/simplebroker/_backend_plugins.py`
- `../simplebroker/simplebroker/_sql/_contract.py`
- `../simplebroker/simplebroker/_sql/sqlite.py`
- `../simplebroker/simplebroker/_backends/sqlite/plugin.py`
- `../simplebroker/extensions/simplebroker_pg/simplebroker_pg/plugin.py`

Implementation notes:

- Keep the Engram `StateBackend` protocol much smaller than simplebroker's
  plugin protocol.
- Suggested backend protocol:
  - `name`
  - `schema_version`
  - `sql`
  - `create_runner(target, *, create)`
  - `initialize_database(runner, *, create)`
  - `meta_table_exists(runner)`
  - `read_magic(runner)`
  - `read_schema_version(runner)`
  - `write_schema_version(runner, version)`
  - `select_metadata(runner)`
  - `migrate_schema(runner, *, current_version, write_schema_version)`
- Suggested SQL namespace protocol should include:
  - schema DDL constants or accessors
  - ordered item column tuple
  - ordered failure column tuple
  - insert/update/select statements used by `StateStoreCore`
  - helper for `IN` placeholders
- SQL namespace should expose explicit ordered select lists, not `SELECT *`.
- SQLite backend should adapt to current file-backed vaults only.
- Do not include simplebroker concepts:
  - queue aliases
  - last timestamp generator
  - vacuum
  - watcher activity waiters
  - broadcast preparation
  - external plugin entry points

Tests:

- Red-green first:
  - Backend contract exposes required members.
  - SQLite SQL namespace has required members.
  - `ITEM_COLUMNS` order matches row mapper expectations.
  - No SQL constants in new code contain `SELECT *`.
- It is acceptable for these tests to inspect strings. They are architecture
  and contract tests, not persistence behavior tests.

Stop and re-evaluate if:

- The protocol becomes a large clone of simplebroker's plugin protocol.
- SQL namespace starts doing business logic.
- Backend adapter starts depending on LanceDB, Weft, CLI, or client modules.

Done signal:

- Backend and SQL contracts exist, are small, and tests prevent obvious drift.

### 8. Implement schema bootstrap and ordered SQLite migrations

Outcome:

- SQLite store initialization creates current schema and migrates known older
  Engram schemas forward on open.

Files to touch:

- `engram/store/backends/sqlite/schema.py`
- `engram/store/backends/sqlite/backend.py`
- `engram/store/_sql/sqlite.py`
- `tests/store/test_sqlite_migrations.py`
- Update `tests/store/test_sqlite.py` rejection tests.

Read first:

- `../simplebroker/simplebroker/_backends/sqlite/schema.py`
- `../simplebroker/tests/test_message_claim.py` migration tests
- `../simplebroker/tests/test_edge_cases.py` concurrent migration test
- Current legacy-shape tests in `tests/store/test_sqlite.py`

Implementation notes:

- Bootstrap current schema:
  - create `vault_meta`
  - create `memory_items`
  - create `memory_edges`
  - create current query indexes
  - insert `state_magic`
  - insert `schema_version`
  - insert `vault_created_at`
- Add exactly these query indexes:
  - `memory_items(tier, created_at)`
  - `memory_edges(child_id)`
  - `memory_edges(parent_id, position)`
  - Do not add any other indexes in this plan.
- Detect current schema by metadata and exact shape.
- Detect known old schemas by exact table and column signatures.
- Known migrations to implement:
  - pre-plan v4 to v5: add `state_magic`, set schema version to 5, and create
    current indexes.
  - legacy no-metadata state shape to current metadata shape when
    `memory_items` and `memory_edges` match known Engram columns.
  - queue-shaped v3 with `processing_status` to current shape without that
    column, preserving `processing_attempts`, `last_processing_error`,
    `last_task_tid`, and `last_task_updated_at`.
  - metadata key drift from `vault_schema_version` to canonical
    `schema_version` only for known Engram shapes.
- For SQLite column removal, use `ALTER TABLE memory_items DROP COLUMN
  processing_status`. This is why the runtime check requires SQLite 3.35.0 or
  newer. Do not implement a table-rebuild migration in this plan.
- Wrap each migration in:
  - `BEGIN IMMEDIATE`
  - schema changes for exactly one version step
  - write schema version
  - run migration verification, including `PRAGMA foreign_key_check`
  - commit
- Verify after each migration:
  - current tables exist
  - current columns match expected order
  - metadata includes correct magic and schema version
  - required row counts match pre-migration counts
  - `PRAGMA foreign_key_check` returns no rows
- Reject newer schema before attempting migration.
- Reject unknown shapes.

Tests:

- Red-green first:
  - Current DB opens idempotently.
  - New DB initializes with magic, schema version, and vault_created_at.
  - Pre-plan v4 DB without magic migrates to v5 by adding `state_magic`,
    updating `schema_version`, and creating current indexes.
  - Known legacy no-metadata DB migrates and preserves memory item and edge
    data.
  - Known v3 queue-shaped DB migrates and preserves processing error/task data.
  - Metadata key drift fixture migrates to canonical key and does not keep a
    second canonical version key.
  - Newer schema version fails clearly and leaves DB unchanged.
  - Wrong magic fails clearly and leaves DB unchanged.
  - Unknown SQLite shape fails clearly and leaves DB unchanged.
  - Failed migration rolls back. Induce this by creating an old fixture with
    data that violates a new invariant.
  - Migration is idempotent across repeated opens.
  - Concurrent opens from multiple processes do not corrupt migration. Use a
    small multiprocessing test like simplebroker's, marked appropriately if it
    is slow or platform-sensitive.
- Use real SQLite. Do not mock migration SQL.

Stop and re-evaluate if:

- Migration logic starts guessing from partial table names.
- Migration drops data without an explicit old-shape reason.
- Migration requires LanceDB.
- Migration requires package-level global mutable state.

Done signal:

- Old rejection tests have been replaced by positive migration tests for known
  old Engram shapes and rejection tests for unknown/wrong/newer shapes.

### 9. Build `StateStoreCore` over runner and backend SQL

Outcome:

- All state-store domain operations run through `SQLRunner` and backend SQL,
  not direct `sqlite3` calls.

Files to touch:

- `engram/store/core.py`
- `engram/store/sqlite.py`
- `engram/store/base.py` only if the protocol needs methods already present in
  `SQLiteStateStore` but missing from `StateStore`.
- `tests/store/test_sqlite.py`
- `tests/store/test_state_store_contract.py`

Read first:

- `engram/store/sqlite.py`
- `engram/store/base.py`
- `engram/_models.py`
- `tests/store/test_sqlite.py`

Implementation notes:

- Move store behavior into `StateStoreCore`.
- Keep `SQLiteStateStore` as a thin wrapper:
  - compute DB target from vault path
  - create SQLite backend/runner
  - initialize/migrate
  - delegate `StateStore` methods to `StateStoreCore`
  - expose `db_path` for existing status behavior
  - own `close()`
- Preserve all existing state behavior:
  - `put_item`
  - `get_item`
  - `get_items`
  - `list_recent_items`
  - `list_high_value_items`
  - `list_uncoalesced_moments`
  - `list_uncoalesced_episodes`
  - `list_uncoalesced_items`
  - `create_episode`
  - `create_arc`
  - `create_summary_item`
  - `get_children`
  - `get_next_repairable_item`
  - processing success/failure/task submission
  - count methods
  - `update_indexed_at`
  - `update_indexed_at_many`
  - `increment_access`
  - `pin_item`
  - `all_items`
- Use explicit ordered select columns:
  - no `SELECT *`
  - row mapper accepts `tuple[Any, ...]`
  - mapper order comes from SQL namespace constants
- Keep JSON summary term serialization in the core for now because it is part
  of Engram's durable state contract. Do not introduce PG JSONB in this plan.
- Keep `_allocate_id` behavior intact: nanosecond timestamp candidate, increment
  until unique in the store.
- Any helper for `IN` clauses must handle empty sequences before generating SQL.
- Do not add generic repository abstractions for each table. That is ORM drift.

Tests:

- Red-green first:
  - Add a backend-neutral store contract test file that exercises behavior via
    the public `StateStore` protocol using real SQLite.
  - Existing `tests/store/test_sqlite.py` should still pass after being updated
    for migration policy.
  - Add a test that monkeypatching `sqlite3` is not needed; the store contract
    runs against real DB files.
  - Add a test or architecture grep that new store code does not contain
    `SELECT *`.
- Do not mock `StateStoreCore`, `SQLiteRunner`, or SQLite persistence.

Stop and re-evaluate if:

- `StateStoreCore` starts importing SQLite modules.
- `SQLiteStateStore` and `StateStoreCore` both contain copies of the same SQL
  behavior.
- Existing public behavior changes outside open/migration errors.

Done signal:

- Store tests pass through `SQLiteStateStore`, but the actual implementation is
  runner/backend/core based.

### 10. Add state-store factory and remove direct SQLite coupling from `Engram`

Outcome:

- Domain construction goes through one store factory, making backend selection
  explicit and future PG work localized.

Files to touch:

- `engram/store/factory.py`
- `engram/core/memory.py`
- `engram/_constants.py`
- `tests/core/test_memory.py`
- `tests/store/test_store_factory.py`
- `tests/commands/test_memory_commands.py`
- `tests/cli/test_cli.py`

Read first:

- `engram/core/memory.py`
- `engram/_constants.py` `load_config()`
- `tests/core/test_memory.py`

Implementation notes:

- Add `open_state_store(vault_path, *, create, backend_name=None, config=None)`.
- Default backend remains SQLite.
- `Engram.__init__` should call the factory instead of `SQLiteStateStore`
  directly.
- If `ENGRAM_BACKEND` is unset or `sqlite`, behavior remains local SQLite.
- If `ENGRAM_BACKEND=pg`, raise a clear `StoreBackendNotSupportedError` or
  equivalent. Do not silently fall back to SQLite.
- Keep `Engram.status()` behavior for SQLite. If generic status fields are
  added, update specs and CLI JSON tests in the same task.
- Do not implement PG connection parsing in this plan.

Tests:

- Red-green first:
  - Default factory returns a SQLite-backed store.
  - `ENGRAM_BACKEND=sqlite` returns SQLite-backed store.
  - `ENGRAM_BACKEND=pg` fails clearly and does not create an SQLite DB.
  - `Engram.init()` and `Engram.open()` still use real SQLite by default.
  - CLI commands still work by default.
- Use real SQLite for default behavior.
- Mocking environment variables is fine. Do not mock store persistence.

Stop and re-evaluate if:

- Store factory starts importing CLI/client/background modules.
- Factory grows plugin discovery or PG implementation.
- `Engram` still imports `SQLiteStateStore` directly after this task.

Done signal:

- `engram/core/memory.py` depends on the store protocol/factory path, not the
  SQLite concrete implementation.

### 11. Add architecture guardrails for backend boundaries

Outcome:

- Tests prevent the most likely future drift: SQLite imports in core, SQL
  copied into domain code, private backend coupling, and mock-heavy store tests.

Files to touch:

- `tests/architecture/test_store_boundaries.py`
- Possibly update existing architecture tests if they exist.

Read first:

- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1], [FCI-2],
  [FCI-35], [FCI-36], [FCI-38]
- Existing tests under `tests/architecture/` if present.
- `../simplebroker/tests/test_backend_plugin_resolution.py` for the spirit of
  backend contract checks.

Implementation notes:

- Add grep/import-boundary tests:
  - `engram/core/*` must not import `sqlite3`.
  - `engram/core/memory.py` must not import `SQLiteStateStore`.
  - `engram/store/core.py` must not import `sqlite3`.
  - `engram/store/backends/sqlite/*` may import `sqlite3`.
  - `engram/store/*` must not import CLI, client, background, dogfood, or
    LanceDB.
  - New store code should not contain `SELECT *`.
- Keep architecture tests clear and targeted. Do not build a general static
  analyzer.

Tests:

- The architecture tests are themselves the proof.
- Also run normal store/core tests to make sure guardrails did not replace real
  behavior tests.

Stop and re-evaluate if:

- Guardrails become so broad they block legitimate imports not related to this
  plan.
- Guardrails are used instead of real persistence tests.

Done signal:

- Architecture tests fail for the obvious forbidden dependency patterns and pass
  for the intended new structure.

### 12. Update documentation and implementation notes

Outcome:

- Future agents can understand the backend foundation without rediscovering it
  from code.

Files to touch:

- `AGENTS.md` only if root guidance needs a concise pointer. Avoid duplicating
  long context.
- `docs/agent-context/engineering-principles.md` if the backend portability
  rule should become durable guidance.
- `docs/implementation/` new or existing implementation note for state store
  backend architecture.
- `docs/specs/README.md` or spec backlinks if needed.
- `docs/lessons.md` only if implementation reveals a reusable correction.

Read first:

- `docs/agent-context/runbooks/maintaining-traceability.md`
- Existing `docs/implementation/` files.

Implementation notes:

- Add an implementation note such as
  `docs/implementation/08-state-store-backend-foundation.md`.
- Explain:
  - runner/backend/core layering
  - metadata and magic
  - migration policy
  - SQLite defensive open
  - what is deliberately not included yet: PG implementation, plugin discovery,
    ORM/migration framework
  - how future PG should fit the seam
- Keep docs operational. Do not write generic database theory.

Tests:

- Docs-only verification by inspection.
- If docs include file links, verify paths exist with `rg --files`.

Stop and re-evaluate if:

- Docs imply PG is already implemented.
- Docs diverge from spec language.

Done signal:

- Specs, plan, implementation note, and code point to the same architecture.

## 9. Testing Plan

### Testing Principles

- Use red-green TDD whenever the expected behavior can be expressed before
  implementation.
- For every simplebroker behavior or helper ported into Engram, port or adapt
  the corresponding simplebroker test into Engram's test suite. If a
  simplebroker test is not applicable, write the reason in the implementation
  note or the task handoff.
- Use real SQLite for all store, migration, transaction, and open behavior.
- Do not mock the core state-store path.
- Do not mock `StateStoreCore`.
- Do not mock `SQLiteRunner` in behavior tests.
- Do not mock migrations.
- Mock only:
  - helper retry callables when testing retry logic itself
  - environment variables
  - one narrow WAL failure path if a real failure cannot be induced safely
  - external model calls in unrelated existing tests

### New Or Updated Test Files

- `tests/store/test_db_retry.py`
  - Retry helper behavior.
- `tests/store/test_pathing.py`
  - Path component validation and vault path allowance.
- `tests/store/test_sqlite_validation.py`
  - SQLite file validation and magic validation.
- `tests/store/test_sqlite_runtime.py`
  - WAL, foreign keys, busy timeout, setup idempotence.
- `tests/store/test_sql_runner.py`
  - Runner execution, transactions, error translation, close behavior.
- `tests/store/test_backend_contract.py`
  - Backend protocol and SQLite backend contract.
- `tests/store/test_sql_namespace.py`
  - SQL namespace required members, ordered columns, no `SELECT *`.
- `tests/store/test_sqlite_migrations.py`
  - Forward migrations and rejection cases.
- `tests/store/test_state_store_contract.py`
  - Backend-neutral state-store behavior through real SQLite.
- `tests/store/test_store_factory.py`
  - Backend selection, default SQLite, unsupported PG failure.
- `tests/architecture/test_store_boundaries.py`
  - Import and SQL-boundary guardrails.
- Update `tests/store/test_sqlite.py`
  - Preserve existing behavior tests.
  - Replace old-shape rejection assertions with migration assertions where the
    shape is known Engram history.
- Update `tests/core/test_memory.py`, `tests/commands/test_memory_commands.py`,
  and `tests/cli/test_cli.py` only as needed to account for factory construction
  and unchanged behavior.

### Simplebroker Test Port Matrix

Each row below must have an Engram test before the related implementation is
considered done:

| Simplebroker source test | Engram target test | Adaptation required |
| --- | --- | --- |
| `tests/test_runner_validation.py` | `tests/store/test_sqlite_validation.py`, `tests/store/test_sql_runner.py` | Keep real invalid/empty/corrupt files; use Engram store errors and vault paths. |
| `tests/test_pragma_settings.py` | `tests/store/test_sqlite_runtime.py` | Assert Engram's WAL, `foreign_keys`, busy timeout, and autocheckpoint settings. |
| `tests/test_path_security.py` | `tests/store/test_pathing.py` | Keep component-level rejection cases; add a positive case for absolute vault paths with spaces. |
| `tests/test_message_claim.py` migration tests | `tests/store/test_sqlite_migrations.py` | Replace queue/claimed assertions with memory item, edge, metadata, and processing projection preservation. |
| `tests/test_edge_cases.py::test_concurrent_schema_migration` | `tests/store/test_sqlite_migrations.py` or a dedicated multiprocessing test file | Start from an old Engram schema fixture and open it from multiple processes. |
| `tests/test_backend_plugin_resolution.py` | `tests/store/test_backend_contract.py` | Test Engram's internal backend contract only; external entry-point plugin behavior stays out of scope. |
| `extensions/simplebroker_pg/tests/test_pg_ownership.py` | No executable target in this plan | Document the future PG typed singleton meta shape; do not add PG runtime tests until the PG backend exists. |

### Invariants To Prove

- New vault initializes metadata with magic, schema version, and created time.
- Current vault opens idempotently.
- Known old vault migrates forward and preserves items.
- Known v3 queue-shaped vault migrates forward and preserves processing
  inspection data.
- Unknown SQLite file is rejected.
- Wrong magic is rejected.
- Newer schema is rejected and not rewritten.
- Invalid non-SQLite file is rejected and not overwritten.
- Failed migration rolls back.
- SQLite WAL mode is enabled.
- SQLite foreign keys are enabled on active connections.
- Lock/busy errors retry; non-lock errors do not.
- `record()` still stores a durable moment before returning.
- `lookup` and `search` access-score semantics do not change.
- `context` and status still do not increment access scores.
- Parent-child edge ordering survives migration and normal writes.
- LanceDB rebuild still reads from authoritative state store only.
- `Engram` uses the store factory instead of a SQLite concrete import.

### Commands

Run targeted tests as tasks complete:

```bash
./.venv/bin/python -m pytest tests/store/test_db_retry.py
./.venv/bin/python -m pytest tests/store/test_pathing.py
./.venv/bin/python -m pytest tests/store/test_sqlite_validation.py
./.venv/bin/python -m pytest tests/store/test_sqlite_runtime.py
./.venv/bin/python -m pytest tests/store/test_sql_runner.py
./.venv/bin/python -m pytest tests/store/test_backend_contract.py
./.venv/bin/python -m pytest tests/store/test_sql_namespace.py
./.venv/bin/python -m pytest tests/store/test_sqlite_migrations.py
./.venv/bin/python -m pytest tests/store/test_state_store_contract.py
./.venv/bin/python -m pytest tests/store/test_store_factory.py
./.venv/bin/python -m pytest tests/store/test_sqlite.py
./.venv/bin/python -m pytest tests/architecture/test_store_boundaries.py
```

Run broader tests after integration:

```bash
./.venv/bin/python -m pytest tests/store tests/core/test_memory.py tests/core/test_context.py
./.venv/bin/python -m pytest tests/commands/test_memory_commands.py tests/cli/test_cli.py
./.venv/bin/python -m pytest tests
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests
```

If `.venv` is missing, run:

```bash
uv sync --all-extras
```

Do not assume global `pytest`, `mypy`, or `ruff`.

## 10. Verification And Gates

Per-task gates:

- Each task's targeted tests pass before moving to the next task.
- No task leaves both old and new implementations active for the same store
  behavior.
- Any spec change lands before code that relies on it.
- Any public output shape change has matching spec and tests in the same task.

Final gates before claiming done:

- `./.venv/bin/python -m pytest`
- `./.venv/bin/mypy engram`
- `./.venv/bin/ruff check engram tests`
- Manual inspection that `engram/core/memory.py` does not import
  `SQLiteStateStore`.
- Manual inspection that `engram/store/core.py` does not import `sqlite3`.
- Manual inspection that new store implementation code contains no `SELECT *`.
- Manual inspection that docs/specs/plans/implementation notes are consistent.

Observable success:

- A new vault initializes normally.
- An existing current vault opens normally.
- A known old development vault fixture migrates on open.
- Status still reports coherent state after migration.
- Search/rebuild still work after migration.
- Unsupported `ENGRAM_BACKEND=pg` fails clearly instead of silently using
  SQLite.

Post-merge watch points:

- User reports of "vault not initialized" for old Engram dev vaults should
  decrease.
- Any report of wrong-magic rejection should be inspected carefully; it may be
  protecting the user from pointing Engram at the wrong DB.
- Any report of migration failure should include schema version, detected
  shape, and path, without dumping memory text.

## 11. Independent Review Loop

Before implementation:

Use an independent review pass on this plan. Suggested prompt:

```text
Read docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md.
Read the referenced Engram specs and the current files engram/store/sqlite.py,
engram/core/memory.py, engram/_constants.py, and tests/store/test_sqlite.py.
Also inspect the referenced simplebroker backend files.

Review only. Do not implement. Look for errors, bad ideas, missing invariants,
over-broad abstractions, unclear task boundaries, and places where a
zero-context implementer could make a wrong but plausible choice. Answer:
Could you implement this confidently and correctly if asked? If not, what must
change in the plan?
```

During implementation:

- If the reviewer flags ambiguity, update the plan before coding that area.
- If a task forces a new dependency, stop and re-plan.
- If PG implementation becomes necessary to finish a task, stop and re-plan.
- If a migration cannot preserve data in tests, stop and re-plan.

After implementation:

- Run a second independent review focused on code and tests.
- The reviewer should prioritize:
  - migration safety
  - backend boundary drift
  - weak tests or over-mocking
  - public shape changes
  - accidental SQLite assumptions in backend-neutral code

## 12. Fresh-Eyes Self Review

Review pass 1:

- Risk found: the phrase "backend plugin" could lead an implementer to copy
  simplebroker's full plugin system and entry-point loading. Fixed by naming an
  internal `StateBackend` protocol and making entry-point discovery out of
  scope.
- Risk found: path hardening could reject valid absolute vault paths. Fixed by
  limiting safe component validation to generated DB names and relative
  components.
- Risk found: current specs reject migrations. Fixed by making spec updates the
  first task and calling out the exact conflicting clauses.
- Risk found: future PG could cause over-generalization. Fixed by making PG
  implementation out of scope and using unsupported-backend failure as the only
  PG-related runtime behavior.

Review pass 2:

- Risk found: `SELECT *` would work in SQLite and fail subtly for PG row
  mapping. Fixed by adding explicit ordered column requirements and architecture
  tests.
- Risk found: migration adoption of no-magic SQLite files could be too broad.
  Fixed by requiring exact known Engram table signatures before adopting any
  no-magic legacy DB.
- Risk found: old `SQLiteStateStore` and new core could become parallel paths.
  Fixed by requiring `SQLiteStateStore` to become a thin wrapper and banning
  duplicated SQL behavior.
- Risk found: tests could over-mock. Fixed by naming real SQLite requirements
  in each storage task and allowing fakes only for retry helper callables and
  env vars.

Review pass 3:

- Risk found: dropping the old queue-shaped `processing_status` column is a
  one-way door. Fixed by requiring SQLite 3.35.0, using a direct `DROP COLUMN`
  migration instead of a table rebuild, and requiring data-preservation,
  rollback, and verification tests.
- Risk found: adding generic status fields now might create public-shape churn.
  Fixed by keeping status behavior stable unless a task explicitly updates spec
  and CLI tests in the same change.
- Risk found: this could drift into an ORM or external migration framework.
  Fixed by banning new dependencies and naming the local runner/backend/schema
  path as the intended shape.
- Risk found: "port simplebroker tests" was implied across task-level test
  sections but not stated as a global requirement. Fixed by adding the
  simplebroker test source list and a test port matrix.

Decision after review:

The plan still matches the discussed direction: port simplebroker's backend
portability and battle-tested SQLite handling into Engram's state store, adapt
it to Engram's memory domain, and stop before PG implementation. No material
direction change is needed before implementation.
