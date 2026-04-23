# 2026-04-23 Layering Cleanup Plan

Status: Proposed

## 1. Goal

Fix the layering violations found in the current Engram codebase without
changing product behavior. The work should remove the `core.memory ->
background -> core.memory` import cycle, keep background worker code out of
storage internals, keep retrieval adapters from importing core modules, keep
backend-neutral storage code free of SQLite defaults, avoid CLI imports through
the package root, and tighten architecture tests so these problems do not
return.

This is a foundation cleanup, not a feature project. Do not use it to redesign
Engram, add Postgres, change CLI output, change memory semantics, or add public
APIs unless the task below explicitly says to do so.

## 2. Source Documents

Read these before editing:

- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-2], [LAS-4],
  [LAS-8], [LAS-12], [LAS-17], [LAS-18], [LAS-19], [LAS-20],
  [LAS-22], [LAS-23], [LAS-29], [LAS-30]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-3],
  [EWM-4], [EWM-5], [EWM-13], [EWM-15], [EWM-16], [EWM-17],
  [EWM-18], [EWM-19], [EWM-22], [EWM-23], [EWM-24], [EWM-25],
  [EWM-26]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1],
  [FCI-2], [FCI-3], [FCI-4], [FCI-5], [FCI-6], [FCI-7], [FCI-8],
  [FCI-9], [FCI-15], [FCI-24], [FCI-35], [FCI-36], [FCI-37],
  [FCI-38], [FCI-39], [FCI-41], [FCI-43], [FCI-44]

Related plan:

- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`

That plan introduced the backend foundation. This plan does not replace it.
This plan tightens the layer boundaries that became visible after that work.

Weft cleanup references to port/adapt:

- `../weft/tests/helpers/weft_harness.py`
  - `WeftTestHarness` creates an isolated temp root, patches env, builds the
    Weft context early, tracks task IDs, manager IDs, and PIDs, stops live work,
    closes every broker queue it opens, removes broker database files, probes
    SQLite db/WAL/SHM file releasability on Windows, and retries tempdir cleanup.
- `../weft/tests/conftest.py`
  - the `weft_harness` fixture owns teardown; `queue_factory` and `broker_env`
    close all created `Queue` objects; CLI helpers register task/manager IDs
    from outputs so teardown can stop work it did not create directly.
- `../weft/tests/test_harness_registration.py`
  - tests the cleanup contract directly: wait for database release, extend the
    Windows release budget, and raise if files remain locked.

Simplebroker cleanup references to port/adapt:

- `../simplebroker/tests/helper_scripts/cleanup.py`
  - watcher/resource tracking, best-effort stop, GC, Windows delay before
    tmpdir cleanup.
- `../simplebroker/tests/test_queue_coverage.py`
  - `ensure_windows_cleanup()` pattern: `gc.collect()`, short Windows sleep,
    second `gc.collect()`.
- `../simplebroker/tests/conftest.py`
  - close all created queue/core resources in fixture teardown.
- `../simplebroker/tests/test_project_scoping.py`
  - Windows-oriented temporary database cleanup and sqlite connection flush
    pattern.

## 3. Audience Assumptions

Assume the implementer is a skilled developer with little Engram context and
questionable taste. Assume they may:

- "fix" a boundary by renaming a module while keeping the same dependency
  direction
- add a generic service locator or plugin system because it feels flexible
- add a public API only because a test wants an ID
- mock `Engram`, SQLite, LanceDB, or Weft submission so heavily that tests stop
  proving the real contract
- weaken the architecture test instead of making the code obey it
- leave a compatibility alias behind "just in case"
- expand the work into Postgres, an ORM, or a new background framework

Do not do those things. Follow the tasks below in order.

## 4. Current Problems To Fix

### Problem A: Core Imports Background And Creates A Cycle

Current code:

- `engram/core/memory.py` imports `initialize_embedded_weft_project` and
  `submit_process_item_task` from `engram.background`.
- `engram/background.py` imports `Engram` inside `process_memory_task()`.
- The current import cycle is:

```text
engram.core.memory -> engram.background -> engram.core.memory
```

Why this matters:

- [FCI-1] says `engram.core.*` must not import adapter layers.
- `engram.background` is a Weft worker adapter. It is the function target that
  Weft calls back into.
- Cycles make import-time behavior fragile and make architecture tests less
  meaningful.

### Problem B: Background Writes Store State Directly

Current code:

- `engram/background.py` imports `open_state_store`.
- `_mark_failed()` opens the store directly and calls
  `record_processing_failure()`.

Why this matters:

- [FCI-7] says background may open `Engram` at the worker boundary but should
  use public domain methods rather than private storage or index state.
- This direct store call is only needed for a narrow failure branch where
  `Engram.open()` failed before assigning `memory`.
- The branch is real and should remain recoverable, but it should be owned by a
  domain-level helper rather than by the background adapter.

### Problem C: Index Adapter Imports Core Embedding Code

Current code:

- `engram/index/lance.py` imports `default_lance_embedding_function` from
  `engram.core.embeddings`.

Why this matters:

- `engram.index.*` should be a retrieval adapter below `Engram`.
- `Engram` can orchestrate core embedding choices and inject the Lance
  embedding function into `LanceIndex`.
- `LanceIndex` should not reach back into `engram.core.*`.

### Problem D: StateStoreCore Has A SQLite Default

Current code:

- `engram/store/core.py` imports `engram.store._sql.sqlite as sqlite_sql`.
- `StateStoreCore.__init__()` defaults to `sql=sqlite_sql`.

Why this matters:

- The simplebroker-style backend layer is supposed to make `StateStoreCore`
  backend-neutral.
- The core may consume a `StateSQL` namespace, but a concrete wrapper such as
  `SQLiteStateStore` must pass that namespace in.
- A future PG backend should not have to fight a SQLite default in the shared
  core.

### Problem E: CLI Imports Through Package Root

Current code:

- `engram/cli.py` imports `__version__` from `engram`.
- `engram/__init__.py` imports `EngramClient` and `Engram`.

Why this matters:

- `engram version` should not import the full client/core stack through the
  package root.
- This is a transitive layering loophole that the current architecture test does
  not catch.
- The CLI can import `__version__` from `engram._constants` directly.

### Problem F: Tests Normalize Private Store/Index Access

Current code:

- Several tests use `memory._store` or `memory._index`.
- Some of those are justified invariant tests. Others are just shortcuts to get
  IDs or simulate drift.

Why this matters:

- [FCI-35] requires architecture tests to protect private storage/index access
  rules.
- [FCI-39] says if a shared operation needs a shape not exposed publicly, add a
  narrow command/client method instead of reaching into internals.
- Tests may use internals only when proving invariants that have no public
  inspection surface. Do not make private access the default test style.

### Problem G: Test Cleanup Does Not Explicitly Release All DB Handles

Current code:

- `tests/conftest.py` closes the shared `memory` fixture, but many tests create
  additional `Engram`, `EngramClient`, `SQLiteStateStore`, `SQLiteRunner`, or
  `LanceIndex` instances directly.
- Some tests close these manually. Some resources, such as direct `LanceIndex`
  instances, do not currently expose a close method.
- Embedded Weft submission creates short-lived Weft clients and broker access
  against sqlite files in the vault.
- The current test harness does not have a Weft-style owner that can register
  resources, close them in teardown, wait for SQLite file release, and fail when
  handles remain open.

Why this matters:

- On Windows, tmpdir cleanup fails if any open file handle remains under the
  temp directory. SQLite database, WAL, SHM, lock, LanceDB, and embedded Weft
  broker files are all vulnerable to this.
- This is also a CI reliability issue on Unix, but Windows makes it deterministic.
- The simplebroker backend foundation deliberately tracks and closes runners.
  Engram tests need a matching harness so test helpers and direct construction
  do not leak handles.
- Weft already solved the broader version of this problem for manager/task
  processes and simplebroker-backed queues. Engram should adapt that harness
  shape instead of relying on ad hoc `finally: close()` blocks scattered through
  tests.

## 5. Intended Layer Model After This Work

Use this model during implementation:

```text
CLI
  -> commands
      -> Engram domain object
          -> state store protocol/factory
          -> LanceIndex adapter
          -> Weft runtime submission/bootstrap module

EngramClient
  -> commands
      -> Engram domain object

Weft worker adapter: engram.background
  -> Engram public/domain methods only

Dogfood
  -> EngramClient for ordinary app operations
```

The important distinction:

- `engram.background` is the worker adapter and must not be imported by
  `engram.core.*`.
- A new small Weft runtime module may own embedded Weft bootstrap and task
  submission because `Engram.init()` and `Engram.record()` currently expose
  those local-app behaviors directly. This module must not contain worker
  callback domain logic, storage code, retrieval code, or command/client
  presentation logic.

Name the new module:

```text
engram/runtime/weft.py
```

Also add:

```text
engram/runtime/__init__.py
```

Do not name it `background`, `worker`, `tasks`, or `adapter`. Those names hide
the boundary. The module is for the embedded Weft runtime integration that
Engram directly invokes: init and submit. The Weft callback remains
`engram.background:process_memory_task`.

## 6. Invariants And Constraints

These must remain true:

- `Engram.init(path)` still initializes the embedded Weft runtime by default.
- `Engram.init(path, autostart=False)` still passes `autostart=False` through
  to Weft init.
- `Engram.init(path, submit_background=False)` still creates a usable vault and
  records moments without submitting background tasks.
- `Engram.record(text)` still submits the item-processing task when
  `submit_background=True`.
- `process_memory_task()` still calls the same domain repair path as local
  repair: `Engram.repair_item()`.
- If `repair_item()` raises after `Engram.open()` succeeded, the domain method
  should record processing failure exactly as it does today.
- If `Engram.open()` fails before a worker can call `repair_item()`, the worker
  may make a best-effort call into a domain-level failure-recording helper.
  Background must not open the store directly.
- SQLite remains authoritative for state. LanceDB remains rebuildable.
- Rebuild remains one-way from SQLite to LanceDB.
- CLI default output and JSON output shapes must not change.
- Package-root public exports must not be removed.
- No new runtime dependency is allowed.
- No Postgres backend implementation is allowed in this plan.
- No ORM or SQLAlchemy-style abstraction is allowed.
- No service locator, plugin discovery system, dependency injection framework,
  or global mutable registry is allowed.
- Do not weaken architecture tests to make current code pass. Add tests first,
  watch them fail, then fix code.
- Keep red-green TDD where practical. If a task cannot be red-green tested
  cleanly, document the concrete proof used instead in the implementation
  notes or final handoff.
- Tests that create Engram, Weft, SQLite, LanceDB, runner, or store resources
  must close those resources before tmpdir cleanup. This is required for
  Windows CI, not optional polish.
- If a resource does not currently expose a close method but owns file-backed
  state, either add a narrow close/release method or ensure the test harness
  can release references and force GC in a documented way.
- Test cleanup must explicitly handle SQLite database sidecar files: main db,
  `-wal`, `-shm`, and rollback journal files when present.
- Do not hide cleanup failures with `shutil.rmtree(..., ignore_errors=True)` as
  the proof of correctness. It is acceptable as a last-ditch finalizer only if a
  separate test already proves explicit release and cleanup behavior.
- Weft-related cleanup must be based on the installed/local Weft API. If
  `WeftClient` has no close method, do not invent a fake test-only close. Close
  the underlying queues/brokers/context-owned resources that Weft exposes, and
  use file-release probing for sqlite-backed broker files.

## 7. Files To Touch

Expected production files:

- `engram/core/memory.py`
- `engram/background.py`
- `engram/runtime/__init__.py` (new)
- `engram/runtime/weft.py` (new)
- `engram/index/lance.py`
- `engram/store/core.py`
- `engram/store/sqlite.py`
- `engram/cli.py`
- `docs/specs/15-foundation-contracts-and-invariants.md`

Expected test files:

- `tests/architecture/test_import_boundaries.py`
- `tests/test_background.py`
- `tests/conftest.py`
- `tests/test_resource_cleanup.py` (new, if the cleanup helper is added)
- `tests/index/test_lance.py`
- `tests/core/test_memory.py`
- `tests/core/test_context.py`
- `tests/cli/test_cli.py`
- `tests/fixtures/resource_cleanup.py` or
  `tests/fixtures/runtime_cleanup.py` (new, if useful)

Possible supporting test helper:

- `tests/fixtures/storage_inspection.py` or `tests/fixtures/state_inspection.py`

Do not touch unless a targeted test proves it is needed:

- `engram/commands/memory.py`
- `engram/client.py`
- `engram/dogfood/*`
- `engram/store/backends/sqlite/schema.py`
- `engram/store/backends/sqlite/runtime.py`
- `engram/store/db.py`
- `pyproject.toml`

## 8. Task Breakdown

### 1. Add Failing Architecture Tests First

Outcome:

- The architecture suite should fail on the current layering violations before
  production code changes begin.

Files to touch:

- `tests/architecture/test_import_boundaries.py`

Read first:

- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1] through
  [FCI-7], [FCI-35], [FCI-41]
- Existing `tests/architecture/test_import_boundaries.py`

Add tests or strengthen the existing visitor to cover:

- No import cycles among `engram.*` modules.
- `engram.core.*` must not import `engram.background`.
- `engram.background` must not import `engram.store.*`.
- `engram.index.*` must not import `engram.core.*`.
- `engram.store.core` must not import concrete SQL namespaces such as
  `engram.store._sql.sqlite`.
- `engram.cli` must not import from package root `engram`; it should import
  constants and exceptions from concrete modules.
- Production modules outside `engram.core.memory` must not access `._store` or
  `._index`. The current test already checks this through AST attributes; keep
  it.

Do not:

- Ban tests from importing low-level modules. Tests need focused low-level
  proof.
- Ban `engram.dogfood` from importing `EngramClient` through the package root;
  [FCI-6] and [FCI-9] make that the preferred production dogfood surface.
- Implement a heavy graph library. A small AST-based import graph is enough.

Red-green expectation:

- Run `./.venv/bin/python -m pytest tests/architecture/test_import_boundaries.py`.
- It should fail before the code fixes. The failure list should include at
  least the `core.memory -> background -> core.memory` cycle and the
  `index.lance -> core.embeddings` import.

Stop and re-evaluate if:

- The test requires importing modules to inspect them. Architecture checks
  should parse files, not execute package imports.
- The test starts encoding every allowed import manually. Keep it rule-based.

Done signal:

- The architecture tests fail for the known current violations and do not fail
  for unrelated acceptable imports.

### 2. Adapt Weft/SimpleBroker Cleanup Harness For Engram Tests

Outcome:

- Tests have an explicit cleanup harness for file-backed resources created
  during tests: `Engram`, `EngramClient`, `SQLiteStateStore`, `SQLiteRunner`,
  `LanceIndex`, and embedded Weft broker access.
- Cleanup closes resources before pytest or `TemporaryDirectory` tries to remove
  the temp tree.
- Windows handle-release behavior is tested directly.
- Existing tests that create direct resources are either tracked by the harness,
  use a context manager, or close in a `finally` block.

Files to touch:

- `tests/conftest.py`
- `tests/fixtures/resource_cleanup.py` or `tests/fixtures/runtime_cleanup.py`
  (new; prefer one small helper module)
- `tests/test_resource_cleanup.py` (new)
- Existing tests that directly construct resources:
  - `tests/store/test_sqlite.py`
  - `tests/store/test_memory_ids.py`
  - `tests/index/test_lance.py`
  - `tests/core/test_memory.py`
  - `tests/core/test_context.py`
  - `tests/client/test_client.py`
  - `tests/commands/test_memory_commands.py`
  - `tests/cli/test_cli.py`
  - `tests/dogfood/test_codex_replay.py`
- Production files only if a real close/release hook is missing:
  - `engram/core/memory.py`
  - `engram/client.py`
  - `engram/store/sqlite.py`
  - `engram/store/db.py`
  - `engram/index/lance.py`
  - `engram/runtime/weft.py` after Task 3 creates it

Read first:

- `../weft/tests/helpers/weft_harness.py`
  - `WeftTestHarness.__enter__`
  - `WeftTestHarness.cleanup`
  - `WeftTestHarness._cleanup_preserving_database`
  - `WeftTestHarness._remove_database_files`
  - `WeftTestHarness._database_candidate_paths`
  - `WeftTestHarness._database_files_releasable`
  - `WeftTestHarness._cleanup_tempdir`
- `../weft/tests/conftest.py`
  - `weft_harness`
  - `queue_factory`
  - `broker_env`
  - `_register_cli_outputs`
- `../weft/tests/test_harness_registration.py`
  - `test_harness_cleanup_preserve_database_waits_for_database_release`
  - `test_harness_cleanup_preserve_database_extends_windows_release_budget`
  - `test_harness_cleanup_preserve_database_raises_if_database_stays_locked`
- `../simplebroker/tests/helper_scripts/cleanup.py`
  - `cleanup_watchers`
  - `cleanup_at_exit`
  - `register_watcher`
- `../simplebroker/tests/test_queue_coverage.py`
  - `ensure_windows_cleanup`
- Current Engram lifecycle code:
  - `tests/conftest.py`
  - `engram/core/memory.py`
  - `engram/client.py`
  - `engram/store/sqlite.py`
  - `engram/store/db.py`
  - `engram/index/lance.py`

Implementation steps:

1. Add the cleanup helper module.

   Suggested name: `tests/fixtures/resource_cleanup.py`.

   Keep it test-only. Do not put this in production code.

   Include:

```python
from typing import TypeVar

T = TypeVar("T")

class ResourceTracker:
    def register(self, resource: T) -> T: ...
    def close_all(self) -> None: ...

def ensure_windows_cleanup() -> None: ...
def sqlite_candidate_paths(db_path: Path) -> list[Path]: ...
def database_files_releasable(paths: Sequence[Path]) -> bool: ...
def wait_for_database_release(paths: Sequence[Path], *, timeout: float) -> None: ...
```

   Required behavior:

   - `register()` returns the resource so fixtures can write
     `return tracker.register(Engram.init(...))`.
   - `close_all()` closes in reverse creation order. This matters because
     `EngramClient` owns `Engram`, `Engram` owns store/index handles, and direct
     stores/runners may share SQLite files.
   - A resource counts as closeable if it has `close()`, `stop()`, `shutdown()`,
     or `cleanup()`. Prefer `close()` first.
   - Close exceptions should fail the test unless the existing resource contract
     already documents best-effort teardown. Do not swallow all exceptions by
     default.
   - `ensure_windows_cleanup()` should mirror simplebroker:
     `gc.collect()`, and on `sys.platform == "win32"` sleep briefly and run a
     second `gc.collect()`.
   - `sqlite_candidate_paths()` must include the main db, `-wal`, `-shm`, and
     `-journal` if present.
   - `database_files_releasable()` should adapt Weft's Windows rename probe:
     after GC, try to `Path.replace()` each candidate to a probe name and then
     restore it. Return `False` on `PermissionError`. Restore every file that
     was moved, and raise if restoration fails.
   - On non-Windows, `database_files_releasable()` may return `True` after GC.
     Unix can rename open files, so a successful rename there does not prove the
     same invariant.
   - `wait_for_database_release()` should poll with a short interval and raise a
     useful `RuntimeError` listing candidate paths if the files remain locked.
     Use a longer default budget on Windows, following Weft's 30 second
     preserve-database budget.

2. Add a fixture to `tests/conftest.py`.

   Recommended fixture:

```python
@pytest.fixture
def resource_tracker() -> Iterator[ResourceTracker]:
    tracker = ResourceTracker()
    try:
        yield tracker
    finally:
        tracker.close_all()
        ensure_windows_cleanup()
```

   Use this fixture in helper fixtures and in tests that directly create
   resources. Do not make it a global mutable registry. A per-test fixture is
   enough.

3. Register the shared `memory` fixture.

   Change the fixture from manual close-only teardown to tracker-owned teardown,
   or keep the explicit `finally: instance.close()` and then run the cleanup
   helper. The important invariant is that the fixture closes before pytest
   cleans `tmp_path`.

   Good shape:

```python
@pytest.fixture
def memory(vault_path: Path, resource_tracker: ResourceTracker) -> Iterator[Engram]:
    instance = resource_tracker.register(
        Engram.init(vault_path, embedder=DeterministicEmbedder())
    )
    yield instance
```

   Do not hide an `Engram.close()` failure.

4. Add factory fixtures only where they remove duplication.

   Useful factories:

   - `engram_factory(path, **kwargs) -> Engram`
   - `store_factory(path, **kwargs) -> SQLiteStateStore`
   - `runner_factory(path) -> SQLiteRunner`
   - `lance_index_factory(path, **kwargs) -> LanceIndex`

   Keep them test-local. They exist to ensure cleanup, not to abstract Engram's
   public API.

5. Audit direct resource construction in tests.

   Use:

```bash
rg "Engram\\.(init|open)\\(|EngramClient\\(|SQLiteStateStore\\(|SQLiteRunner\\(|LanceIndex\\(" tests --glob '*.py'
```

   For every match, choose one:

   - use an existing context manager
   - register the resource with `resource_tracker`
   - close it in a `finally` block and call `ensure_windows_cleanup()`

   Do not convert behavior tests into mock tests just to avoid cleanup.

6. Adapt Weft's file-release logic to Engram's embedded Weft paths.

   Engram owns at least two sqlite-backed paths in a vault after the backend
   foundation work:

   - state db, derived from `engram._constants.DEFAULT_SQLITE_FILENAME`
     (currently `engram.db`)
   - embedded Weft broker db, currently under the vault as `broker.db`

   If those names differ in the current code, use the constants or helper
   functions that production code uses. Do not duplicate stale path literals
   when a constant exists.

   Add a helper such as:

```python
from engram._constants import DEFAULT_SQLITE_FILENAME

def wait_for_vault_database_release(vault_path: Path) -> None:
    paths = [
        *sqlite_candidate_paths(vault_path / DEFAULT_SQLITE_FILENAME),
        *sqlite_candidate_paths(vault_path / "broker.db"),
    ]
    wait_for_database_release(paths, timeout=30.0 if sys.platform == "win32" else 1.0)
```

   Prefer deriving the state path from `DEFAULT_SQLITE_FILENAME` and the broker
   path from `Engram.status().broker_path` or the embedded Weft config helpers
   if the test already has a live `Engram`. If no constant exists for the broker
   path, add one only if production already has repeated literals. Do not add a
   broad path registry.

7. Revisit runtime Weft usage after Task 3.

   In `engram/runtime/weft.py`, any direct Weft broker/queue access must be in a
   context manager or `try/finally` close block. If the installed `WeftClient`
   still has no `close()` method, do not call one. Instead, keep client creation
   short-lived and rely on Weft/simplebroker queue closure and file-release
   probing.

   Counterargument to watch: it is tempting to add `EngramWeftRuntime.close()`.
   Do that only if there is an actual long-lived runtime object. The current
   intended runtime module is function-based and should not grow state just for
   cleanup aesthetics.

8. Add cleanup harness tests.

   Create `tests/test_resource_cleanup.py`.

   Required tests:

   - `ResourceTracker` closes resources in reverse order.
   - `ResourceTracker` surfaces close failures.
   - `ensure_windows_cleanup()` runs GC and, under a monkeypatched Windows
     platform, performs the second GC after a sleep.
   - `database_files_releasable()` restores every renamed file after a successful
     Windows probe.
   - `wait_for_database_release()` waits through transient locked states and
     raises with path details when files stay locked. This can use monkeypatched
     helper functions; do not use real OS file locking for this narrow timing
     test.
   - An integration test creates a real temporary vault, initializes Engram with
     deterministic embeddings and embedded Weft init, closes it through the
     tracker, waits for vault database release, and then removes the temp root.

   The integration test should use real SQLite and real Engram. It may keep Weft
   task submission shimmed if the test is about cleanup, but it must not mock
   `SQLiteRunner.close()`, `SQLiteStateStore.close()`, or `Engram.close()`.

9. Add a regression test for untracked direct resources if practical.

   This can be a static test that scans test files for direct construction and
   enforces one of the approved cleanup patterns. Keep it conservative. If a
   static test becomes brittle, skip it and rely on the manual `rg` gate in this
   plan.

Do not:

- Add production lifecycle abstractions only for test cleanup.
- Add a global test registry that crosses test boundaries.
- Ignore tempdir cleanup errors as the main proof.
- Mock the close method of the resource whose handle release you are proving.
- Copy Weft's process/PID teardown wholesale. Engram only needs that if Engram
  tests start real Weft managers/tasks that can outlive a test.
- Change backend schema, migration behavior, command output, or public API.

Tests:

```bash
./.venv/bin/python -m pytest tests/test_resource_cleanup.py
./.venv/bin/python -m pytest tests/core/test_memory.py tests/client/test_client.py
./.venv/bin/python -m pytest tests/test_background.py
```

Also run:

```bash
rg "Engram\\.(init|open)\\(|EngramClient\\(|SQLiteStateStore\\(|SQLiteRunner\\(|LanceIndex\\(" tests --glob '*.py'
```

Every match must be tracked, context-managed, or closed in `finally`.

Stop and re-evaluate if:

- The local Weft version's cleanup APIs differ from `../weft`. Inspect the
  installed package and adapt to the actual API in use.
- LanceDB exposes no meaningful close/release operation. In that case, document
  the handle-release strategy in the test helper and prove tempdir removal after
  dropping references and forcing GC.
- The cleanup helper grows into a general lifecycle framework. Keep it a small
  test harness.

Done signal:

- Cleanup harness tests pass.
- Existing Engram tests that create file-backed resources use the harness or an
  explicit `finally` close.
- Windows-specific file-release behavior is represented by tests, not comments.
- Manual construction search has no unexplained leaks.

### 3. Split Weft Runtime Init/Submission From The Background Worker Adapter

Outcome:

- `engram.core.memory` no longer imports `engram.background`.
- `engram.background` keeps only worker callback behavior and any helper that
  is strictly worker-adapter behavior.
- `Engram.init()` and `Engram.record()` keep current runtime behavior.
- The split starts with Weft initialization using Engram-derived vault values,
  then verifies the created runtime paths before adding Engram-specific task
  submission behavior.

Files to touch:

- `engram/runtime/__init__.py`
- `engram/runtime/weft.py`
- `engram/background.py`
- `engram/core/memory.py`
- `tests/test_background.py`
- `tests/conftest.py`

Read first:

- `engram/background.py`
- `engram/core/memory.py`
- `engram/_internal_tasks.py`
- `tests/test_background.py`
- `tests/conftest.py`
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-13], [EWM-15],
  [EWM-16], [EWM-22], [EWM-23]

Implementation steps:

1. Create `engram/runtime/__init__.py` with a short package docstring.
2. Create `engram/runtime/weft.py`.
3. Move the Weft initialization path first:
   - `_weft_runtime_root_and_config`
   - `initialize_embedded_weft_project`
4. Keep the implementation using Engram-owned values from
   `load_embedded_weft_overrides()` and `load_embedded_weft_config()`.
   Specifically preserve:
   - `WEFT_DIRECTORY_NAME` derived from the resolved vault directory name
   - `WEFT_DEFAULT_DB_LOCATION = ""`
   - `WEFT_DEFAULT_DB_NAME = "<vault-name>/broker.db"`
   - Weft root set to `vault_path.parent`
5. Update `Engram.init()` to call
   `weft_runtime.initialize_embedded_weft_project()` and run the narrow init
   tests before moving task submission. This confirms the vault directory,
   embedded Weft metadata directory, config, and broker assumptions are still
   correct before the worker submission code moves.
6. Move task submission only after the init path is green:
   - `submit_process_item_task`
   - `submit_internal_task`
7. Keep `process_memory_task()` in `engram/background.py`, because
   `_internal_tasks.py` points Weft at `engram.background:process_memory_task`.
8. In `engram/core/memory.py`, import the runtime module, not individual
   functions:

```python
from engram.runtime import weft as weft_runtime
```

Then call:

```python
weft_runtime.initialize_embedded_weft_project(...)
weft_runtime.submit_process_item_task(...)
```

Module import is preferred here because tests can monkeypatch one module
attribute without relying on stale function references.

9. Update `tests/conftest.py` monkeypatch targets:
   - from `engram.core.memory.submit_process_item_task`
   - to `engram.core.memory.weft_runtime.submit_process_item_task`
10. Update `tests/test_background.py`:
   - tests for runtime init/submission should import and patch
     `engram.runtime.weft`
   - worker tests should continue to import `engram.background`

Do not:

- Leave re-export aliases in `engram.background` for moved functions. Move repo
  users to the canonical runtime module in the same change.
- Put `process_memory_task()` in the runtime module. That would move the worker
  adapter down into the runtime boundary and recreate ambiguity.
- Add a service locator or dependency injection container.
- Disable background behavior in `Engram.init()` or `Engram.record()`.

Tests:

- Update existing background tests rather than replacing them.
- Run the initialization test immediately after moving only the init path:

```bash
./.venv/bin/python -m pytest tests/test_background.py -k "initialize_embedded_weft_project or init_can_disable_embedded_weft_autostart"
```

- The init proof should assert that Engram's resolved vault path is what drives
  Weft's root, metadata directory, default DB location, and broker DB name.
- Keep the Weft API monkeypatched in tests. Weft is an external execution
  substrate and is acceptable to shim.
- Do not mock `Engram.repair_item()` in the worker success-path test. That test
  should keep proving the real local repair operation can run through the worker
  boundary.

Stop and re-evaluate if:

- `Engram.init()` behavior changes.
- `Engram.record()` no longer records a failure when submission raises.
- The new runtime module starts importing `engram.core`, `engram.store`, or
  `engram.index`.

Done signal:

- `engram.core.memory` has no import of `engram.background`.
- The import cycle detector from Task 1 no longer reports a cycle.
- Weft initialization tests pass before submission tests are updated.
- Runtime init/submission tests still prove the vault path maps to the embedded
  Weft directory and broker path.

### 4. Move Worker Open-Failure Recording Behind A Domain Method

Outcome:

- `engram.background` does not import or call `open_state_store`.
- The narrow worker failure branch still records processing failure when
  possible.

Files to touch:

- `engram/core/memory.py`
- `engram/background.py`
- `tests/test_background.py`

Read first:

- `engram/background.py` `_mark_failed()`
- `engram/core/memory.py` `repair_item()`, `_submit_background_task()`, and
  store initialization
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-17] through [EWM-19],
  [EWM-25], [EWM-26]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-7]

Implementation steps:

1. Add a narrow domain-level classmethod or staticmethod on `Engram`, for
   example:

```python
@staticmethod
def record_processing_failure_for_vault(
    vault_path: Path,
    *,
    item_id: int,
    error: str,
    updated_at: int | None = None,
) -> None:
    ...
```

2. Implement it in `engram/core/memory.py` using `open_state_store()` and the
   existing store method. This keeps storage access inside the domain layer.
3. Use `time.time_ns()` if `updated_at` is `None`.
4. Update `engram/background.py` so `_mark_failed()` imports or uses `Engram`
   and calls this domain method. Keep the import lazy inside the worker path if
   needed to avoid import-time coupling.
5. If `_mark_failed()` becomes a one-line wrapper, consider deleting it and
   calling the domain helper directly inside the `except` branch. Prefer fewer
   layers if the code remains readable.

Do not:

- Add a generic "failure recorder" abstraction.
- Catch and suppress all failures in the domain helper. Let storage failures
  propagate to the existing best-effort catch in `process_memory_task()`.
- Change `repair_item()` failure handling. That path already owns normal repair
  failure recording.

Tests:

- Add or update a background test for the branch where `Engram.open()` fails
  before `memory` is assigned but the state store is still usable.
- Use a real initialized vault and real SQLite state for the proof.
- It is acceptable to monkeypatch `Engram.open()` to raise in this test because
  the branch under test is the worker fallback, not normal domain processing.
- Assert observable state after the call:
  - the worker raises the original exception
  - inspecting the real state store shows `failed_processing_items == 1`
  - the failed item contains the recorded error
- If `Engram.open()` is monkeypatched to force this branch, do not use
  `Engram.open()` for the postcondition inside the same monkeypatch scope. Use
  `SQLiteStateStore(vault_path, create=False)` or a test-only inspection helper
  and close it in `finally`.

Stop and re-evaluate if:

- You need to import `engram.store.*` in `engram.background`.
- You are tempted to make this helper public on `EngramClient`. This is a
  low-level worker recovery hook, not an application API.

Done signal:

- `rg "engram.store|open_state_store" engram/background.py` returns no storage
  import or call.
- Worker success and failure tests pass with real SQLite.

### 5. Remove The Index Adapter's Dependency On Core Embeddings

Outcome:

- `engram/index/lance.py` no longer imports `engram.core.embeddings`.
- `Engram` remains responsible for choosing and injecting the embedding
  function.

Files to touch:

- `engram/index/lance.py`
- `engram/core/memory.py` only if constructor call sites need adjustment
- `tests/index/test_lance.py`
- any test that constructs `LanceIndex` directly

Read first:

- `engram/index/lance.py`
- `engram/core/embeddings.py`
- `engram/core/memory.py` constructor
- `tests/index/test_lance.py`

Implementation steps:

1. Remove this import from `engram/index/lance.py`:

```python
from engram.core.embeddings import default_lance_embedding_function
```

2. Make `embedding_function` required in `LanceIndex.__init__()`.
3. Remove fallback creation inside `LanceIndex.__init__()`.
4. Keep the existing `Engram` constructor injection:

```python
embedding_function=embedder_to_lance_function(self._embedder)
```

5. Update direct `LanceIndex` tests to pass a deterministic Lance embedding
   function explicitly. `tests/index/test_lance.py` already does this; verify
   all call sites.

Do not:

- Move all embedding code into `engram.index` as part of this task. That is a
  larger design question.
- Add a second default embedding path inside `LanceIndex`.
- Add lazy imports from `engram.core` inside `LanceIndex`.

Tests:

- Add or update an architecture assertion that `engram.index.*` cannot import
  `engram.core.*`.
- Run `tests/index/test_lance.py`.
- Run a core memory test that proves `Engram` still constructs and searches the
  index through injection.

Stop and re-evaluate if:

- A production caller outside tests constructs `LanceIndex` without an
  embedding function. If found, update that caller to inject explicitly rather
  than restoring the fallback.

Done signal:

- `rg "engram.core" engram/index -n` returns no matches.
- `LanceIndex` still supports text and vector search in the existing index
  test.

### 6. Make StateStoreCore Truly Backend-Neutral

Outcome:

- `engram/store/core.py` consumes a `StateSQL` namespace but does not import a
  concrete SQLite SQL namespace.
- `SQLiteStateStore` owns passing SQLite SQL into the core.

Files to touch:

- `engram/store/core.py`
- `engram/store/sqlite.py`
- `tests/store/test_sqlite.py`
- `tests/architecture/test_import_boundaries.py`

Read first:

- `engram/store/core.py`
- `engram/store/sqlite.py`
- `engram/store/_sql/base.py`
- `engram/store/_sql/sqlite.py`
- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`
  sections about SQL namespaces and backend portability

Implementation steps:

1. Remove `from engram.store._sql import sqlite as sqlite_sql` from
   `engram/store/core.py`.
2. Change `StateStoreCore.__init__()` from a defaulted SQL namespace to a
   required SQL namespace:

```python
def __init__(self, runner: SQLRunner, sql: StateSQL) -> None:
    self._runner = runner
    self._sql = sql
```

3. Import `sqlite_sql` in `engram/store/sqlite.py`.
4. Construct the core as:

```python
self._core = StateStoreCore(self._runner, sqlite_sql)
```

5. Keep SQL operation names and behavior unchanged.

Do not:

- Add a generic SQL builder.
- Add a PG namespace.
- Move schema migration SQL into `StateStoreCore`.
- Reintroduce `SELECT *`.

Tests:

- Add or strengthen an architecture assertion that `engram.store.core` cannot
  import `engram.store._sql.sqlite`.
- Existing store tests should continue to use real SQLite.
- Do not mock `SQLRunner` for this proof. The behavior that matters is real
  persistence through the SQLite wrapper.

Stop and re-evaluate if:

- You need conditional logic in `StateStoreCore` based on backend name.
- You need SQLite-specific SQL in the core.

Done signal:

- `rg "sqlite" engram/store/core.py` returns no concrete SQLite namespace
  import.
- Store tests still pass.

### 7. Remove The CLI Package-Root Import Loophole

Outcome:

- `engram/cli.py` does not import from package root `engram`.
- Running `engram version` does not pull in client/core through
  `engram/__init__.py`.

Files to touch:

- `engram/cli.py`
- `tests/architecture/test_import_boundaries.py`
- `tests/cli/test_cli.py` if needed

Read first:

- `engram/cli.py`
- `engram/__init__.py`
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-4],
  [FCI-15], [FCI-24]

Implementation steps:

1. Change:

```python
from engram import __version__
```

to:

```python
from engram._constants import __version__
```

2. Keep package-root `__version__` re-export in `engram/__init__.py`.
3. Add or strengthen an architecture test that production `engram.cli` cannot
   import package root `engram`.

Do not:

- Remove `__version__` from package root.
- Change `engram version` output.

Tests:

- Run existing CLI tests.
- Add a narrow assertion in architecture tests if the import-boundary visitor
  does not already catch it.

Stop and re-evaluate if:

- Changing this import causes a circular import elsewhere. That would signal a
  different package-root problem that should be reported before broad fixes.

Done signal:

- `engram/cli.py` imports version directly from `_constants`.
- CLI tests still pass.

### 8. Clean Up Test Private Access Without Adding API For Tests

Outcome:

- Tests no longer use `memory._store` or `memory._index` as a convenience.
- Any remaining private access is explicitly limited to invariant tests with no
  public inspection surface.

Files to touch:

- `tests/core/test_memory.py`
- `tests/core/test_context.py`
- `tests/cli/test_cli.py`
- Optional helper: `tests/fixtures/state_inspection.py`

Read first:

- `docs/specs/15-foundation-contracts-and-invariants.md` lines around the
  mental model and [FCI-35] through [FCI-39]
- Current tests listed above
- `engram/store/sqlite.py`
- `engram/index/lance.py`

Recommended helper approach:

- Add `tests/fixtures/state_inspection.py` only if it reduces duplication.
- Keep helpers test-only and explicit. Suggested helpers:

```python
def recent_items(vault_path: Path, *, tier: int, limit: int) -> list[MemoryItem]:
    ...

def children(vault_path: Path, parent_id: int) -> list[MemoryItem]:
    ...

def delete_index_item(vault_path: Path, item_id: int) -> None:
    ...
```

Implementation notes:

- `recent_items()` and `children()` can use `SQLiteStateStore(vault_path,
  create=False)` and close it in `finally`.
- `delete_index_item()` can instantiate `LanceIndex` with a deterministic Lance
  embedding function and call `delete_item()`.
- Do not route these helpers through `memory._store` or `memory._index`.
- Do not add `Engram.children()` or `Engram.delete_index_item()` only for tests.
  A public API addition must serve product behavior, not test convenience.

Known places to address:

- `tests/cli/test_cli.py`
  - Replace private store reads used only to find episode/arc IDs with the
    test-only storage inspection helper.
  - Replace private index deletion used to simulate drift with the test-only
    index helper.
- `tests/core/test_context.py`
  - Replace private store traversal used for round-trip validation with the
    storage inspection helper.
  - Replace recent-moment baseline reads with the storage inspection helper.
- `tests/core/test_memory.py`
  - Replace index drift setup with the test-only index helper.
  - Replace arc child inspection with the storage inspection helper.
  - The direct call to `_coalesce_available_tier_operation()` may remain only
    because it is proving generic tier coalescing behavior that has no public
    surface. Add a short comment before it explaining that exception.
  - Avoid `memory._store.create_summary_item()` if possible by using
    `SQLiteStateStore` directly through a helper. If direct state setup is
    still needed, make it a named helper such as `create_summary_item_for_test`
    so the reason is obvious.

Do not:

- Add public methods just so tests can avoid private access.
- Replace real SQLite or LanceDB with mocks.
- Use monkeypatch call counts as primary proof.

Tests:

- Run the updated test files.
- Run the architecture tests.
- Search for remaining private access:

```bash
rg "\\._store|\\._index" tests engram --glob '*.py'
```

Any remaining match must be in `engram/core/memory.py` or must have a nearby
comment in tests explaining why no public/test-helper path is appropriate.

Stop and re-evaluate if:

- Test helpers start duplicating production behavior rather than inspecting
  state.
- A test becomes less behavior-focused after removing private access.

Done signal:

- Convenience private access is gone from CLI and context tests.
- Remaining private access, if any, is narrow and justified.

### 9. Update The Foundation Spec For The Runtime Boundary

Outcome:

- The spec reflects the intended distinction between the embedded Weft runtime
  integration and the Weft worker adapter.

Files to touch:

- `docs/specs/15-foundation-contracts-and-invariants.md`

Read first:

- The current [FCI-1] through [FCI-7] section.
- The final module layout after Tasks 3 and 4.

Implementation steps:

1. Update [FCI-1] or add a small clarifying note near [FCI-1] through [FCI-7]:
   - `engram.core.*` must not import `engram.background`.
   - `engram.background` is the worker adapter.
   - A narrowly scoped runtime module may own embedded Weft bootstrap and
     submission if it does not import core, store, index, commands, client, CLI,
     or dogfood.
2. Update the implementation mapping table if it names background ownership in
   a way that is now stale.
3. Keep the requirement that background uses public/domain methods.

Do not:

- Use the spec update to weaken the architecture direction.
- Add broad permission for core to import arbitrary runtime or adapter code.
- Change access-score, CLI, command, or storage contracts.

Tests:

- Documentation verification is by inspection plus architecture tests. There is
  no runtime test for the prose itself.

Stop and re-evaluate if:

- The spec wording would permit `engram.core.memory` to import
  `engram.background` again.
- The spec wording would permit runtime code to own memory state.

Done signal:

- The spec and architecture tests agree on the new boundary.

### 10. Run Final Verification Gates

Outcome:

- The cleanup is proven at the narrow and broad levels.

Commands:

```bash
./.venv/bin/python -m pytest tests/architecture/test_import_boundaries.py
./.venv/bin/python -m pytest tests/test_resource_cleanup.py
./.venv/bin/python -m pytest tests/test_background.py
./.venv/bin/python -m pytest tests/index/test_lance.py
./.venv/bin/python -m pytest tests/store/test_sqlite.py
./.venv/bin/python -m pytest tests/store/test_memory_ids.py
./.venv/bin/python -m pytest tests/core/test_memory.py tests/core/test_context.py
./.venv/bin/python -m pytest tests/client/test_client.py tests/commands/test_memory_commands.py
./.venv/bin/python -m pytest tests/cli/test_cli.py
./.venv/bin/python -m pytest
./.venv/bin/ruff check engram tests
./.venv/bin/mypy engram
```

If `.venv` does not exist, stop and inspect the repo setup. The repository
instructions say to use in-repo virtualenv binaries after environment setup.
Do not silently rely on global `pytest`, `ruff`, or `mypy` unless you record
why the local environment is unavailable.

Additional manual checks:

```bash
rg "from engram.background|import engram.background" engram/core engram/index engram/store --glob '*.py'
rg "from engram import __version__" engram/cli.py
rg "from engram.core" engram/index --glob '*.py'
rg "engram.store._sql.sqlite|sqlite_sql" engram/store/core.py
rg "open_state_store|engram.store" engram/background.py
rg "\\._store|\\._index" engram tests --glob '*.py'
rg "Engram\\.(init|open)\\(|EngramClient\\(|SQLiteStateStore\\(|SQLiteRunner\\(|LanceIndex\\(" tests --glob '*.py'
```

Expected results:

- No core/index/store import of `engram.background`.
- No CLI import of `__version__` through package root.
- No index import of `engram.core`.
- No concrete SQLite SQL namespace import in `engram/store/core.py`.
- No direct store access in `engram/background.py`.
- Remaining private access search results are either inside `engram/core/memory.py`
  or are justified test-only invariant exceptions.
- Every direct file-backed test resource construction is tracked, context-managed,
  or closed in `finally`.

## 9. Testing Strategy

Use red-green TDD for guardrails:

1. Strengthen architecture tests first and watch them fail.
2. Add the explicit cleanup harness before refactoring runtime or storage tests.
3. Fix one boundary at a time.
4. Re-run the targeted architecture test after each boundary.

Use real dependencies where they are part of the contract:

- Real SQLite for state behavior.
- Real LanceDB for index drift and search behavior.
- Real `Engram` for worker success-path behavior.
- Real command/CLI path for CLI output shape behavior.
- Real close paths for cleanup behavior. Do not mock the resource whose handle
  release you are proving.

Mock only external, slow, or nondeterministic boundaries:

- Weft client submission can be monkeypatched.
- Weft init command can be monkeypatched.
- LLM summarization can remain shimmed by existing fixtures.
- `Engram.open()` can be monkeypatched only for the narrow worker
  open-failure fallback test.

Do not test these changes with only import mocks or call counts. The meaningful
proof is:

- imports point the right direction
- runtime behavior still works
- failure state is still recorded
- search and rebuild still work
- CLI output does not change
- resources close before tempdir cleanup, including SQLite sidecar files on
  Windows

## 10. Rollback And Safety

This work does not change persisted schema or migrate data. Rollback is a code
revert if behavior regresses.

Riskier edges:

- Moving Weft functions can break monkeypatch targets and internal tests.
  Mitigation: update tests in the same task and do not leave aliases behind.
- Changing `LanceIndex` constructor requirements can break direct internal
  call sites. Mitigation: search all `LanceIndex(` call sites before and after.
- Changing worker failure recording can hide background failures. Mitigation:
  add the open-failure fallback test with real SQLite state.
- Strengthened architecture tests can over-ban legitimate imports. Mitigation:
  inspect each violation and update the spec and test together if an intended
  dependency is genuinely needed.
- Cleanup harness changes can mask leaks if they become too forgiving.
  Mitigation: fail on close errors by default, test file-release waiting, and
  keep `ignore_errors=True` out of the main proof path.

No rollout sequencing is needed beyond keeping tasks small. Do not ship a
half-finished state where architecture tests fail.

## 11. Out Of Scope

Do not do any of the following in this plan:

- implement Postgres
- add backend plugin discovery
- add a new public CLI command
- change command JSON shapes
- change package-root public exports
- redesign `EngramClient`
- redesign dogfood replay
- move all embedding code between packages
- add an ORM or SQL builder
- change state schema version
- change migration policy
- change coalescing behavior
- change context assembly scoring
- implement Weft manager/process cleanup unless a test actually starts live Weft
  managers or tasks that can outlive the test

## 12. Independent Review Loop

After drafting and before implementation, have another agent or reviewer read:

- this plan
- `docs/specs/15-foundation-contracts-and-invariants.md`
- `docs/specs/14-embedded-weft-execution-model.md`
- `engram/core/memory.py`
- `engram/background.py`
- `engram/index/lance.py`
- `engram/store/core.py`
- `tests/architecture/test_import_boundaries.py`
- `tests/conftest.py`
- `tests/fixtures/resource_cleanup.py` if added
- `../weft/tests/helpers/weft_harness.py`
- `../simplebroker/tests/helper_scripts/cleanup.py`

Review prompt:

> Read the layering cleanup plan and the listed files. Do not implement
> anything. Look for bad dependency directions, hidden compatibility breaks,
> weak tests, and places where the plan could be misread by an engineer with no
> Engram context. Could you implement this confidently and correctly? If not,
> name the exact ambiguity or bad decision.

Every review point must be handled explicitly:

- update the plan
- explain why the current path is still better
- or mark it out of scope with reasoning

## 13. Author Self-Review Notes

First-pass concerns checked while writing this plan:

- The plan does not solve the core/background cycle by merely renaming
  `engram.background`; it separates runtime init/submission from the worker
  callback.
- The plan preserves `Engram.init()` and `Engram.record()` behavior instead of
  making background submission opt-in.
- The plan keeps the worker callback target stable:
  `engram.background:process_memory_task`.
- The plan avoids adding public APIs for test convenience. Test helpers are
  allowed only for inspection and drift simulation.
- The plan does not require Postgres work.
- The plan does not require schema changes.
- The plan explicitly strengthens architecture tests before production code
  changes.
- User correction incorporated: the Weft split should first prove
  Engram-derived Weft initialization creates and targets the expected runtime
  paths, then add Engram-specific task submission and worker pieces.
- User correction incorporated: test cleanup is explicit. The plan adapts
  Weft's harness for database release probing and tempdir retry, plus
  simplebroker's GC/Windows delay and resource-tracking cleanup patterns.
- Fresh-eye correction incorporated: the cleanup harness is Task 2, before the
  Weft runtime split, so handle safety is in place before tests start creating
  new embedded Weft/runtime resources.

If implementation evidence contradicts any of these assumptions, stop and
revise this plan before continuing.
