# Local App Surface

Status: Active

This spec defines the usable local-app surface layered on top of Engram's
memory model, retrieval path, and embedded Weft runtime.

## 1. Purpose and Scope

This spec governs the local single-user app surface for daily local use.

In scope:
- vault init and open behavior
- schema versioning and vault metadata
- embedded Weft runtime bootstrap as part of a vault
- status inspection
- one-way index rebuild from SQLite into LanceDB
- shared CLI and Python API ownership for those behaviors

Out of scope:
- Postgres
- hosted or multi-user behavior
- deletion semantics
- import/export
- blob ingestion
- Weft-internal task semantics

## 2. Mental Model

The local app has three cooperating layers:

- SQLite owns durable memory state and metadata
- LanceDB owns the rebuildable search projection
- embedded Weft owns deferred task execution for the vault

`init` creates a vault. `open` and read commands target an existing vault and
must not silently create a new one. `vault status` tells the user whether
domain lag, failure, or index drift exists. `vault rebuild-index` restores
search state from SQLite without treating LanceDB as a peer.

## 3. Requirements

### Vault Lifecycle

- [LAS-1] `init` must create an initialized vault with:
  - a vault directory
  - a SQLite state store
  - a LanceDB index location
  - an embedded Weft project rooted so its metadata directory is the vault
  - an embedded Weft sqlite broker at `<vault>/broker.db` on the default local
    path
  - explicit vault metadata including schema version
- [LAS-1.1] `init` must leave the vault able to submit Engram-owned internal
  TaskSpecs without depending on an ambient project-level Weft installation.
- [LAS-2] Non-init open behavior must not silently create a new vault.
- [LAS-3] A directory without an initialized Engram state store must fail open
  clearly rather than being treated as a new vault.
- [LAS-4] Known older Engram vault shapes must migrate forward on open through
  explicit, ordered, transactional migrations. Unknown, corrupted,
  wrong-identity, or newer-than-supported vault shapes must fail open clearly.

### Metadata and Versioning

- [LAS-5] The SQLite store must record an explicit schema version.
- [LAS-6] The SQLite store must record durable vault metadata sufficient to
  inspect lifecycle state later.
- [LAS-7] Schema, versioning, and on-disk layout changes in this phase must
  define one current shape plus explicit forward migrations for known older
  Engram shapes. Migration logic must be source-of-truth only and must not use
  LanceDB to reconstruct SQLite state.

### Status Surface

- [LAS-8] The app must expose a status surface through both Python and CLI.
- [LAS-9] Status must report enough information to inspect:
  - vault path
  - SQLite path
  - LanceDB path
  - embedded Weft location or broker path
  - schema version
  - item counts
  - Engram-owned domain processing counts or lag projections
  - indexed item count
  - index row count
- [LAS-10] Status must make failed or stuck downstream work visible enough to
  inspect the affected item, recorded error, and last known task correlation
  when available.
- [LAS-11] Status must not mutate access scores, processing state, or item
  content.

### Recovery and Rebuild

- [LAS-12] The app must expose a one-way index rebuild path through both
  Python and CLI.
- [LAS-13] Rebuild must restore the LanceDB projection from authoritative
  SQLite item state.
- [LAS-14] Rebuild must not merge data from LanceDB back into SQLite.
- [LAS-15] Rebuild may refresh SQLite `indexed_at` state after a successful
  restore, but it must not invent, rewrite, or delete memory items.
- [LAS-16] Missing or stale LanceDB state must be recoverable without manual
  SQLite edits.

### Execution Boundary

- [LAS-17] Deferred execution must be owned by embedded Weft rather than an
  Engram-owned task substrate.
- [LAS-18] Engram may record domain processing projections and Weft correlation
  metadata, but it must not introduce a second durable queue or a shadow task
  system.
- [LAS-19] Any local repair helper must wrap the same domain operation used by
  the Weft task path.

### Public Surfaces

- [LAS-20] The Python API and CLI must share the same core logic for init/open,
  status, rebuild, and any local repair behavior.
- [LAS-21] The minimum local-app CLI in this phase must include:
  - `init`
  - `vault status`
  - `vault rebuild-index`
  - `vault process`
  - existing write, search, recall, and context commands that remain in scope
- [LAS-29] The Python API must expose explicit `init` and `open` entry points
  that match the local vault lifecycle rules.
- [LAS-30] The package root should re-export the stable local-user types and
  errors needed to use the app without reaching into private modules.

## 4. Invariants and Constraints

- [LAS-22] SQLite remains authoritative for memory state.
- [LAS-23] LanceDB remains rebuildable.
- [LAS-24] Opening a vault and recovering a vault are different actions.
- [LAS-25] Recovery features should prefer inspection and restore over manual
  storage surgery.

## 5. Interfaces and Data Contracts

Minimum Python surface:

```text
Engram.init(path?) -> Engram
Engram.open(path?) -> Engram
Engram.status(...) -> VaultStatus
Engram.rebuild_index() -> RebuildResult
```

Minimum new CLI surface:

```text
engram vault status
engram vault rebuild-index
```

Status output may be text or structured data, but it must expose the fields
required by [LAS-9] and [LAS-10].

Foundation ownership, command/client roles, access-score mutation tables, and
CLI JSON output contracts are governed more specifically by
`docs/specs/15-foundation-contracts-and-invariants.md`.

## 6. Failure Modes and Edge Cases

- [LAS-26] If a vault path does not exist, non-init open must fail clearly.
- [LAS-27] If a directory exists but is not an initialized vault, non-init
  open must fail clearly.
- [LAS-28] If LanceDB is missing or empty while SQLite has durable items, that
  is recoverable index drift, not authoritative data loss.
- [LAS-31] Rebuild should leave the app usable even if there are zero items.

## 7. Verification Expectations

Changes governed by this spec should be proven with:
- init/open lifecycle tests
- current metadata/versioning tests
- migration tests for known older Engram vault shapes
- rejection tests for unknown, corrupted, wrong-identity, and newer vault shapes
- status tests covering lagging or failed downstream work
- rebuild tests showing LanceDB restoration from SQLite
- CLI tests for `vault status`, `vault process`, and `vault rebuild-index`
- proof that the embedded Weft runtime is initialized and isolated per vault

## Related Plans

- `docs/plans/2026-04-16-basic-working-app-plan.md`
- `docs/plans/2026-04-16-initial-skeleton-validation-plan.md`
- `docs/plans/2026-04-16-weft-background-and-llm-integration-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
- `docs/plans/2026-04-22-engram-foundation-excellence-plan.md`
- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`
- `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`
- `docs/plans/2026-04-23-api-vocabulary-process-set-importance-plan.md`
