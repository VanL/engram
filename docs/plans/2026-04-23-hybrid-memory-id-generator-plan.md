# 2026-04-23 Hybrid Memory ID Generator Plan

Status: Proposed

## 1. Goal

Port the applicable parts of SimpleBroker's hybrid timestamp generator into
Engram as an Engram-native memory ID allocator. Replace the current
check-then-increment `_allocate_id()` behavior with a state-store-backed hybrid
clock that gives unique, monotonic, int64-compatible, timestamp-like memory IDs
across concurrent local writers. Keep the change narrow: this is an ID
allocation and storage-metadata change, not a retrieval redesign, public API
expansion, or Postgres implementation.

## 2. Source Documents

Source specs:

- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-3], [MM-4],
  [MM-5], [MM-6], [MM-7], [MM-9], [MM-12], [MM-13], [MM-19],
  [MM-20], [MM-21], [MM-25], [MM-26]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1],
  [MWS-2], [MWS-3], [MWS-4], [MWS-13], [MWS-27], [MWS-30],
  [MWS-31], [MWS-33], [MWS-34]
- `docs/specs/12-local-app-surface.md` [LAS-4], [LAS-5], [LAS-7],
  [LAS-10], [LAS-12], [LAS-13], [LAS-22], [LAS-24], [LAS-26],
  [LAS-27], [LAS-28]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1],
  [FCI-2], [FCI-8], [FCI-10], [FCI-24], [FCI-27], [FCI-30],
  [FCI-32], [FCI-35], [FCI-36], [FCI-38], [FCI-43], [FCI-44]

Existing implementation notes and plans:

- `docs/implementation/04-minimum-memory-slice.md`
- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`
  - This plan supersedes only the older plan's instruction to keep
    `_allocate_id` behavior intact. Do not reinterpret the older foundation
    plan as a reason to preserve the check-then-insert allocator.

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

SimpleBroker reference files. Read these as calibration material. Do not import
private SimpleBroker modules from Engram.

- `../simplebroker/simplebroker/_timestamp.py`
  - Port the hybrid timestamp generation idea: physical time with low bits used
    as a logical counter, cached last timestamp, fork detection, bounded retry,
    and persisted compare-and-set.
- `../simplebroker/simplebroker/_constants.py`
  - Port only applicable timestamp constants. Do not copy queue, CLI, alias, or
    path constants.
- `../simplebroker/simplebroker/_backends/sqlite/plugin.py`
  - Use the `advance_last_ts` pattern as the compare-and-set reference.
- `../simplebroker/simplebroker/_sql/sqlite.py`
  - Note that SimpleBroker's `meta.value` is `INTEGER`. Engram's `vault_meta`
    value is `TEXT`, so do not blindly copy SQL that compares a metadata value.
- `../simplebroker/simplebroker/db.py`
  - Use `generate_timestamp()` only to understand how the generator is owned by
    the state layer and kept out of caller-facing write transactions.
- `../simplebroker/tests/test_timestamp_helpers.py`
- `../simplebroker/tests/test_timestamp_edge_cases.py`
- `../simplebroker/tests/test_timestamp_resilience.py`
- `../simplebroker/tests/test_fork_safety.py`
- `../simplebroker/tests/test_concurrency.py`

## 3. Current Context And Key Files

Read these files before editing. Do not infer ownership from names alone.

### Engram ID Allocation Today

- `engram/core/memory.py`
  - `Engram.record()` currently calls `time.time_ns()`, passes that timestamp
    into `self._allocate_id(created_at)`, builds a `MemoryItem`, and then calls
    `self._store.put_item(item)`.
  - `_allocate_id()` checks `self._store.get_item(candidate)` and increments in
    memory until it finds a free integer.
  - This is a check-then-insert race if two writers allocate the same candidate
    before either insert commits.
  - `repair_item()` and `process_item_operation()` already have a processing
    lock for indexing and coalescing. Do not reuse that lock for `record()`;
    ID allocation belongs in the state store, not in the domain object.

- `engram/store/core.py`
  - `StateStoreCore.create_summary_item()` currently has its own `_allocate_id()`
    with the same check-then-insert behavior.
  - This is a second allocator path. The port must remove this duplication.
  - `StateStoreCore` already owns backend-neutral SQL operations through
    `SQLRunner`. The new generator must live in
    `engram/store/id_generator.py`, below the domain layer, not in
    `engram.core`.

- `engram/store/base.py`
  - This is the `StateStore` protocol that `Engram` depends on.
  - Add only the narrow method needed by the domain layer:
    `allocate_memory_id(physical_ns: int) -> int`.
  - Do not expose SQL runners, SQLite details, or generator internals through
    this protocol.

- `engram/store/sqlite.py`
  - This class is the public SQLite-backed state-store adapter.
  - It delegates to `StateStoreCore`. Add any new protocol method here as a
    thin delegate only.

- `engram/store/db.py`
  - Contains `SQLRunner`, `SQLiteRunner`, retry handling, fork reset, and
    backend-neutral error translation.
  - Reuse `SQLRunner.run()` and existing store exceptions. Do not open a raw
    `sqlite3` connection from the ID generator.

### Engram Schema Today

- `engram/store/_sql/sqlite.py`
  - Defines the current SQL namespace and table creation strings.
  - `vault_meta.value` is `TEXT`, which is appropriate for `state_magic` but
    unsafe for numeric compare-and-set unless every SQL comparison casts and
    validates carefully.
  - Add a dedicated typed ID clock table here instead of storing
    `last_memory_id` in `vault_meta`.

- `engram/store/backends/sqlite/schema.py`
  - Owns schema initialization, known-shape migrations, metadata verification,
    index verification, and foreign-key validation.
  - This is where the schema version bump, typed ID clock table creation,
    migration seeding, and verification belong.

- `engram/_constants.py`
  - Holds ID-related constants and current SQLite schema version.
  - Current `TID_LENGTH` says SimpleBroker hybrid compatibility but the system
    still uses plain `time.time_ns()` candidates. Update this language when the
    generator lands.
  - Add hybrid ID constants here. All constants live in this file.

- `engram/_exceptions.py`
  - Prefer existing store errors:
    - `StoreDataError` for unrepresentable or out-of-range physical times or
      generated IDs.
    - `StoreIntegrityError` for missing, malformed, or unadvanceable ID clock
      state.
    - `StoreOperationalError` for retry-exhausted operational failures.
  - Do not add a new exception class unless implementation proves the existing
    store errors make tests or callers less clear.

### Current Tests

- `tests/store/test_sqlite.py`
  - Existing real SQLite state-store tests live here.
  - Add schema and migration assertions here.

- `tests/core/test_memory.py`
  - Existing `Engram.record()`, lookup, rebuild, and coalescing tests live here.
  - Add record-path ID assertions here only if they prove behavior through the
    public domain surface.

- `tests/commands/test_memory_commands.py`, `tests/client/test_client.py`,
  `tests/cli/test_cli.py`
  - These protect command, client, and CLI shapes. They should not need shape
    changes. If they do, stop and re-evaluate.

- Add `tests/store/test_memory_ids.py`
  - Use this for focused ID generator tests.
  - Pure encode/decode can be unit-tested directly.
  - Allocation, compare-and-set, migration seeding, and concurrency must use
    real SQLite via Engram's store stack.

### Code Style For This Change

- Every new Python file must start with `from __future__ import annotations`
  after the module docstring.
- Keep imports at the top of the module. Do not use late imports to work around
  avoidable design coupling.
- Import abstract collection types from `collections.abc`.
- Use `X | None`, `list[T]`, `dict[K, V]`, and `tuple[T, ...]`. Do not import
  `Optional`, `List`, or `Dict`.
- Put every new constant in `engram/_constants.py` with a short docstring.
- Keep state-store SQL strings in `engram/store/_sql/sqlite.py` unless the SQL
  is truly generator-private and cannot be shared.
- Keep all normal database access behind `SQLRunner`.
- Add comments only where they explain a non-obvious concurrency or persistence
  invariant.
- Do not introduce a generic "clock service", "repository", or backend plugin
  registry for this work. Reuse the existing store core and backend structure.

### Comprehension Checks Before Editing

The implementer must be able to answer these before writing code:

- Why is `vault_meta.value` unsafe for raw numeric compare-and-set? Answer:
  the column is `TEXT`; SQLite can perform lexicographic or type-sensitive
  comparisons unless the schema or SQL forces numeric semantics.
- Why must `created_at` remain separate from `id`? Answer: `created_at` is the
  actual item creation timestamp. The ID is timestamp-derived identity and may
  differ after low-bit clearing, logical-counter use, or collision handling.
- Why is a generated ID allowed to be skipped? Answer: ID allocation advances a
  durable clock. If insertion fails after allocation, preserving monotonic
  uniqueness matters more than gap-free IDs.
- Which layer owns ID allocation? Answer: the transactional state store. LanceDB
  stores the resulting ID as a projection only.

## 4. Design Decision

Use a dedicated typed singleton table for the ID clock:

```sql
CREATE TABLE IF NOT EXISTS memory_id_clock (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_memory_id INTEGER NOT NULL CHECK (last_memory_id >= 0)
)
```

Do not store `last_memory_id` in `vault_meta`. That would look simpler but is a
bad tradeoff because `vault_meta.value` is `TEXT`, while the ID clock needs
atomic numeric comparison under concurrency.

The generator should encode IDs like SimpleBroker's current implementation:

```text
time_base = physical_ns with the low 12 bits cleared
logical_counter = low 12 bits, range 0..4095
memory_id = time_base | logical_counter
```

This preserves the magnitude and rough sort order of `time.time_ns()` while
allowing up to 4096 generated IDs in the same 4096-nanosecond bucket. These are
nanosecond-scale hybrid timestamp IDs. Do not describe them as exact raw
nanosecond timestamps after this change.

The ID generator should:

- lazily read `memory_id_clock.last_memory_id`
- cache the last observed ID behind a `threading.Lock`
- reset cached state if `os.getpid()` changes after fork
- compute a candidate from the caller-provided `physical_ns`
- treat `physical_ns` as the initial physical timestamp for the item being
  created, then call the module clock only if counter overflow forces waiting
  for the next physical bucket
- atomically advance the clock with:

```sql
UPDATE memory_id_clock
SET last_memory_id = ?
WHERE singleton = 1
  AND last_memory_id < ?
```

- read the latest stored value and retry if another writer wins the race
- fail clearly after a small bounded retry loop instead of looping forever
- reject negative physical timestamps
- reject generated IDs `>= 2**63`

## 5. Invariants And Constraints

- IDs remain integer memory item identities shared by SQLite/PG and LanceDB.
- IDs remain unique within a vault and immutable after creation.
- Existing memory item IDs must never be rewritten during migration.
- Existing `created_at` values must never be rewritten during migration.
- `created_at` remains the actual creation timestamp, not the decoded ID time.
- Coalescing remains additive. No tier-0 moments may be deleted or rewritten.
- SQLite remains authoritative. LanceDB remains a rebuildable projection.
- `record()` still returns only after the moment is durably stored in SQLite
  and downstream processing need is recorded.
- `record()` still does not wait for embedding, LanceDB indexing, or coalescing.
- `engram record TEXT --json` still returns exactly `{"id": <int>}`.
- `engram moment|episode|arc ID --json` shape does not change.
- Lookup must continue to accept existing integer IDs, including small integer
  IDs in tests and legacy development fixtures. Do not enforce `TID_LENGTH` on
  lookup.
- Do not add a public `Engram.generate_id()`, CLI command, or client method.
  SimpleBroker exposes timestamp generation publicly because queues use it for
  checkpoints. Engram does not need that surface now.
- Do not port SimpleBroker timestamp parsing, `--since`, exact message-ID
  validation, conflict metrics, queue resync metrics, or watcher cache logic.
- Do not add a new dependency.
- Do not add SQLAlchemy, an ORM, a repository abstraction, or a plugin system.
- Do not use LanceDB to allocate, validate, or repair IDs.
- Do not retain `_allocate_id()` as a fallback compatibility path.
- Do not use `SELECT *` in new store code.
- Do not mock SQLite for allocation tests. The atomic compare-and-set must be
  proven against real SQLite.

## 6. Rollout, Rollback, And One-Way Doors

This change bumps the SQLite state-store schema. That is a one-way door for a
vault once opened by the new runtime.

Rollout sequencing:

1. Land schema support and migration tests before replacing allocation callers.
2. Land the generator with real SQLite tests before using it in `record()`.
3. Switch `record()` and summary creation to the generator in the same change.
4. Run full tests and static gates before dogfooding against an existing vault.

Rollback:

- Code rollback is straightforward before a migrated vault is opened.
- After a vault is migrated to the new schema version, an older Engram runtime
  should reject it as newer-than-supported. That is acceptable, but it means
  rollback for user data requires restoring a vault snapshot or keeping the new
  runtime.
- Do not attempt to downgrade the schema or delete `memory_id_clock` in
  rollback code.

Compatibility with existing IDs:

- Older Engram vaults contain plain `time.time_ns()` IDs. After migration, the
  generator seeds `memory_id_clock` from `MAX(memory_items.id)` and treats that
  max value as the last hybrid ID.
- This is acceptable. The low 12 bits of an older raw timestamp become the
  logical-counter component for future allocation. Existing IDs remain valid and
  immutable.
- If a legacy max ID has a high low-bit value, the next allocation may advance
  the physical bucket before returning. That is better than rewriting IDs.

Fatal versus best-effort failures:

- ID allocation failure is fatal. `record()` must not store a moment without a
  valid allocated ID.
- Summary ID allocation failure is fatal for that coalescing operation. The
  original lower-tier items remain durable and unmodified.
- Background task submission failure after a successful `record()` remains the
  current best-effort path: record the processing failure state and return the
  stored moment ID.

Stop and re-plan if:

- the implementation needs a public API addition
- you are tempted to store numeric clock state in `vault_meta.value`
- any code path still calls an `_allocate_id()` check-then-insert loop
- the schema migration would rewrite existing item IDs or `created_at`
- tests require mocking the store layer to prove normal allocation behavior
- the plan starts turning into a Postgres implementation

## 7. Bite-Sized Tasks

### 1. Establish Red Tests For The ID Clock Schema

Outcome: Tests fail because the current schema has no typed ID clock table.

Files to touch:

- `tests/store/test_sqlite.py`

Read first:

- `engram/store/_sql/sqlite.py`
- `engram/store/backends/sqlite/schema.py`
- `tests/store/test_sqlite.py`

Test work:

- Add a test that a newly initialized vault contains `memory_id_clock`.
- Assert its columns are exactly:
  - `singleton`
  - `last_memory_id`
- Assert it contains exactly one row:
  - `singleton = 1`
  - `last_memory_id = 0` for a brand-new vault with no items
- Add a migration test for the current pre-change schema version:
  - create a v5-shaped vault without `memory_id_clock`
  - insert at least two memory items with known IDs
  - open through `SQLiteStateStore`
  - assert schema version was bumped
  - assert `last_memory_id == max(existing ids)`
  - assert all existing item IDs and `created_at` values are unchanged

Do not mock:

- SQLite
- schema initialization
- migration open path

Done signal:

- The new tests fail for the expected reason: missing `memory_id_clock` or old
  schema version.

Stop and re-evaluate if:

- the test requires importing private migration helpers instead of opening the
  real store
- the test rewrites IDs to make assertions pass

### 2. Add Hybrid ID Constants

Outcome: Constants exist in the repo's canonical constants module with precise
docstrings.

Files to touch:

- `engram/_constants.py`

Read first:

- `../simplebroker/simplebroker/_constants.py`
- current `engram/_constants.py` ID and storage sections

Implementation notes:

- Add constants near `TID_LENGTH`:
  - `MEMORY_ID_LOGICAL_COUNTER_BITS: Final[int] = 12`
  - `MEMORY_ID_LOGICAL_COUNTER_MASK: Final[int] = (1 << MEMORY_ID_LOGICAL_COUNTER_BITS) - 1`
  - `MEMORY_ID_MAX_LOGICAL_COUNTER: Final[int] = 1 << MEMORY_ID_LOGICAL_COUNTER_BITS`
  - `MEMORY_ID_WAIT_FOR_NEXT_INCREMENT: Final[float] = 0.000_001`
  - `MEMORY_ID_MAX_WAIT_ITERATIONS: Final[int] = 100_000`
  - `SQLITE_MAX_INT64: Final[int] = 2**63`
- Add `MEMORY_ID_CLOCK_TABLE: Final[str] = "memory_id_clock"` only if it avoids
  repeated string literals in schema and tests.
- Update the `TID_LENGTH` docstring to say generated IDs are expected to be
  19-digit, nanosecond-scale hybrid timestamp IDs compatible with
  SimpleBroker's current format.

Testing:

- No standalone runtime test is needed for constants.
- Existing import and static checks must pass later.

Done signal:

- Constants are centralized in `_constants.py`; no duplicate magic numbers are
  introduced elsewhere.

Stop and re-evaluate if:

- constants start pulling queue, watcher, or timestamp parsing concerns from
  SimpleBroker.

### 3. Implement The Typed ID Clock Schema And Migration

Outcome: The schema tests from Task 1 pass.

Files to touch:

- `engram/store/_sql/sqlite.py`
- `engram/store/backends/sqlite/schema.py`
- `engram/_constants.py`
- `tests/store/test_sqlite.py`

Read first:

- Task 1 tests
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-44]

Implementation notes:

- Bump `CURRENT_SQLITE_SCHEMA_VERSION` by one.
- Add SQL namespace strings:
  - `CREATE_MEMORY_ID_CLOCK`
  - `INIT_MEMORY_ID_CLOCK_EMPTY`
  - `SEED_MEMORY_ID_CLOCK_FROM_ITEMS`
- Create the table during current-schema creation after `memory_items` exists.
- Seed new vaults with `last_memory_id = 0`.
- During any known-schema migration, create and seed the clock with:

```sql
INSERT INTO memory_id_clock (singleton, last_memory_id)
SELECT 1, COALESCE(MAX(id), 0)
FROM memory_items
ON CONFLICT(singleton) DO NOTHING
```

- Ensure the migration is idempotent. Reopening a migrated vault must not lower
  or overwrite `last_memory_id`.
- Add `memory_id_clock` to required current-schema verification.
- Verify:
  - table exists
  - columns are exactly the intended shape
  - exactly one singleton row exists
  - `last_memory_id >= COALESCE(MAX(memory_items.id), 0)`
- Reject malformed clock state with `VaultNotInitializedError` or
  `StoreIntegrityError`. Prefer:
  - wrong shape or missing singleton: `VaultNotInitializedError`
  - impossible relational state, such as `last_memory_id < MAX(id)`:
    `StoreIntegrityError`

Testing:

- Run:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_sqlite.py -k "schema or migration or clock"
```

Done signal:

- New schema and migration tests pass.
- Existing store migration tests still pass.

Stop and re-evaluate if:

- the migration rewrites item IDs or `created_at`
- schema verification accepts malformed clock state because it is convenient
- the implementation stores numeric clock state in `vault_meta.value`

### 4. Add `MemoryIdGenerator`

Outcome: A focused generator module ports the applicable SimpleBroker behavior
without queue-specific code.

Files to touch:

- add `engram/store/id_generator.py`
- add `tests/store/test_memory_ids.py`
- do not touch `engram/_exceptions.py` unless the implementation proves the
  existing store exceptions make the failure contract materially less clear

Read first:

- `../simplebroker/simplebroker/_timestamp.py`
- `engram/store/db.py`
- `engram/_exceptions.py`

Implementation notes:

- Add `from __future__ import annotations`.
- Keep imports at module top.
- Use `threading.Lock`, `os.getpid()`, `random`, and `time`.
- Add `MemoryIdGenerator` with:
  - `__init__(runner: SQLRunner) -> None`
  - `generate(physical_ns: int) -> int`
  - `get_cached_last_id() -> int`
  - `refresh_last_id() -> int`
  - private `_encode_hybrid_id(physical_ns: int, logical: int) -> int`
  - private `_decode_hybrid_id(item_id: int) -> tuple[int, int]`
  - private `_next_components(physical_ns: int) -> tuple[int, int]`
  - private `_advance_last_id(new_id: int) -> bool`
  - private `_read_last_id() -> int`
  - private `_ensure_pid() -> None`
- If tests need encode/decode directly, expose module-level functions instead
  of encouraging tests to reach into too many private methods:
  - `encode_hybrid_memory_id(physical_ns: int, logical: int) -> int`
  - `decode_hybrid_memory_id(item_id: int) -> tuple[int, int]`
- Use the existing `SQLRunner`; do not import `sqlite3`.
- This first implementation may use SQLite-specific clock SQL because the only
  implemented state backend is SQLite and Postgres is out of scope. Keep that
  SQL isolated in `MemoryIdGenerator` or in `engram/store/_sql/sqlite.py`; do
  not scatter it through `StateStoreCore`.
- Use the typed `memory_id_clock` table:

```sql
SELECT last_memory_id
FROM memory_id_clock
WHERE singleton = 1
```

```sql
UPDATE memory_id_clock
SET last_memory_id = ?
WHERE singleton = 1
  AND last_memory_id < ?
```

- After the update, check success using `SELECT changes()` for SQLite.
- Do not use `RETURNING` unless the SQL namespace already supports it for the
  current backend. SQLite version supports it, but current Engram store code
  does not rely on it.
- Retry a small bounded number of times, as SimpleBroker does. Six attempts is
  acceptable.
- On a lost race, read the latest stored ID, update the cache, and retry.
- On logical-counter overflow, wait for the physical clock bucket to advance
  using bounded sleep with jitter and the module's real clock. If it cannot
  advance, raise a store error.
- If `physical_ns < 0`, raise `StoreDataError`.
- If `new_id >= SQLITE_MAX_INT64`, raise `StoreDataError`.
- If the singleton row is missing, malformed, or cannot be read, raise
  `StoreIntegrityError`.

Tests to port or adapt:

- From `test_timestamp_helpers.py`:
  - generator returns ints
  - repeated generation is monotonic
- From `test_timestamp_edge_cases.py`:
  - magnitude preservation
  - encode/decode round trip
  - max logical counter round trip
  - negative physical timestamp rejection
  - far-future int64 rejection
  - fork reinitialization resets cached state
  - exhausted compare-and-set retries fail clearly
- Keep parser tests out. Engram is not adding timestamp parsing.

Anti-mocking rule:

- Use a real `SQLiteStateStore` or real `SQLiteRunner` for normal allocation
  tests.
- A tiny fake runner is acceptable only for an impossible edge path such as
  forced compare-and-set exhaustion, and that test must be secondary to real
  SQLite proofs.
- Mocking `time.time_ns` or passing a fixed `physical_ns` is acceptable because
  physical time is nondeterministic.

Testing:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_memory_ids.py
```

Done signal:

- New generator tests pass.
- The module has no dependency on SimpleBroker or queue concepts.

Stop and re-evaluate if:

- generator behavior depends on item insertion succeeding
- the generator opens its own SQLite connection
- tests prove only method calls on a fake runner and never the real SQLite CAS

### 5. Add A Narrow State Store Allocation Method

Outcome: The state store owns ID allocation through one canonical method.

Files to touch:

- `engram/store/base.py`
- `engram/store/core.py`
- `engram/store/sqlite.py`
- `tests/store/test_sqlite.py`
- `tests/store/test_memory_ids.py`

Read first:

- `engram/store/base.py`
- `engram/store/sqlite.py`
- `engram/store/core.py`

Implementation notes:

- Add to `StateStore` protocol:

```python
def allocate_memory_id(self, physical_ns: int) -> int:
    """Allocate a unique memory item ID for this vault."""
```

- Add `StateStoreCore.allocate_memory_id()` that delegates to a
  `MemoryIdGenerator` instance.
- Construct the generator once in `StateStoreCore.__init__`.
- Add `SQLiteStateStore.allocate_memory_id()` as a thin delegate.
- Keep the method internal to store/domain code. Do not add client, CLI, or
  command wrappers.

Tests:

- Add a real SQLite test:
  - call `allocate_memory_id(base)` several times on one store
  - assert strict increase
  - close and reopen the store
  - call `allocate_memory_id(base)` again
  - assert the new ID is greater than the previous ID even though the physical
    timestamp input is unchanged
- Add a cross-handle test:
  - open two `SQLiteStateStore` instances for the same vault
  - call `allocate_memory_id(base)` from both
  - assert unique, increasing IDs

Done signal:

- Store-level allocation tests pass with real SQLite.

Stop and re-evaluate if:

- allocation requires a domain `Engram` object
- callers outside store/domain need to know about `MemoryIdGenerator`

### 6. Replace Moment Allocation In `Engram.record()`

Outcome: New moments use the canonical store-backed ID allocator.

Files to touch:

- `engram/core/memory.py`
- `tests/core/test_memory.py`
- `tests/commands/test_memory_commands.py` only if a command-shape regression
  appears while running the neighboring gates

Read first:

- `engram/core/memory.py` `record()`
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1] through [MWS-4]

Implementation notes:

- Keep this ordering:

```python
created_at = time.time_ns()
item_id = self._store.allocate_memory_id(created_at)
item = MemoryItem(id=item_id, tier=TIER_MOMENT, text=stripped, created_at=created_at)
self._store.put_item(item)
...
return item.id
```

- Remove `Engram._allocate_id()`.
- Do not hold `self._processing_lock()` in `record()`.
- Do not submit background work until after `put_item()` succeeds.
- If ID allocation succeeds and `put_item()` fails, allow the ID gap. Do not
  try to decrement the clock.

Tests:

- Add or update a core test proving:
  - `record()` returns an int ID
  - lookup by that ID returns the stored moment
  - `item.created_at` is present and remains independent from ID equality
  - the returned ID is 19 digits under normal current timestamps
- Add a concurrent write test through the public domain surface:
  - initialize one vault
  - open multiple `Engram` instances with `submit_background=False`
  - write multiple records from threads
  - assert all returned IDs are unique
  - assert sorted returned IDs are strictly increasing
  - do not assert that ID order matches thread completion order; concurrency
    makes completion order nondeterministic
  - assert all items can be looked up
- Use deterministic embeddings only if the test invokes indexing. For pure
  record/lookup with `submit_background=False`, no embedding mock is needed.

Testing:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/core/test_memory.py -k "record or concurrent"
```

Done signal:

- Core record tests pass.
- No `_allocate_id()` remains in `engram/core/memory.py`.

Stop and re-evaluate if:

- command, client, or CLI output shapes change
- the test needs sleeps to avoid duplicate IDs
- background submission starts before the moment is durable

### 7. Replace Summary Item Allocation

Outcome: Higher-tier summaries use the same canonical ID allocator as moments.

Files to touch:

- `engram/store/core.py`
- `tests/store/test_sqlite.py`
- `tests/core/test_memory.py`
- `tests/core/test_context.py` if context or arc tests expose ordering issues

Read first:

- `engram/store/core.py` `create_summary_item()`
- `engram/core/memory.py` `_coalesce_available_tier_operation()`
- `docs/specs/10-minimum-memory-model.md` [MM-9] through [MM-14]

Implementation notes:

- In `StateStoreCore.create_summary_item()`, replace:

```python
id=self._allocate_id(created_at)
```

with:

```python
id=self.allocate_memory_id(created_at)
```

- Remove `StateStoreCore._allocate_id()`.
- Keep parent-child edge insertion in the same transaction as summary item
  insertion.
- Do not change coalescing window selection or summary generation.

Tests:

- Add a store test:
  - create moments with known existing IDs
  - create an episode with `created_at` less than or equal to an existing max ID
  - assert the episode ID is still greater than the existing clock
  - assert ordered children are unchanged
- Existing coalescing and context tests should still pass.

Testing:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_sqlite.py -k "summary or episode or children or clock"
./.venv/bin/python -m pytest tests/core/test_memory.py tests/core/test_context.py
```

Done signal:

- No `_allocate_id()` remains in `engram/store/core.py`.
- Summary creation tests pass.

Stop and re-evaluate if:

- summary creation mutates children
- summary allocation bypasses the same generator as moments

### 8. Port Applicable Concurrency And Fork Tests

Outcome: Engram has real proof for the race this plan is fixing.

Files to touch:

- `tests/store/test_memory_ids.py`
- `tests/core/test_memory.py`

Read first:

- `../simplebroker/tests/test_timestamp_resilience.py`
- `../simplebroker/tests/test_fork_safety.py`
- `../simplebroker/tests/test_concurrency.py`
- `engram/store/db.py`

Tests to add:

- Real SQLite concurrent allocator test:
  - create one vault
  - open multiple store instances against it
  - call `allocate_memory_id()` with the same `physical_ns` from each worker
  - assert no duplicates
  - assert all generated IDs are greater than the seeded clock
- Public record concurrency test:
  - multiple `Engram` instances, same vault, `submit_background=False`
  - concurrent `record()` calls
  - assert unique IDs and durable lookup
- Fork/cache reset test:
  - use the generator or store in a controlled test
  - simulate PID change if true `os.fork()` would be too brittle in the test
    environment
  - assert the generator refreshes from persisted clock before generating again
- Clock rollback test:
  - allocate an ID with a high physical timestamp
  - allocate again with a lower physical timestamp
  - assert the second ID is still greater than the first
- Counter overflow test:
  - set persisted `last_memory_id` to a base with logical counter 4095
  - generate with the same physical base
  - patch only the module's time source so the first overflow check sees the old
    bucket and a later check sees an advanced bucket
  - assert the returned ID decodes to the advanced physical bucket with logical
    counter 0

Anti-mocking rule:

- Do not mock `SQLiteStateStore`, `StateStoreCore`, or `SQLRunner` for the main
  concurrency tests.
- Do not assert on lock calls or retry call counts as the primary proof.
- Assert on durable state: unique IDs, persisted clock, successful lookup.

Testing:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_memory_ids.py tests/core/test_memory.py -k "id or concurrent or fork or rollback"
```

Done signal:

- The new tests fail on the old allocator and pass with the hybrid generator.

Stop and re-evaluate if:

- concurrency tests are flaky
- tests pass without exercising real SQLite
- the implementation relies on process-global memory for uniqueness

### 9. Update Specs And Documentation

Outcome: Docs describe the new ID contract and storage shape accurately.

Files to touch:

- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md` if record/write-path
  language needs clarification
- `docs/specs/15-foundation-contracts-and-invariants.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `README.md`
- `AGENTS.md`
- `docs/lessons.md` only if implementation exposes a durable lesson beyond
  this plan

Read first:

- Current sections mentioning "nanosecond timestamp"
- Current related-plan sections

Required doc changes:

- Update [MM-3] from raw "nanosecond-timestamp integer ID" to
  "nanosecond-scale hybrid timestamp integer ID".
- Document that IDs are timestamp-derived and sortable, but `created_at` is the
  canonical creation timestamp.
- Document that IDs may have gaps.
- Document that existing IDs remain immutable through migration.
- Add the new plan to relevant `Related Plans` sections.
- Update README and AGENTS invariants to avoid claiming IDs are exact raw
  `time.time_ns()` values.
- Update implementation docs to say ID allocation is owned by the state store.

Do not:

- Add user-facing timestamp parsing docs.
- Document a public `generate_id` API.
- Promise global uniqueness across vaults.

Verification:

```bash
rg -n "nanosecond timestamp|nanosecond-timestamp|time\\.time_ns\\(\\).*ID|_allocate_id|last_memory_id|memory_id_clock" README.md AGENTS.md docs engram tests
```

Done signal:

- Docs no longer misdescribe generated IDs as exact raw nanosecond timestamps.
- Specs and plan backlinks are consistent.

Stop and re-evaluate if:

- docs drift into SimpleBroker queue concepts
- docs imply ID uniqueness across vaults

### 10. Clean Up Old Allocation Paths

Outcome: There is one canonical allocation path and no stale test or doc
fixtures hide the old behavior.

Files to inspect:

- `engram/core/memory.py`
- `engram/store/core.py`
- `engram/store/sqlite.py`
- `engram/store/base.py`
- `tests/`
- `docs/`

Commands:

```bash
rg -n "_allocate_id|allocate_id|time\\.time_ns\\(\\).*id|id=time\\.time_ns|created_at = time\\.time_ns\\(\\)" engram tests docs
```

Expected result:

- No `_allocate_id()` definitions remain.
- `time.time_ns()` still appears for `created_at`, `indexed_at`, processing
  timestamps, and vault creation metadata. Those are not ID allocation paths.
- Tests may still manually construct `MemoryItem(id=1, created_at=1)` for pure
  model/coalescing fixtures. Do not rewrite those unless the test is meant to
  prove generated ID behavior.

Done signal:

- The grep results are understood and contain no stale allocation path.

Stop and re-evaluate if:

- deleting `_allocate_id()` requires changing public behavior
- tests become harder to understand because simple fixtures were over-updated

## 8. Testing Plan

Test with the narrowest real proof that exercises the behavior:

- Pure encoding and decoding:
  - `tests/store/test_memory_ids.py`
  - direct function or class tests are fine
  - no database needed
- Generator compare-and-set, persistence, clock rollback, and monotonicity:
  - `tests/store/test_memory_ids.py`
  - use real SQLite through `SQLiteStateStore` or `SQLiteRunner`
  - do not mock the store layer
- Schema and migration:
  - `tests/store/test_sqlite.py`
  - use real SQLite files
  - assert durable rows and schema shape
- Public write path:
  - `tests/core/test_memory.py`
  - use `Engram` with a real vault
  - use `submit_background=False` when the test only needs durable record
    behavior
- CLI, command, and client shape regression:
  - existing command/client/CLI tests should pass unchanged
  - add targeted assertions only if a regression appears

What not to mock:

- SQLite state store
- schema migration
- `StateStoreCore`
- `SQLRunner` for normal behavior
- `Engram.record()` for public-path tests

What may be mocked or controlled:

- physical time, because it is nondeterministic
- random jitter in counter-overflow tests
- impossible compare-and-set exhaustion, as a secondary unit test only
- external Weft submission and LLM summarization, following existing test
  patterns

Specific invariants to test:

- generated IDs are ints and usually 19 digits under current timestamps
- generated IDs are strictly increasing per vault even for repeated or
  backward physical timestamps
- generated IDs are unique across multiple store handles for one vault
- existing item IDs survive migration unchanged
- `last_memory_id` or the clock row is seeded to at least `MAX(memory_items.id)`
- newly allocated IDs after migration are greater than existing IDs
- `record()` returns the durable item ID
- direct lookup by returned ID works before indexing
- summary items use the same allocator as moments
- command and CLI JSON shapes do not change

## 9. Verification And Gates

Before implementation:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_sqlite.py tests/core/test_memory.py
```

If `.venv` is missing:

```bash
. ./.envrc
uv sync --all-extras
```

Targeted gates while implementing:

```bash
./.venv/bin/python -m pytest tests/store/test_memory_ids.py
./.venv/bin/python -m pytest tests/store/test_sqlite.py
./.venv/bin/python -m pytest tests/core/test_memory.py
```

Neighboring behavior gates:

```bash
./.venv/bin/python -m pytest tests/core/test_context.py tests/test_background.py
./.venv/bin/python -m pytest tests/commands/test_memory_commands.py tests/client/test_client.py tests/cli/test_cli.py
```

Final gates before claiming completion:

```bash
./.venv/bin/python -m pytest
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests
```

Documentation and cleanup gates:

```bash
rg -n "_allocate_id|allocate_id|nanosecond timestamp|nanosecond-timestamp" engram tests README.md AGENTS.md docs
rg -n "memory_id_clock|hybrid memory ID|hybrid timestamp" README.md AGENTS.md docs engram tests
```

Success means:

- all targeted and final commands pass
- no old allocation path remains
- docs describe hybrid timestamp IDs accurately
- old generated IDs and `created_at` values are preserved in migration tests
- command, client, and CLI shapes are unchanged

Residual risk to call out if not fully proven:

- true multi-process concurrency can be slower or flakier than thread-based
  tests. If process-based tests are skipped for platform reasons, state that
  clearly and keep the real SQLite multi-handle thread test.

## 10. Independent Review Loop

Before implementation, ask an independent reviewer to review this plan and the
current code. Use this stance:

> Read `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`, then inspect
> `engram/core/memory.py`, `engram/store/core.py`, `engram/store/base.py`,
> `engram/store/sqlite.py`, `engram/store/_sql/sqlite.py`,
> `engram/store/backends/sqlite/schema.py`, `engram/store/db.py`, and
> `../simplebroker/simplebroker/_timestamp.py`. Do not implement. Look for
> errors, bad ideas, hidden schema problems, weak tests, and ambiguous tasks.
> Could a zero-context engineer implement this correctly from the plan?

The plan author must handle each review point explicitly:

- update the plan
- explain why the current direction is still right
- or mark the point out of scope with reasoning

Implementation review should happen after the code change and before merge.
The reviewer should focus on:

- no stale `_allocate_id` path
- no numeric clock state stored in `vault_meta.value`
- migration idempotence
- real SQLite concurrency proof
- command and CLI shape preservation
- docs matching code

## 11. Out Of Scope

- Postgres backend implementation
- hosted or multi-user service behavior
- public ID generation API
- CLI timestamp parsing or `--since` filters
- SimpleBroker queue, watcher, alias, vacuum, or message lifecycle behavior
- LanceDB schema changes
- retrieval ranking changes
- Weft task execution changes
- deletion or forgetting semantics
- blob ingestion
- UUID, ULID, UUID7, or Snowflake redesign beyond the SimpleBroker-compatible
  hybrid timestamp format described here

## 12. Fresh-Eyes Review Notes

Review pass 1 findings applied:

- A naive `last_memory_id` metadata key would be risky because Engram's
  `vault_meta.value` is `TEXT`. The plan now requires a dedicated typed
  singleton table instead.
- The plan now distinguishes `created_at` from ID more explicitly. Generated
  IDs are timestamp-derived, not exact raw creation timestamps.
- The plan now treats the schema version bump as a one-way door and requires a
  rollback story before implementation.
- The plan now names which SimpleBroker tests to port and which not to port, so
  the implementer does not copy queue-specific timestamp parser behavior.

Review pass 2 findings applied:

- The tasks now remove both allocator paths, not just `Engram._allocate_id()`.
- The testing plan now requires public `record()` concurrency proof as well as
  focused store-level allocation proof.
- The plan now says lookup must continue accepting existing small integer IDs,
  preventing accidental `TID_LENGTH` enforcement that would break tests and
  legacy fixtures.

Review pass 3 findings applied:

- The public record concurrency test no longer asks the implementer to compare
  ID order with nondeterministic thread completion order.
- The generator contract now explains that the caller-provided `physical_ns` is
  the initial item timestamp, while counter-overflow waiting may consult the
  module clock.
- The plan now documents how legacy raw `time.time_ns()` IDs are interpreted
  after migration without rewriting them.
- A code-style section was added so the implementer does not have to infer
  local typing, constants, SQL, or abstraction rules from scattered files.

Review pass 4 findings applied:

- The generator now explicitly rejects negative physical timestamps and
  out-of-range generated IDs.
- The plan now states that SQLite-specific clock SQL is acceptable in this
  first implementation because Postgres remains out of scope, but the SQL must
  stay isolated and not spread through domain code.

Review pass 5 findings applied:

- Soft guidance such as "likely", "maybe", and "if useful" was replaced with
  exact file and symbol decisions where the plan already had enough context.

The plan remains aligned with the original decision: port the applicable
SimpleBroker timestamp generator design into Engram. The typed clock table is a
small Engram-specific adaptation needed because Engram's metadata table has a
different type contract from SimpleBroker's `meta` table.
