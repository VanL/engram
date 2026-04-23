# Local Vault Recovery

## Purpose and Scope

This note explains the current rationale for local vault lifecycle, status, and
recovery behavior in the first usable local-app phase.

It covers:
- explicit vault initialization versus open behavior
- current metadata and schema versioning
- forward migrations for known Engram state-store schemas
- status inspection for domain lag, failure, and index drift
- one-way index rebuild from SQLite into LanceDB

## Governing Spec References

- `docs/specs/10-minimum-memory-model.md` [MM-19], [MM-20], [MM-21]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-5], [MWS-8]
- `docs/specs/12-local-app-surface.md` [LAS-2], [LAS-4], [LAS-7],
  [LAS-8], [LAS-12], [LAS-19]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-44]

## Current Design Rationale

### Open Must Not Mean Create

The skeleton favored convenience. The local app needs safer lifecycle
semantics.

Current rule:
- `init` creates a vault
- `init` also runs Weft's project init against the vault parent with embedded
  config so the Weft metadata directory is the vault itself
- non-init commands and `create=False` open existing state only
- the public Python entry points mirror this as `Engram.init(...)` and
  `Engram.open(...)`

This avoids a bad failure mode where a typo in the vault path quietly creates a
fresh empty vault and makes recovery harder to reason about.

### One Current Schema With Forward Migrations

Engram has one current runtime schema, but the opener may migrate known older
Engram SQLite shapes into that current schema before normal state operations
run. Migration is not a runtime compatibility branch: after setup completes,
the store code sees only the current shape.

The current SQLite metadata includes:
- `state_magic = "engram-state-v1"`
- `schema_version = "<current sqlite schema version>"`
- `vault_created_at = "<nanoseconds>"`

The current schema also includes the typed `memory_id_clock` singleton table.
That table owns the last allocated hybrid memory ID and is seeded from existing
item IDs during migration. Existing item IDs and `created_at` values are never
rewritten.

Known Engram development shapes migrate forward in ordered, transactional,
idempotent steps. Unknown SQLite files, corrupted files, wrong magic values,
unknown old shapes, and newer-than-supported schemas fail open clearly.

### Status Is an Operator Surface

Background lag and failure are expected states in this design, not rare
exceptions. The app therefore needs a status surface that makes these visible.

Current status is meant to answer:
- how many items exist
- how many items SQLite believes are indexed
- how many rows Lance currently has
- how many moments still need downstream work
- how many moments have a recorded failure and what the last known task
  correlation was
- whether the user should consider rebuild or repair actions

The important boundary is ownership:
- Weft owns execution and queueing
- Engram owns durable lag and failure projections plus last-known correlation

The current schema now enforces that boundary more directly. The active
`memory_items` table no longer keeps a queue-shaped `processing_status` column.
Instead it stores only:
- whether an item is indexed yet
- how many attempts have been recorded
- the last recorded error when one exists
- the last known Weft task correlation when available

### Rebuild Is One-Way

Recovery is intentionally asymmetric:
- SQLite is authoritative
- LanceDB is disposable

`rebuild_index()` restores the search projection from SQLite items. It may
refresh `indexed_at` state because the authoritative store now knows a rebuild
completed, but it does not import, merge, or trust LanceDB content.

## Key Files

| Path | Purpose |
|------|---------|
| `engram/core/memory.py` | Vault lifecycle orchestration, status surface, rebuild API |
| `engram/runtime/weft.py` | Embedded Weft init and internal task submission |
| `engram/background.py` | Weft worker callback boundary |
| `engram/store/sqlite.py` | Public SQLite store wrapper over the shared store core |
| `engram/store/core.py` | Backend-neutral state operations and processing inspection |
| `engram/store/db.py` | SQL runner, retry, transaction, and SQLite connection primitives |
| `engram/store/id_generator.py` | Hybrid timestamp memory ID allocator |
| `engram/store/backends/sqlite/schema.py` | SQLite current-schema creation, verification, and migrations |
| `engram/store/backends/sqlite/runtime.py` | SQLite runtime setup and PRAGMA policy |
| `engram/store/backends/sqlite/validation.py` | SQLite file validation before open |
| `engram/store/_sql/sqlite.py` | SQLite SQL namespace and ordered column lists |
| `engram/index/lance.py` | One-way index rebuild implementation |
| `engram/cli.py` | Local operator surfaces for `vault status` and `vault rebuild-index` |
| `tests/store/test_sqlite.py` | Lifecycle, metadata, migration, and schema regression coverage |
| `tests/store/test_memory_ids.py` | Hybrid memory ID allocation coverage |
| `tests/core/test_memory.py` | Status and rebuild behavior |
| `tests/cli/test_cli.py` | Public CLI recovery coverage |

## Current Invariants

- Open and create are different actions.
- Known Engram store schemas migrate forward before normal use.
- Unknown, corrupted, wrong-identity, and newer store schemas fail clearly.
- Migrations use SQLite state only; LanceDB never participates.
- Existing item IDs and `created_at` values are not rewritten by migration.
- SQLite remains authoritative even when LanceDB is empty or stale.
- Status is read-only.
- Rebuild is restore, not merge.
- Failed item processing stays visible after failure.
- Engram stores item state, not its own queue.
