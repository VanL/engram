# 2026-04-23 Support-Anchored Summary MIDs Plan

Status: Implemented

Verification:

- `. ./.envrc && ./.venv/bin/python -m pytest -q`
- `. ./.envrc && ./.venv/bin/mypy engram`
- `. ./.envrc && ./.venv/bin/ruff check engram tests`
- `. ./.envrc && ./.venv/bin/ruff format --check engram tests`

## 1. Goal

Change summary MID allocation so episodes, arcs, and future higher-tier
summaries are placed immediately after the memory items they summarize. Moments
remain the only real memory events. Summary items are derived projections, so
their durable identity and timeline position must be anchored to their support
set, not to the wall-clock time when back processing happened.

The rule is:

```text
moments:   MID = state-store allocated hybrid time ID
summaries: MID = first unused MID after max(child MIDs)
```

This is not a public import feature, a retrieval redesign, or a new summarizer.
It is a state-store allocation rule for derived memory items.

## 2. Source Documents

Read these before editing. The current specs are close but not yet precise
enough about derived-summary identity, so this plan includes a spec update task.

Source specs:

- `docs/specs/10-minimum-memory-model.md` [MM-3], [MM-4], [MM-5],
  [MM-6], [MM-7], [MM-9], [MM-10], [MM-11], [MM-12], [MM-13],
  [MM-19], [MM-20], [MM-21], [MM-25], [MM-25.1]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-13],
  [MWS-14], [MWS-15], [MWS-16], [MWS-17], [MWS-23], [MWS-24],
  [MWS-25], [MWS-26]
- `docs/specs/12-local-app-surface.md` [LAS-12], [LAS-13], [LAS-14],
  [LAS-15], [LAS-16], [LAS-22], [LAS-23]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1],
  [FCI-2], [FCI-35], [FCI-36], [FCI-38], [FCI-43], [FCI-44]

Related plans and context:

- `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`
  - This introduced the hybrid MID allocator and `memory_id_clock`.
  - Do not undo moment allocation or the persisted clock.
- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`
  - This explains the store/core split and SQLite runner foundation.
- `README.md`
  - Update only if its high-level ID model would mislead a reader.
- `AGENTS.md`
  - Update if the invariant list still implies summaries are allocated at
    processing time.
- `docs/agent-context/engineering-principles.md`
  - Update if needed so future agents understand summary IDs are support
    anchored.

Workflow and style:

- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/lessons.md`

## 3. Context And Key Files

### Mental Model

Engram has two durable item categories:

- Moments are real memory events. They are recorded at a physical time and get
  a state-store-allocated hybrid timestamp MID.
- Summaries are derived memory items. They summarize ordered support items.
  Their timeline identity should be a projection of the support graph.

The point of this change is to prevent delayed processing from leaking into the
memory timeline. If a user imports or records historical moments, and
coalescing runs later, the resulting episodes and arcs should sort with the
records they summarize. A summary created today for 2024 moments should not
look like a 2026 memory because the summarizer happened to run in 2026.

Important consequence: changing only the summary MID is not enough. Several
current paths order items by `created_at`, not by `id`. If summary `created_at`
continues to be `time.time_ns()` at processing time, context assembly and
recent-summary listing can still treat historical summaries as recent. For
derived summaries with children, `created_at` must be support-derived too.

Use this rule:

```text
summary.id         = first unused MID after max(child.id)
summary.created_at = max(child.created_at)
```

For empty `child_ids`, there is no support set. Keep the existing clock-based
fallback for test fixtures and future explicit summary construction, but do not
let normal coalescing create childless summaries.

### Current Code

Read these files in this order before editing.

1. `engram/store/core.py`
   - `StateStoreCore.create_summary_item()` currently builds a `MemoryItem`
     before opening its transaction.
   - It currently calls `self.allocate_memory_id(created_at)`.
   - It currently writes `last_task_updated_at=created_at` for summaries.
     That must not survive blindly once summary `created_at` becomes
     support-derived. `last_task_updated_at` is task-correlation metadata, not
     memory timeline metadata.
   - `create_episode()` and `create_arc()` are thin wrappers over
     `create_summary_item()`.
   - `put_item()` now advances `memory_id_clock` after explicit item inserts.
   - This file is the main implementation owner for support-anchored summary
     IDs.

2. `engram/store/id_generator.py`
   - Owns hybrid moment ID allocation and clock advancement helpers.
   - Keep moment allocation here.
   - Reuse `observe_existing_id()` after inserting an anchored summary so the
     clock remains at least the highest inserted MID.
   - Do not add summary-child SQL here. The generator should not know about
     `memory_items` or `memory_edges`.

3. `engram/store/base.py`
   - Protocol for state stores.
   - Update summary creation signatures here if `created_at` becomes optional.
   - Do not expose runner internals or SQL helpers.

4. `engram/store/sqlite.py`
   - Thin adapter over `StateStoreCore`.
   - Keep it thin. If you add logic here, you are probably putting it in the
     wrong file.

5. `engram/core/memory.py`
   - `_coalesce_available_tier_operation()` currently passes
     `created_at=time.time_ns()` into `create_summary_item()`.
   - This must stop for non-empty summary windows. The store should derive the
     summary timestamp from children.
   - `indexed_at` should remain processing time. That is correct because it is
     index-maintenance state, not memory timeline state.

6. `engram/_models.py`
   - `MemoryItem.created_at` currently says "Creation timestamp in ns".
   - If summaries become support-derived, update docstrings/descriptions so
     they do not imply wall-clock creation time for summaries.

7. `engram/store/_sql/sqlite.py`
   - Defines `memory_items` and `memory_edges`.
   - No schema migration should be needed for this change if the existing
     columns are reused.
   - Do not add a new column such as `processed_at` or `summary_created_at`.
     That is a separate audit feature and out of scope.

8. `engram/store/backends/sqlite/schema.py`
   - Should not need a schema version bump if no table or column changes.
   - If you find you need a migration, stop and re-evaluate. This plan expects
     a behavior change using existing schema.

9. Tests:
   - `tests/store/test_memory_ids.py`
   - `tests/store/test_sqlite.py`
   - `tests/core/test_memory.py`
   - `tests/core/test_context.py`
   - `tests/fixtures/state_inspection.py`

### Comprehension Checks Before Editing

Before changing code, be able to answer these:

1. Why is `memory_id_clock` still needed if summary IDs can be inserted below
   the current clock?
   - Answer: moments still need globally monotonic generated IDs. Explicit or
     support-anchored inserts below the clock are allowed. Anchored inserts
     above the clock must advance it.

2. Why is `summary.created_at = max(child.created_at)` part of this plan?
   - Answer: current recent/context paths sort by `created_at`. MID anchoring
     alone would not keep derived summaries in historical time order.

3. Why should the summary allocator use `max(child_ids) + 1` rather than
   `MAX(all item IDs in the vault) + 1`?
   - Answer: global max follows insertion order and would place backfilled
     summaries after unrelated later records. The support set is the timeline
     anchor for derived items.

## 4. Invariants And Constraints

- Moment allocation must not change. `Engram.record()` keeps using
  `StateStore.allocate_memory_id(time.time_ns())`.
- Summary allocation for non-empty `child_ids` must not use
  `time.time_ns()` as the MID anchor.
- Summary allocation for non-empty `child_ids` must use:

  ```text
  candidate = max(child_ids) + 1
  while candidate already exists:
      candidate += 1
  ```

- Candidate uniqueness must be checked inside the same state-store transaction
  that inserts the summary row and edges.
- Summary insertion and edge insertion must stay atomic. No summary row without
  edges, no edges without the summary row.
- If any child ID is missing, fail the summary creation. Do not silently create
  a partial or childless summary.
- Do not deduplicate or reorder `child_ids` for edge insertion. If duplicate
  child IDs appear, reject them before insert with `StoreDataError`. Never
  silently collapse duplicates into one edge.
- `memory_id_clock` must never move backward.
- If an anchored summary MID is greater than the current clock, advance the
  clock to cover it.
- If an anchored summary MID is lower than the current clock, leave the clock
  alone.
- Summary `created_at` for non-empty `child_ids` must be `max(child.created_at)`.
- Do not derive summary `created_at` by decoding or masking the child MID.
  Explicit historical records may have valid MIDs and valid `created_at` values
  that are not exactly equal.
- `indexed_at` remains processing/index-maintenance time.
- `last_task_updated_at` must not be set to the support-derived
  `summary.created_at`. For summary rows created without a real Weft task
  correlation update, store `NULL` for `last_task_updated_at`.
- Do not add a public `id=` argument to `record()`.
- Do not add an import subsystem in this change.
- Do not add a new schema column for audit time.
- Do not change CLI or JSON output shapes.
- Do not add a new dependency.
- Do not mock SQLite, LanceDB, or the state store in tests that prove this
  behavior.
- Existing support links remain authoritative in SQLite. The retrieval index
  remains a rebuildable projection.
- Plans are non-normative. Update specs for behavior that becomes normative.

## 5. Design

### Allocation Rule

For a non-empty support set:

```python
anchor_id = max(child_ids)
candidate = anchor_id + 1
while memory_items.id == candidate exists:
    candidate += 1
summary_id = candidate
summary_created_at = max(child.created_at for child in children)
```

Treat MID and `created_at` as two related but distinct support-derived axes.
The summary MID follows child MID order. The summary `created_at` follows child
`created_at` values. Do not compute one from the other.

The loop is a robustness guard, not a performance concern. On human-scale
records with nanosecond-format MIDs, collisions are expected to be effectively
irrelevant in practice. Keep the loop simple and bounded by `SQLITE_MAX_INT64`.

For an empty support set:

```python
summary_id = allocate_memory_id(created_at)
summary_created_at = created_at
```

This fallback exists for fixtures and explicit internal construction. Normal
coalescing should always pass children.

### Where The Logic Lives

Put the support-anchored allocation in `StateStoreCore`, not in `Engram` and
not in `MemoryIdGenerator`.

Reason:

- `StateStoreCore` owns `memory_items`, `memory_edges`, child lookup, and the
  transaction.
- `MemoryIdGenerator` owns clock-based moment allocation and should stay
  unaware of summary graph semantics.
- `Engram` should not know SQL or check uniqueness.

Expected private helpers in `engram/store/core.py`:

```python
def _summary_timeline_anchor(
    self,
    child_ids: Sequence[int],
) -> tuple[int, int]:
    """Return (max_child_id, max_child_created_at), validating all children exist."""

def _first_unused_memory_id_after(self, anchor_id: int) -> int:
    """Return the first unused non-negative MID greater than anchor_id."""

def _memory_id_exists(self, item_id: int) -> bool:
    """Return whether a memory item exists with this ID."""
```

Do not add a public method unless implementation proves multiple modules need
it. They should not.

### `created_at` Signature

Change summary creation signatures to allow the store to derive `created_at`
for real summaries:

```python
def create_summary_item(
    *,
    tier: int,
    text: str,
    summary_terms: Sequence[str],
    child_ids: Sequence[int],
    created_at: int | None = None,
) -> MemoryItem:
```

Use these rules:

- If `child_ids` is non-empty:
  - derive `created_at` from children
  - do not accept a caller wall-clock timestamp unless it exactly matches the
    derived child timestamp
  - if the caller provides `created_at` and it differs from the derived value,
    raise `StoreDataError`
- If `child_ids` is empty:
  - require `created_at` to be provided
  - allocate through the existing clock path

This makes misuse visible. It prevents an implementer from keeping a hidden
processing-time timestamp on summaries with real children.

### Error Types

Use existing exceptions:

- `MemoryItemNotFoundError(child_id)` for missing child support items.
- `StoreDataError` for invalid summary timestamp arguments, negative anchor
  values, or no valid integer space after the anchor.
- `StoreIntegrityError` for database constraint failures or impossible clock
  state.

Do not add a new exception class.

## 6. Bite-Sized Tasks

### Task 1. Add Red Tests For Store-Level Summary MID Anchoring

Outcome: Tests describe the new core state-store behavior before production
code changes.

Files to touch:

- `tests/store/test_memory_ids.py`

Read first:

- Existing tests in `tests/store/test_memory_ids.py`
- `StateStoreCore.create_summary_item()` in `engram/store/core.py`

Add tests using real `SQLiteStateStore`. Do not mock the store or runner.

Tests to add:

1. `test_summary_item_id_is_first_unused_after_max_child_id`
   - Create a vault.
   - Insert two moment items with explicit MIDs, for example `1_000_000_000`
     and `1_000_010_000`, using `store.put_item()`.
   - Create an episode over those children.
   - Assert `episode.id == max(child_ids) + 1`.
   - Assert `episode.created_at == max(child.created_at)`.
   - Assert `store.get_children(episode.id)` returns the child IDs in input
     order.

2. `test_summary_item_id_skips_existing_collision_after_child_anchor`
   - Insert children with max child ID `base + 10`.
   - Insert an unrelated item at `base + 11`.
   - Create an episode over the children.
   - Assert `episode.id == base + 12`.
   - This proves collision handling without pretending collisions are common.

3. `test_summary_item_below_current_clock_does_not_allocate_from_clock`
   - First allocate a future moment ID with `store.allocate_memory_id(future_ns)`
     or insert a future item that advances the clock.
   - Then insert historical child items below that clock.
   - Create an episode over the historical children.
   - Assert the episode ID is immediately after the historical child max, not
     after the current `memory_id_clock`.
   - Then call `store.allocate_memory_id(future_ns)` again and assert it is
     greater than the previous generated future ID. This proves the clock did
     not move backward.

4. `test_summary_item_above_clock_advances_memory_id_clock`
   - Insert child items with explicit MIDs above the current clock.
   - Create an episode.
   - Allocate a new moment ID at the same or lower physical timestamp.
   - Assert the generated moment ID is greater than the summary ID.

5. `test_summary_item_rejects_missing_children`
   - Call `create_episode()` with one real child ID and one missing child ID.
   - Assert `MemoryItemNotFoundError`.
   - Assert no summary row was inserted.

6. `test_summary_item_rejects_duplicate_children`
   - Call `create_episode()` with duplicate child IDs.
   - Assert `StoreDataError`.
   - Assert no summary row was inserted.
   - This prevents accidental deduplication of support edges.

7. `test_summary_item_rejects_mismatched_explicit_created_at`
   - Insert children with known `created_at` values.
   - Call `create_episode(..., created_at=max_child_created_at + 1)`.
   - Assert `StoreDataError`.
   - This prevents future code from reintroducing processing-time summaries.

8. `test_summary_item_does_not_store_support_time_as_task_update_time`
   - Create an episode over children with historical `created_at` values.
   - Read the raw SQLite row for that summary.
   - Assert `last_task_updated_at IS NULL`.
   - This is an internal storage assertion, but it protects a field that is not
     exposed through `MemoryItem`.

9. `test_childless_summary_keeps_clock_allocator_fallback`
   - Call `create_summary_item()` with `child_ids=()` and explicit
     `created_at`.
   - Assert it still returns a valid hybrid MID and stores the explicit
     timestamp.
   - Keep this fallback narrow. Do not use it in normal coalescing.

Per-task done signal:

- The new tests fail for the expected reason: current summaries use
  `allocate_memory_id(created_at)` and processing-time `created_at`.
- If tests fail because imports or fixtures are broken, fix the tests before
  production code.

Stop and re-evaluate if:

- You need to mock `SQLiteStateStore`.
- You need to add a schema migration just to write these tests.
- You find existing tests depend on summary IDs being processing-time IDs in a
  way that is not just fixture setup.

### Task 2. Add Red Tests For Coalescing Back Processing

Outcome: The domain path proves delayed coalescing does not place historical
summaries at processing time.

Files to touch:

- `tests/core/test_memory.py`

Read first:

- `test_work_until_idle_creates_arc_and_arc_lookup`
- `test_generic_tier_coalescing_supports_unwrapped_higher_tiers`
- `tests/conftest.py` local runtime shims

Add one or two tests through `Engram`, not by calling private store helpers as
the main proof.

Tests to add:

1. `test_back_processed_episode_mid_and_created_at_follow_children`
   - Use `monkeypatch` to control `engram.core.memory.time.time_ns`.
   - Record at least three moments with historical timestamps. Use distinct
     timestamps that are far lower than a later processing timestamp.
   - After recording, monkeypatch `time.time_ns()` to a far-future value.
   - Run `memory.work_until_idle()`.
   - Fetch the created episode from the store or via lookup.
   - Assert:
     - `episode.id == max(moment_ids_in_episode) + 1` or the first unused ID
       after that max if the test intentionally creates a collision.
     - `episode.created_at == max(child.created_at)`.
     - `episode.id` is much lower than the far-future processing timestamp.
     - `episode.indexed_at` is not asserted as historical. It is allowed to be
       processing time.

2. `test_back_processed_arc_mid_and_created_at_follow_episode_children`
   - Use enough deterministic moment text to create at least three episodes
     and one arc, similar to the existing `arc_memory` fixture.
   - Force processing time to be far future.
   - Assert the arc ID is first unused after max child episode ID.
   - Assert the arc `created_at` is max child episode `created_at`.

Keep the tests focused. Do not assert exact summary text unless necessary.

Per-task done signal:

- Tests fail under current implementation because `time.time_ns()` drives
  summary `created_at` and MID allocation.

Stop and re-evaluate if:

- The tests become brittle because they depend on LLM output. Use existing
  deterministic shims in `tests/conftest.py`.
- You need sleeps or real time delays. Use monkeypatching instead.

### Task 3. Implement Support-Anchored Allocation In `StateStoreCore`

Outcome: Summary rows and edges are inserted transactionally with IDs anchored
to their support set.

Files to touch:

- `engram/store/core.py`

Read first:

- `StateStoreCore.put_item()`
- `StateStoreCore.allocate_memory_id()`
- `StateStoreCore.create_summary_item()`
- `engram/store/id_generator.py`

Implementation steps:

1. Add private helper `_memory_id_exists(item_id: int) -> bool`.
   - Use a narrow `SELECT 1 FROM memory_items WHERE id = ? LIMIT 1`.
   - Do not call `get_item()` in the collision loop. It constructs models and
     does more work than needed.

2. Add private helper `_first_unused_memory_id_after(anchor_id: int) -> int`.
   - Start at `anchor_id + 1`.
   - Reject if `anchor_id < 0`.
   - Reject if the candidate is `>= SQLITE_MAX_INT64`.
   - Loop while `_memory_id_exists(candidate)`.
   - Raise `StoreDataError` if no valid candidate remains.
   - Import `SQLITE_MAX_INT64` from `engram._constants`.

3. Add private helper `_summary_timeline_anchor(child_ids)`.
   - If `len(set(child_ids)) != len(child_ids)`, raise `StoreDataError`
     before reading or writing rows.
   - Fetch `id` and `created_at` for all child IDs using one SQL query.
   - Validate every distinct child ID exists.
   - Raise `MemoryItemNotFoundError(missing_id)` for the first missing child.
   - Return `max_child_id, max_child_created_at`.
   - Preserve `child_ids` order for edge insertion. The helper only computes
     max values.
   - Do not use a deduplicated child list for `memory_edges`.

4. Change `create_summary_item()`:
   - Move item construction inside `with self._runner.transaction():`.
   - If `child_ids` is non-empty:
     - compute `max_child_id, max_child_created_at`
     - if `created_at` was provided and differs from `max_child_created_at`,
       raise `StoreDataError`
     - set `item_id = _first_unused_memory_id_after(max_child_id)`
     - set `item_created_at = max_child_created_at`
   - If `child_ids` is empty:
     - require `created_at is not None`
     - set `item_id = self.allocate_memory_id(created_at)`
     - set `item_created_at = created_at`
   - Insert the summary row.
   - Set `last_task_tid` and `last_task_updated_at` to `None` for these
     summary rows unless a future task-correlation feature explicitly updates
     them through the existing task-correlation methods.
   - Insert the edges.
   - Call `self._id_generator.observe_existing_id(item.id)` before the
     transaction commits.

5. Keep `create_episode()` and `create_arc()` as thin wrappers.
   - Update their signatures only as needed for optional `created_at`.
   - Do not duplicate allocation logic in those wrappers.

6. Keep `put_item()` behavior from the hybrid MID change.
   - Explicit item inserts still advance the clock only when needed.

Per-task done signal:

- Store-level red tests from Task 1 pass.

Stop and re-evaluate if:

- You are tempted to use global `MAX(id)` from `memory_items`.
- You are tempted to put this logic in `Engram`.
- You are adding a new table or column.
- You need nested transactions.

### Task 4. Update Store Protocol And SQLite Adapter Signatures

Outcome: Type contracts match the new optional `created_at` behavior.

Files to touch:

- `engram/store/base.py`
- `engram/store/sqlite.py`
- `tests/fixtures/state_inspection.py`

Read first:

- Existing method signatures for `create_episode`, `create_arc`, and
  `create_summary_item`.

Implementation steps:

1. Update `StateStore` protocol signatures:

   ```python
   created_at: int | None = None
   ```

2. Update `SQLiteStateStore` methods with the same signatures.

3. Keep adapter bodies as delegates only.

4. Update `tests/fixtures/state_inspection.py` only if its helper needs to
   pass optional `created_at`.

Per-task done signal:

- `mypy engram` does not report signature mismatch.

Stop and re-evaluate if:

- You need overloads.
- You are adding public API surface outside the store protocol.

### Task 5. Update Coalescing To Let Store Derive Summary Timeline

Outcome: Normal episode and arc creation no longer passes processing time into
summary timeline fields.

Files to touch:

- `engram/core/memory.py`

Read first:

- `_coalesce_available_tier_operation()`
- `process_item_operation()`
- `rebuild_index()`

Implementation steps:

1. In `_coalesce_available_tier_operation()`, remove
   `created_at=time.time_ns()` from `self._store.create_summary_item(...)`.
2. Keep `indexed_at=time.time_ns()` after `self._index.upsert_item()`.
3. Do not change the processing lock, summarization, indexing, or edge
   selection behavior.

Per-task done signal:

- Core coalescing tests from Task 2 pass.

Stop and re-evaluate if:

- You are changing `choose_summary_window()`.
- You are changing summary text or term extraction.
- You are changing `indexed_at` to a historical value.

### Task 6. Update Existing Tests That Encoded Old Summary Time Assumptions

Outcome: Existing tests remain meaningful under support-anchored summaries.

Files likely to touch:

- `tests/store/test_sqlite.py`
- `tests/core/test_memory.py`
- `tests/core/test_context.py`
- `tests/fixtures/state_inspection.py`

What to look for:

- Tests that call `create_episode(..., created_at=base + 100)` with real
  children.
- Tests that assume a summary ID is close to processing time.
- Tests that use childless summary fixtures and still need explicit
  `created_at`.

How to update:

- If a test creates summaries with real children, either remove the explicit
  `created_at` argument or set it to `max(child.created_at)`.
- If a test creates childless summary fixtures, keep explicit `created_at`.
- If a test asserts "recent summaries", ensure it is testing the intended
  support-derived ordering, not processing order.

Do not weaken tests by removing assertions. Replace stale assertions with the
new invariant.

Per-task done signal:

- All previously passing targeted tests still pass.

Stop and re-evaluate if:

- A test failure suggests user-visible CLI or client output shape changed.
- Updating the test would make it stop proving any real behavior.

### Task 7. Update Specs And User-Facing Docs

Outcome: The normative docs match the new derived-summary timeline model.

Files to touch:

- `docs/specs/10-minimum-memory-model.md`
- `README.md`
- `AGENTS.md`
- `docs/agent-context/engineering-principles.md`
- Possibly `docs/implementation/04-minimum-memory-slice.md` if it still
  describes summary IDs as processing-time IDs.

Spec changes:

1. Update [MM-9] or add a nearby requirement:
   - Higher-tier summary IDs are support-anchored.
   - For non-empty support sets, the summary MID is the first unused MID after
     `max(child MIDs)`.

2. Update [MM-25.1]:
   - Moments use `created_at` as the physical memory timestamp.
   - Summaries use `created_at = max(child.created_at)` because they are
     derived from support items.
   - `indexed_at` or future audit fields represent processing time, not the
     memory timeline.

3. Keep [MM-4] gap language:
   - Collisions can cause gaps.
   - Callers must not infer exact equality between MID and `created_at`.

README and AGENTS changes:

- State that moments are real memory events.
- State that summaries are derived and timeline-anchored to their support.
- Keep the `time.time_ns()` format-compatible language for MIDs.

Per-task done signal:

- `rg` no longer finds stale statements implying summary IDs are allocated at
  processing time.

Suggested grep:

```bash
rg -n "summary.*time\\.time_ns|created now|processing time|timestamp IDs|nanosecond-timestamp" README.md AGENTS.md docs engram
```

Stop and re-evaluate if:

- The docs start describing a new import API.
- The docs imply summaries are real memories rather than derived projections.

### Task 8. Run Verification Gates

Outcome: The behavior is proven at the store, domain, and neighboring contract
layers.

Run targeted tests first:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_memory_ids.py -q
./.venv/bin/python -m pytest tests/store/test_sqlite.py -q
./.venv/bin/python -m pytest tests/core/test_memory.py -q
./.venv/bin/python -m pytest tests/core/test_context.py -q
```

Run neighboring contract tests:

```bash
. ./.envrc
./.venv/bin/python -m pytest \
  tests/test_background.py \
  tests/commands/test_memory_commands.py \
  tests/client/test_client.py \
  tests/cli/test_cli.py \
  -q
```

Run full gates:

```bash
. ./.envrc
./.venv/bin/python -m pytest -q
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests
./.venv/bin/ruff format --check engram tests
```

If `ruff format --check engram tests` reports unrelated pre-existing files,
format only files touched by this change and report the unrelated file names.
Do not create unrelated formatting churn.

Per-task done signal:

- Full pytest passes.
- `mypy engram` passes.
- `ruff check` passes.
- Format check passes for touched files, or unrelated pre-existing formatting
  drift is clearly reported.

## 7. Testing Plan

Use red-green TDD.

Start with the store-level tests because the state store owns the invariant.
Then add domain-level tests proving coalescing uses the store correctly.

Do not mock:

- `SQLiteStateStore`
- `StateStoreCore`
- `SQLiteRunner`
- LanceDB when proving rebuild/search context behavior

Allowed shims:

- Existing test shims for LLM summarization in `tests/conftest.py`
- Existing deterministic embeddings
- `monkeypatch` for `time.time_ns()` to prove back-processing behavior without
  sleeping

Required invariant coverage:

- Summary MID is immediately after max child MID when no collision exists.
- Summary MID skips occupied IDs after the child anchor.
- Summary MID can be below the current `memory_id_clock`.
- Anchored summaries above the current clock advance the clock.
- Summary `created_at` is `max(child.created_at)`.
- `indexed_at` remains processing/index time.
- `last_task_updated_at` is not populated with support-derived memory time.
- Missing children fail without partial rows.
- Duplicate child IDs are not silently deduplicated.
- Existing support edge ordering remains intact.
- Empty-child fallback remains valid but is not used by normal coalescing.
- Moment IDs remain generated through the hybrid clock.

Anti-patterns to avoid:

- Mocking `create_summary_item()` and asserting it was called.
- Testing only private helper methods while skipping actual row insertion.
- Asserting exact summary text from the summarizer.
- Adding sleeps to create time separation.
- Weakening existing tests that should now assert the new invariant.

## 8. Verification And Gates

Implementation is not done until these pass or are explicitly reported with
reason:

```bash
. ./.envrc
./.venv/bin/python -m pytest tests/store/test_memory_ids.py tests/store/test_sqlite.py tests/core/test_memory.py tests/core/test_context.py -q
./.venv/bin/python -m pytest tests/test_background.py tests/commands/test_memory_commands.py tests/client/test_client.py tests/cli/test_cli.py -q
./.venv/bin/python -m pytest -q
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests
./.venv/bin/ruff format --check engram tests
```

Success means:

- All tests pass.
- No type errors.
- No lint errors.
- No unrelated file churn.
- Docs and specs state the support-anchored model clearly.

## 9. Rollback Plan

This should not need data rollback because it changes allocation behavior using
existing columns.

If the change must be reverted before release:

1. Revert the code changes in `engram/store/core.py`,
   `engram/store/base.py`, `engram/store/sqlite.py`, and
   `engram/core/memory.py`.
2. Revert tests that assert support-anchored summary IDs.
3. Revert docs/spec changes about summary timeline anchoring.
4. Do not delete `memory_id_clock`; it belongs to the previous hybrid MID
   generator change and remains needed for moments.

If support-anchored summaries have already been written to a vault, reverting
the code does not corrupt those rows. The rows are ordinary `memory_items` and
`memory_edges`. The old code would simply create future summaries using the
clock allocator again. That is semantically undesirable, but it does not make
the store unreadable.

## 10. Out Of Scope

- Public historical import API.
- `record(text, id=...)` or CLI flags for explicit IDs.
- New audit fields such as `processed_at`, `summarized_at`, or
  `source_window_start`.
- Postgres implementation.
- Retrieval ranking changes.
- Coalescing-window algorithm changes.
- LLM prompt changes.
- Schema migration unless implementation proves the existing schema cannot
  express the rule. If that happens, stop and re-plan.

## 11. Fresh-Eyes Review Notes

This section records the self-review applied to this plan.

### Finding 1: MID-Only Anchoring Would Not Meet The Goal

Problem:

- The initial narrow interpretation was "change summary MID allocation only."
- Current code uses `created_at` for recent ordering in store queries and
  context assembly.
- If `summary.created_at` stayed at processing time, backfilled summaries would
  still appear temporally recent in those paths.

Fix in this plan:

- For non-empty child summaries, derive `created_at` from
  `max(child.created_at)`.
- Keep `indexed_at` as processing time.
- Update specs and tests around this distinction.

### Finding 2: Global MAX Would Be The Wrong Anchor

Problem:

- A global `MAX(memory_items.id) + 1` rule would place historical summaries
  after unrelated later memories when back processing a populated vault.

Fix in this plan:

- The rule is `first unused MID after max(child MIDs)`.
- Tests explicitly set the global clock higher than the historical children and
  assert the summary remains child anchored.

### Finding 3: Hidden Partial-Write Risk

Problem:

- Summary ID selection, row insertion, edge insertion, and clock advancement
  must not split into separate transactions.

Fix in this plan:

- The implementation task requires all of those steps in one
  `StateStoreCore` transaction.
- Tests include missing-child failure and no partial summary row.

### Finding 4: The Collision Loop Is Robustness, Not Product Semantics

Problem:

- Overweighting collision density could lead to a global allocator design that
  harms historical ordering.

Fix in this plan:

- The plan keeps the collision loop simple and local.
- It states that dense collisions are not expected on human timescales, while
  still requiring correctness if one occurs.

### Finding 5: This Must Not Grow Into Import

Problem:

- The motivating use case includes dated records and explicit IDs, which could
  tempt the implementer to add an import API.

Fix in this plan:

- Import API is explicitly out of scope.
- The implementation changes only summary allocation and summary timeline
  semantics.

### Finding 6: Support Time Must Not Become Task Metadata

Problem:

- Current `create_summary_item()` stores `last_task_updated_at=created_at` for
  summary rows.
- After this change, `created_at` is support-derived historical time for
  summaries. Copying it into `last_task_updated_at` would make task metadata
  falsely historical.

Fix in this plan:

- Summary insert semantics now require `last_task_updated_at` to stay `NULL`
  unless a real task-correlation update writes it.
- Store tests include a raw SQLite assertion for this internal field because
  `MemoryItem` does not expose it.

### Finding 7: Duplicate Children Must Not Be Silently Collapsed

Problem:

- The anchor helper needs to use distinct IDs for existence checks, but edge
  insertion must preserve caller order and cardinality.
- A careless implementation could turn `child_ids` into a set and silently
  collapse duplicate support edges.

Fix in this plan:

- Duplicate child IDs are rejected with `StoreDataError` before insertion.
- Tests assert failure and no partial summary row.
