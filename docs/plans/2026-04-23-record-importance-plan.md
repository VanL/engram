# 2026-04-23 Record Importance Plan

Status: Implemented

## 1. Goal

Implement:

```bash
engram record --importance INT "TEXT"
```

and expose the same write-time importance option through the shared command
layer and `EngramClient`.

`importance` is the user-facing write-time name for the existing relevance
multiplier used by scoring. The stored item should still use the existing
`MemoryItem.relevance` field. This is not a storage-model change and should not
add a new column.

The intended layering is:

```text
CLI parsing
  -> engram.commands.memory.record(memory, text, importance=...)
      -> Engram.record(text, importance=...)
          -> MemoryItem(relevance=float(importance))
          -> StateStore.put_item(...)

EngramClient.record(text, importance=...)
  -> engram.commands.memory.record(...)
```

The important engineering point: set importance during the initial durable
moment write. Do not implement this as "record, then pin" because that creates
two state mutations and a partial-failure edge that does not need to exist.

## 2. Source Documents

Read these before editing:

- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/specs/10-minimum-memory-model.md` [MM-15], [MM-17], [MM-18]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1],
  [MWS-2], [MWS-3], [MWS-4], [MWS-21], [MWS-22], [MWS-27],
  [MWS-31], [MWS-35]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-3],
  [FCI-4], [FCI-5], [FCI-24], [FCI-25], [FCI-27], [FCI-35],
  [FCI-36], [FCI-38], [FCI-43]
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/02-repository-map.md`
- `AGENTS.md`
- `README.md`

Current code to read before editing:

- `engram/core/memory.py`
- `engram/commands/memory.py`
- `engram/client.py`
- `engram/cli.py`
- `engram/_constants.py`
- `engram/_exceptions.py`
- `engram/_models.py`
- `tests/core/test_memory.py`
- `tests/commands/test_memory_commands.py`
- `tests/client/test_client.py`
- `tests/cli/test_cli.py`

## 3. Current Context

Current behavior:

- `Engram.record(text) -> int` stores a tier-0 `MemoryItem`.
- `MemoryItem.relevance` defaults to `DEFAULT_RELEVANCE_FLOOR`, currently
  `1.0`.
- `Engram.pin(item_id, relevance=...)` updates `MemoryItem.relevance` after an
  item already exists.
- Search score uses `fused_score * access * relevance`.
- CLI `engram record TEXT --json` returns exactly `{"id": <int>}`.
- CLI `engram pin ID RELEVANCE --json` returns the lookup item shape.
- `record()` uses the state-store hybrid memory ID allocator. Do not touch ID
  allocation for this change.
- `record()` is asynchronous with respect to indexing and coalescing. It must
  still return after durable state write and deferred-work recording, not after
  LanceDB indexing.

The requested new behavior:

- `engram record --importance 5 "Decision text"` stores a moment whose
  `relevance` is `5.0`.
- `Engram.record("Decision text", importance=5)` stores the same relevance.
- `engram.commands.memory.record(memory, "Decision text", importance=5)` does
  the same thing.
- `EngramClient.record("Decision text", importance=5)` does the same thing.
- Omitting importance preserves current behavior: relevance `1.0`.

## 4. Design Decision

Add a single optional keyword parameter named `importance` to the write path:

```python
Engram.record(text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int
commands.record(memory: Engram, text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int
EngramClient.record(text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int
```

CLI:

```bash
engram record --importance 5 "Decision text"
engram record "Decision text" --importance 5
engram record "Decision text"
```

Implementation rule:

```python
MemoryItem(
    id=item_id,
    tier=TIER_MOMENT,
    text=stripped,
    created_at=created_at,
    relevance=float(importance),
)
```

Validation:

- `importance` must be an integer.
- `importance` must be at least `1`.
- Invalid importance must fail before any `MemoryItem` is stored.
- CLI `--importance` should use `type=int`, but domain validation must still
  enforce the rule because Python callers can bypass argparse.

Recommended error shape:

- Add `InvalidImportanceError(EngramError, ValueError)` in
  `engram/_exceptions.py`.
- Export it from `engram/__init__.py`.
- Raise it from the domain layer. The CLI already catches `EngramError`, so a
  domain-owned error avoids a broad `ValueError` catch in `engram/cli.py`.

Default:

- Add `DEFAULT_IMPORTANCE: Final[int] = 1` in `engram/_constants.py`.
- Keep `DEFAULT_RELEVANCE_FLOOR: Final[float] = 1.0` because scoring and model
  validation still use relevance as a float.
- Do not introduce a new `importance` storage field.

## 5. Invariants And Constraints

Do not break:

- `record()` still writes one durable moment and returns its ID.
- `record()` still records downstream processing need before returning.
- `record()` still does not wait for embedding, LanceDB indexing, or
  coalescing.
- `record()` still uses state-store ID allocation. No check-then-increment
  allocator may return.
- Existing `record(text)` callers keep working with default importance `1`.
- `created_at` remains the actual creation timestamp.
- `id` remains the state-store allocated memory identity.
- `MemoryItem.relevance` remains the persisted multiplier.
- Search still boosts by `access * relevance`.
- `engram record TEXT --json` still returns exactly `{"id": <int>}`. Do not add
  `importance` or `relevance` to the record JSON output.
- CLI default record output still prints only the ID.
- `pin` remains the update-time relevance command in this plan.
- No schema migration is required.
- No new dependency is allowed.
- No storage abstraction, ORM, service locator, or plugin work is allowed.

Do not add:

- `--weight`
- `--relevance` as a record flag
- `engram memorize`
- a `remember` alias
- a new top-level `importance` command
- a second path that records first and then updates relevance
- a backwards-compatibility alias for any renamed public surface

Stop and re-plan if:

- the implementation starts renaming `pin`
- the implementation starts adding a storage column
- the implementation needs a schema version bump
- CLI JSON output shape changes
- tests require mocking `Engram.record`, SQLite, or LanceDB to prove normal
  behavior
- the change starts turning into a broader CLI redesign

## 6. Files To Touch

Expected production files:

- `engram/_constants.py`
  - Add `DEFAULT_IMPORTANCE`.
- `engram/_exceptions.py`
  - Add `InvalidImportanceError`.
- `engram/__init__.py`
  - Re-export `InvalidImportanceError` if added.
- `engram/core/memory.py`
  - Add `importance` keyword to `Engram.record`.
  - Validate importance.
  - Set `MemoryItem.relevance` on initial construction.
- `engram/commands/memory.py`
  - Add `importance` keyword to command-layer `record`.
  - Delegate to `Engram.record(text, importance=importance)`.
- `engram/client.py`
  - Add `importance` keyword to `EngramClient.record`.
  - Delegate through `commands.record`.
- `engram/cli.py`
  - Add `record.add_argument("--importance", type=int, default=DEFAULT_IMPORTANCE)`.
  - Pass `args.importance` to `commands.record`.
- `docs/specs/11-minimum-write-search-context-slice.md`
  - Clarify that record may accept write-time importance and stores it as the
    relevance multiplier.
- `docs/specs/15-foundation-contracts-and-invariants.md`
  - Clarify that `engram record TEXT --json` remains exactly `{"id": ...}` even
    when `--importance` is supplied.
  - Add this plan to related plans.
- `README.md`
  - Update CLI and Python examples to show optional `--importance` /
    `importance=`.
- `AGENTS.md`
  - Update the CLI/API table if it should show the new optional parameter.

Expected test files:

- `tests/core/test_memory.py`
- `tests/commands/test_memory_commands.py`
- `tests/client/test_client.py`
- `tests/cli/test_cli.py`
- Possibly `tests/test_constants.py` if it asserts storage/default constants.

Do not touch unless a failing test proves it is needed:

- `engram/store/*`
- `engram/index/*`
- `engram/runtime/*`
- `engram/background.py`
- `tests/store/*`
- `tests/index/*`
- `tests/test_background.py`

## 7. Bite-Sized Tasks

### 1. Update specs before code

Outcome:

- Specs define the intended behavior before implementation.

Files:

- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/15-foundation-contracts-and-invariants.md`

Changes:

- In `docs/specs/11-minimum-write-search-context-slice.md`, add a requirement
  near [MWS-1] through [MWS-4]:
  - `record(text, importance=1)` may set write-time importance.
  - Importance maps to the existing relevance multiplier.
  - Importance must be an integer >= 1.
  - Omitted importance is equivalent to `1`.
- In the same spec, clarify [MWS-22] remains about update-time pinning.
- In `docs/specs/15-foundation-contracts-and-invariants.md`, update CLI JSON
  output requirements:
  - `engram record TEXT --json` and
    `engram record --importance INT TEXT --json` both return exactly `id`.
- Add this plan to related plans in touched specs.

Verification:

- Inspection only.
- Do not run runtime tests for this task.

Freshness check:

- The spec must not imply a new storage column named `importance`.
- The spec must not imply `pin` is renamed or removed in this plan.

### 2. Write red domain tests for write-time importance

Outcome:

- Tests fail because `Engram.record()` does not yet accept `importance`.

Files:

- `tests/core/test_memory.py`

Tests to add:

1. `test_record_importance_sets_initial_relevance`
   - Use the existing real `memory` fixture.
   - Call `item_id = memory.record("Decision: ...", importance=5)`.
   - Fetch with `memory.lookup(item_id, count_access=False)`.
   - Assert:
     - `item.relevance == 5.0`
     - `item.access == 1.0`
     - `item.tier == 0`
     - `memory.items_needing_processing_count() == 1`
   - Run `memory.work_until_idle()`.
   - Search for text and assert the item is searchable.

2. `test_record_rejects_invalid_importance_before_writing`
   - Call `memory.record("Decision: invalid importance.", importance=0)`.
   - Expect `InvalidImportanceError`.
   - Assert no moment was stored:
     - `memory.items_needing_processing_count() == 0`
     - `memory.status().item_counts.get("moment", 0) == 0`
   - Repeat for a negative value if it keeps the test readable.

Do not mock:

- SQLite
- LanceDB
- `Engram.record`
- `MemoryItem`

Allowed shims:

- Existing test fixture shims for Weft submission and deterministic embeddings.

Command:

```bash
uv run pytest tests/core/test_memory.py -k "record_importance or invalid_importance"
```

Expected red result:

- `TypeError: Engram.record() got an unexpected keyword argument 'importance'`
  or missing `InvalidImportanceError` import until production code is added.

### 3. Implement domain validation and storage in one write

Outcome:

- Core domain tests pass.

Files:

- `engram/_constants.py`
- `engram/_exceptions.py`
- `engram/__init__.py`
- `engram/core/memory.py`

Implementation notes:

- Add in `_constants.py` near scoring or write defaults:

```python
DEFAULT_IMPORTANCE: Final[int] = 1
"""Default write-time importance. Maps to relevance 1.0."""
```

- Add in `_exceptions.py`:

```python
class InvalidImportanceError(EngramError, ValueError):
    """Raised when write-time importance is not a positive integer."""
```

- Re-export `InvalidImportanceError` from `engram/__init__.py`.
- In `engram/core/memory.py`, import `DEFAULT_IMPORTANCE` and
  `InvalidImportanceError`.
- Change:

```python
def record(self, text: str) -> int:
```

to:

```python
def record(self, text: str, *, importance: int = DEFAULT_IMPORTANCE) -> int:
```

- Validate in `Engram.record()` before allocating an ID:

```python
if not isinstance(importance, int) or isinstance(importance, bool):
    raise InvalidImportanceError("importance must be an integer")
if importance < DEFAULT_IMPORTANCE:
    raise InvalidImportanceError("importance must be at least 1")
```

- Construct the item with:

```python
relevance=float(importance)
```

Why before ID allocation:

- Invalid input should not advance `memory_id_clock`.
- Invalid input should not create gaps or item rows.

Do not:

- call `self.pin(...)`
- call `self._store.pin_item(...)`
- mutate the item after `put_item`
- change state-store methods

Command:

```bash
uv run pytest tests/core/test_memory.py -k "record_importance or invalid_importance"
```

Done signal:

- Targeted core tests pass.

### 4. Add command-layer support and tests

Outcome:

- Shared command layer accepts and forwards importance.

Files:

- `engram/commands/memory.py`
- `tests/commands/test_memory_commands.py`

Tests to add:

1. `test_command_record_importance_sets_relevance`
   - Open a real vault with `commands.open_vault`.
   - Call `commands.record(memory, "Decision: ...", importance=4)`.
   - Fetch through `commands.lookup(memory, item_id, count_access=False)`.
   - Assert returned dict has `"relevance": 4.0`.
   - Assert the dict shape is still `ITEM_KEYS`.

2. `test_command_record_rejects_invalid_importance`
   - Call `commands.record(memory, "Decision: ...", importance=0)`.
   - Expect `InvalidImportanceError`.

Implementation:

- Change command signature:

```python
def record(
    memory: Engram,
    text: str,
    *,
    importance: int = DEFAULT_IMPORTANCE,
) -> int:
    return memory.record(text, importance=importance)
```

- Import `DEFAULT_IMPORTANCE`.
- Do not duplicate validation in the command layer.
- Do not change `_memory_item_to_dict`.

Command:

```bash
uv run pytest tests/commands/test_memory_commands.py -k "record_importance or invalid_importance"
```

Done signal:

- Command tests pass.

### 5. Add client support and tests

Outcome:

- `EngramClient.record(..., importance=INT)` is a thin command adapter.

Files:

- `engram/client.py`
- `tests/client/test_client.py`

Tests to add:

1. `test_client_record_importance_wraps_command_layer`
   - Use `EngramClient.init(..., embedder=DeterministicEmbedder())`.
   - Call `item_id = client.record("Decision: ...", importance=3)`.
   - Assert:
     - `client.lookup(item_id, count_access=False)["relevance"] == 3.0`
     - `commands.lookup(client.memory, item_id, count_access=False)` returns
       the same dict.
   - This proves client and command parity through observable behavior.

2. Update `test_client_close_is_idempotent_and_guards_public_methods`
   only if needed. The existing `lambda: client.record("after close")` should
   continue to cover closed behavior. Do not add a redundant closed-state test
   only for importance.

Implementation:

- Change client signature:

```python
def record(
    self,
    text: str,
    *,
    importance: int = DEFAULT_IMPORTANCE,
) -> int:
```

- Import `DEFAULT_IMPORTANCE`.
- Delegate:

```python
return commands.record(self._memory, text, importance=importance)
```

- Do not reach into `self._memory._store`.

Command:

```bash
uv run pytest tests/client/test_client.py -k "record_importance or client_wraps"
```

Done signal:

- Client tests pass.

### 6. Add CLI support and tests

Outcome:

- `engram record --importance INT "TEXT"` works through the CLI layer and still
  delegates to commands.

Files:

- `engram/cli.py`
- `tests/cli/test_cli.py`

Tests to add:

1. `test_cli_record_importance_sets_relevance`
   - Initialize a real temp vault through CLI.
   - Call:

```python
main([
    "--vault", str(vault),
    "record",
    "--importance", "6",
    "Decision: CLI record importance should set relevance.",
    "--json",
])
```

   - Assert output shape is exactly `{"id": item_id}`.
   - Call `main(["--vault", str(vault), "moment", str(item_id), "--json"])`.
   - Assert the moment output has `"relevance": 6.0`.

2. `test_cli_record_default_importance_stays_one`
   - Existing JSON contract test may already prove this indirectly. If not,
     extend it carefully:
     - record without `--importance`
     - lookup moment
     - assert `"relevance": 1.0`

3. `test_cli_record_rejects_zero_importance`
   - Call record with `--importance 0`.
   - Assert `main(...) == EXIT_ERROR`.
   - Assert output contains `"importance must be at least 1"`.
   - Assert no item was stored if easy to prove through `status`.

Implementation:

- Import `DEFAULT_IMPORTANCE` from `engram._constants`.
- Add to parser:

```python
record.add_argument("--importance", type=int, default=DEFAULT_IMPORTANCE)
```

- Pass to command:

```python
item_id = commands.record(memory, args.text, importance=args.importance)
```

- Do not parse importance in the command layer.
- Do not use `--relevance` in the CLI.
- Do not change `pin`.
- Do not change record JSON output.

Command:

```bash
uv run pytest tests/cli/test_cli.py -k "record_importance or json_output_contracts"
```

Done signal:

- CLI tests pass.

### 7. Update user-facing docs and agent guidance

Outcome:

- Docs describe the new option without implying a new storage concept.

Files:

- `README.md`
- `AGENTS.md`
- Possibly `docs/implementation/04-minimum-memory-slice.md`

Changes:

- In `README.md`, update CLI examples:

```bash
engram record --importance 5 "Pinned local decision"
```

- In Python examples, show:

```python
client.record("Pinned local decision", importance=5)
```

- Explain briefly:
  - importance is an integer write-time multiplier
  - internally it maps to relevance
  - `pin` remains the way to update importance/relevance after recording

- In `AGENTS.md`, update the CLI/API table only if it improves agent
  discoverability. Keep it concise:

```text
engram record [--importance INT] "text"
```

Do not:

- rewrite the conceptual model
- rename relevance everywhere
- remove pin from docs

Verification:

```bash
rg -n "record --importance|importance=|record \\[--importance" README.md AGENTS.md docs/implementation/04-minimum-memory-slice.md
```

Done signal:

- User-facing docs and agent entry point no longer hide the new option.

### 8. Run focused tests, then full gates

Run targeted checks first:

```bash
uv run pytest tests/core/test_memory.py -k "record_importance or invalid_importance"
uv run pytest tests/commands/test_memory_commands.py -k "record_importance or invalid_importance"
uv run pytest tests/client/test_client.py -k "record_importance or client_wraps"
uv run pytest tests/cli/test_cli.py -k "record_importance or json_output_contracts"
```

Then run full gates:

```bash
uv run ruff check --fix
uv run ruff format
uv run pytest
uv run mypy engram
uv run ruff check
uv run ruff format --check
```

Expected final result:

- All tests pass.
- Mypy passes.
- Ruff check passes.
- Ruff format check passes.

If any formatting command changes unrelated files, inspect before claiming
done. Do not revert user changes.

## 8. Testing Philosophy For This Plan

Prefer real behavior:

- Use real `Engram` with real SQLite and LanceDB for core tests.
- Use the real command layer for command tests.
- Use the real `main()` CLI entry for CLI tests.
- Use `EngramClient` for client tests.

Do not over-mock:

- Do not mock `Engram.record`.
- Do not mock `commands.record`.
- Do not mock SQLite.
- Do not mock LanceDB.
- Do not assert that a mock was called with `importance=...` as the main proof.

Existing fixture shims are acceptable:

- Weft submission is shimmed in `tests/conftest.py`.
- LLM summarization is shimmed in `tests/conftest.py`.
- Deterministic embeddings are used in tests.

Core invariants to assert:

- importance `N` stores `relevance == float(N)`
- default record stores `relevance == 1.0`
- invalid importance stores no item
- record output shape remains exactly ID-only
- command/client/CLI paths behave the same by observable state

## 9. Rollback And Sequencing

This change has no schema migration and no one-way storage door.

Safe rollback:

- Revert code changes to `record` signatures, CLI parser, command layer, and
  client.
- Revert docs/spec updates.
- Existing vaults remain valid because importance uses the existing relevance
  field.

Sequencing:

1. Specs first.
2. Red domain tests.
3. Domain implementation.
4. Red command/client/CLI tests.
5. Command/client/CLI implementation.
6. Docs.
7. Full gates.

Do not implement CLI first. The CLI must be a thin adapter over the command and
domain layers.

## 10. Out Of Scope

- Renaming `pin`.
- Removing `pin`.
- Adding `--weight`.
- Adding `--relevance`.
- Changing `pin` from `float` to `int`.
- Changing search scoring.
- Changing context assembly.
- Changing the SQLite schema.
- Changing `MemoryItem` fields.
- Adding a new importance update command.
- Adding hosted, multi-user, Postgres, blob, deletion, forget, or import/export
  behavior.

## 11. Independent Review Loop

Before implementation:

- Ask a second reviewer, agent, or fresh session to check this plan against:
  - `docs/specs/11-minimum-write-search-context-slice.md`
  - `docs/specs/15-foundation-contracts-and-invariants.md`
  - `engram/core/memory.py`
  - `engram/commands/memory.py`
  - `engram/client.py`
  - `engram/cli.py`
  - tests listed above

Review prompts:

- Does this plan preserve layer ownership?
- Is importance set in one durable write?
- Are there any hidden output-shape changes?
- Are tests proving real behavior instead of mock calls?
- Does the plan accidentally rename or remove `pin`?
- Does any task imply a storage migration?

Implementation is not done until review findings are either fixed or explicitly
rejected with a concrete reason.

## 12. Fresh-Eyes Review

### Pass 1: Ambiguities Found

Potential ambiguity: "same meaning as pin" could imply replacing `pin` or
renaming `relevance` everywhere.

Resolution: This plan limits scope to write-time importance. It maps importance
to the existing relevance multiplier and leaves `pin` as the update-time
surface. A future CLI vocabulary cleanup can revisit `pin`, but doing that here
would move away from the requested `record --importance` change.

Potential ambiguity: CLI JSON output could grow to include importance.

Resolution: Keep `record --json` exactly `{"id": ...}`. The user can verify
importance through lookup, as existing record output is ID-only by contract.

Potential ambiguity: Validation could happen only in argparse.

Resolution: Domain validation is required because Python API and client users
bypass argparse.

Potential ambiguity: Importance might be stored in a new field.

Resolution: Do not add `importance` storage. The current model already has
`relevance`, and search scoring already uses it.

### Pass 2: Bad Decisions Checked

Bad direction checked: implement record importance by calling `pin` after
`record`.

Decision: reject. It creates two writes and a partial-failure edge. Initial
importance belongs on the `MemoryItem` before `put_item`.

Bad direction checked: add `--relevance` because the storage field is named
relevance.

Decision: reject. The requested CLI vocabulary is `importance`, and exposing
storage naming in the CLI makes the public API worse.

Bad direction checked: broaden into a full `pin` rename.

Decision: reject for this plan. That is a separate public API migration.

Bad direction checked: add schema migration.

Decision: reject. Existing `relevance` field is sufficient.

### Pass 3: Final Implementability Check

This plan is implementable without unresolved design choices:

- There is one canonical domain behavior: `Engram.record(..., importance=N)`.
- There is one command-layer adapter: `commands.record(..., importance=N)`.
- There is one client adapter: `EngramClient.record(..., importance=N)`.
- CLI owns only parsing and passes the value down.
- Storage remains unchanged.
- Tests cover core, command, client, and CLI behavior with real local
  persistence.
- Full gates are named.

Do not start implementation if any future decision tries to combine this with a
larger CLI rename. That would be a materially different plan.

## 13. Implementation Result

Implemented on 2026-04-23.

Changed production surfaces:

- `Engram.record(text, importance=1)` validates write-time importance before
  ID allocation and stores it as `MemoryItem.relevance`.
- `commands.record(memory, text, importance=1)` delegates to the domain method.
- `EngramClient.record(text, importance=1)` delegates through the command
  layer.
- `engram record --importance INT TEXT` parses importance in the CLI layer and
  passes it to the command layer.

Changed documentation:

- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/15-foundation-contracts-and-invariants.md`
- `README.md`
- `AGENTS.md`
- `docs/implementation/04-minimum-memory-slice.md`

Verification completed:

```bash
uv run pytest tests/core/test_memory.py -k "record_importance or invalid_importance"
uv run pytest tests/commands/test_memory_commands.py -k "record_importance or invalid_importance"
uv run pytest tests/client/test_client.py -k "record_importance"
uv run pytest tests/cli/test_cli.py -k "record_importance or zero_importance"
uv run pytest tests/core/test_memory.py tests/commands/test_memory_commands.py tests/client/test_client.py tests/cli/test_cli.py
uv run ruff check --fix
uv run mypy engram
uv run ruff format
uv run pytest
uv run ruff check
uv run ruff format --check
```

Final gate results:

- Targeted core/command/client/CLI suites passed.
- Public-layer suite passed: `41 passed`.
- Full test suite passed: `157 passed`.
- `uv run mypy engram` passed.
- `uv run ruff check` passed.
- `uv run ruff format --check` passed.
