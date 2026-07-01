# Weft And SimpleBroker Dependency Refresh Plan

Status: implemented
Source spec: dependency and embedded-runtime compatibility change.

## Goal

Update Engram's Weft and SimpleBroker dependency floors to the current released
values without adding maximum-version caps, then refresh the lockfile and prove
the embedded Weft runtime, Weft agent summary path, SQLite broker sidecars, and
retrieval embedding path still work. As of 2026-07-01, the current PyPI release
values are `weft==0.9.84`, `simplebroker==4.9.0`, and
`simplebroker-pg==2.4.0`.

## Source Documents

- PyPI JSON API: `https://pypi.org/pypi/weft/json`
- PyPI JSON API: `https://pypi.org/pypi/simplebroker/json`
- PyPI JSON API: `https://pypi.org/pypi/simplebroker-pg/json`
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-1.1], [LAS-17],
  [LAS-18], [LAS-19]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-3],
  [EWM-4], [EWM-13], [EWM-17], [EWM-19], [EWM-23], [EWM-24]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-7],
  [FCI-7a], [FCI-36], [FCI-37]
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/07-codex-corpus-validation.md`
- `../weft/pyproject.toml`
- `../weft/docs/specifications/05-Message_Flow_and_State.md`
- `../weft/docs/specifications/10-CLI_Interface.md`

## Context And Key Files

Files to modify:

- `pyproject.toml`
- `uv.lock`
- `docs/implementation/04-minimum-memory-slice.md`, only if the Weft agent
  runtime facts in the current implementation note are stale after the update
- this plan, to record final observed verification

Files to read before editing:

- `pyproject.toml`, because it owns package dependency floors.
- `uv.lock`, because it currently resolves stale values: `weft==0.9.9`,
  `simplebroker==3.1.9`, and `simplebroker-pg==1.0.5`.
- `engram/runtime/weft.py`, because it is the narrow embedded-Weft boundary
  and imports `WeftClient`, `cmd_init`, and `build_context`.
- `engram/_constants.py`, because it translates Engram-owned embedded-Weft env
  vars and forces vault-local Weft paths.
- `engram/_internal_tasks.py`, because it builds the code-owned internal
  `TaskSpec` used for background item processing.
- `engram/background.py`, because it is the Weft worker callback boundary.
- `engram/core/llm_tasks.py`, because it imports Weft's agent runtime directly
  for summary extraction.
- `engram/core/embeddings.py` and `engram/index/lance.py`, because they own
  vector embedding and LanceDB retrieval behavior.
- `tests/test_constants.py`, `tests/test_background.py`,
  `tests/core/test_llm_tasks.py`, `tests/core/test_memory.py`,
  `tests/index/test_lance.py`, and `tests/test_resource_cleanup.py`.

Current dependency facts:

- `pyproject.toml` currently declares `simplebroker[pg]>=3.2.0` and
  `weft[docker]>=0.9.11`.
- Current Weft declares `simplebroker>=4.8.0` and the `docker` extra declares
  `weft-docker>=0.9.70`.
- Current SimpleBroker's `pg` extra declares `simplebroker-pg>=2.4.0`.
- Engram does not directly depend on `simplebroker-pg`; it comes through
  `simplebroker[pg]`.
- Engram does not directly depend on `weft-docker`; it comes through
  `weft[docker]`.

Current runtime facts:

- Embedded Weft initialization and task submission are Python API calls, not
  shell calls.
- Engram stores memory truth in SQLite and only stores Weft task correlation
  as inspection state.
- Engram's Weft internal task is a function task:
  `engram.background:process_memory_task`.
- Engram's LLM summary path uses Weft's in-process `llm` agent runtime through
  `execute_agent_target`, not Docker, Microsandbox, or macOS sandbox runners.
- Engram's vector embedding path is LanceDB-owned and separate from Weft and
  SimpleBroker. It still needs smoke coverage because the lock refresh may
  move shared transitive dependencies.
- The only current "sidecar" behavior in Engram is SQLite sidecar-file cleanup
  for the state DB and embedded broker DB. There is no production Weft sidecar
  runner usage to update.

Comprehension checks before editing:

- Can `engram/runtime/weft.py` still build an embedded context rooted at the
  vault parent while using the vault directory as Weft metadata?
- Can `engram/background.py` still process a memory item without relying on
  Weft queue-history replay?
- Does any Engram code directly select a Weft runner extra beyond the
  package-level `weft[docker]` install extra?

## Invariants And Constraints

- Do not add a maximum-version cap such as `<`, `~=`, or `==` in
  `pyproject.toml`.
- Set dependency floors to the current released values:
  `simplebroker[pg]>=4.9.0` and `weft[docker]>=0.9.84`.
- Do not add direct `simplebroker-pg` or `weft-docker` project dependencies
  unless the resolver cannot express the current released transitive values
  through the existing extras. Prefer keeping them transitive.
- Do not add `weft[all]`, `weft[macos-sandbox]`, or `weft[microsandbox]`.
  Engram does not currently use those runner paths.
- Do not change Engram's embedded-Weft storage ownership: the default broker
  remains `<vault>/broker.db`.
- Do not change internal TaskSpec names, payload shape, or function target
  unless current Weft rejects the existing contract. If that happens, stop and
  revise this plan before changing code.
- Do not make Weft queue history authoritative for memory recovery.
- Do not change vector embedding defaults or LanceDB schema as part of this
  dependency refresh unless a compatibility failure requires it.
- Do not update unrelated dependencies opportunistically. If `uv lock`
  changes unrelated packages because the resolver must, record why in the plan.
- Failure to import current Weft or SimpleBroker is fatal. Failure to use an
  optional Docker runner is not fatal unless an existing Engram test or runtime
  path depends on it.

Rollback before implementation:

- Reverting `pyproject.toml` and `uv.lock` should restore the previous
  dependency set.
- No storage migration is planned, so existing vaults should not need rollback
  work.
- If current Weft requires a code change to embedded init or task submission,
  that code change must be kept separate enough to revert independently from
  the lock refresh if review rejects it.

## Tasks

1. Confirm current release facts immediately before editing.
   - Files to touch: none.
   - Use PyPI JSON or `uv` resolver output, not memory.
   - Record the observed versions for `weft`, `simplebroker`,
     `simplebroker-pg`, and `weft-docker`.
   - Done signal: the plan and implementation notes name the same current
     release values used in the dependency update.
   - Stop and re-evaluate if PyPI has moved past the values listed in this
     plan before implementation starts.

2. Update package dependency floors.
   - Files to touch: `pyproject.toml`.
   - Change `simplebroker[pg]>=3.2.0` to `simplebroker[pg]>=4.9.0`.
   - Change `weft[docker]>=0.9.11` to `weft[docker]>=0.9.84`.
   - Do not add upper bounds.
   - Do not add direct dependency rows for `simplebroker-pg` or `weft-docker`
     unless task 3 proves the existing extras cannot resolve the current
     released versions.
   - Done signal: `pyproject.toml` expresses the intended floors without caps.

3. Refresh the lockfile with the relevant dependency family.
   - Files to touch: `uv.lock`.
   - Prefer:

     ```bash
     uv lock --upgrade-package weft --upgrade-package simplebroker \
       --upgrade-package simplebroker-pg --upgrade-package weft-docker
     ```

   - Inspect the diff for `weft`, `simplebroker`, `simplebroker-pg`,
     `weft-docker`, and any forced transitive dependency changes.
   - Done signal: `uv lock --check` passes and the lock resolves at least
     `weft==0.9.84`, `simplebroker==4.9.0`, `simplebroker-pg==2.4.0`, and
     `weft-docker==0.9.70` unless newer releases exist at implementation time.
   - Stop and re-evaluate if the resolver downgrades Weft extras, removes
     Docker support, or changes Python-version compatibility.

4. Prove embedded Weft init and submission compatibility.
   - Files to touch: tests only if current tests are too shallow for the new
     behavior.
   - Use real Weft import and real embedded init where feasible. Keep only
     process-spawning or external-service work mocked.
   - Run `tests/test_constants.py` and `tests/test_background.py`.
   - Add or tighten a smoke test if current Weft changes config keys or init
     artifacts in a way the existing tests do not catch.
   - Done signal: embedded init still creates the vault-local broker and task
     submission still builds an Engram-owned internal TaskSpec.

5. Prove Weft agent summary compatibility.
   - Files to touch: `engram/core/llm_tasks.py` and
     `tests/core/test_llm_tasks.py` only if current Weft changed
     `AgentSection`, `execute_agent_target`, or public output shapes.
   - Preserve the current policy: tests may shim the external LLM call, but
     should use real Weft model validation for `AgentSection`.
   - Done signal: summary tests pass and no new runner dependency is introduced.
   - Stop and re-evaluate if Weft removed the in-process `llm` runtime or now
     requires sidecar execution for this path.

6. Verify vector embedding and LanceDB behavior after the lock refresh.
   - Files to touch: none unless compatibility fails.
   - Run deterministic embedding and LanceDB tests using real LanceDB and the
     deterministic Lance embedding function.
   - Do not change `DEFAULT_EMBEDDING_MODEL` or Lance schema unless tests prove
     the dependency refresh broke the current path.
   - Done signal: indexing, vector search, and rebuild tests still pass.

7. Verify sidecar behavior.
   - Files to touch: none unless compatibility fails.
   - Confirm there is no production Weft sidecar runner path in Engram.
   - Run SQLite sidecar cleanup tests because embedded SimpleBroker broker DB
     files are part of vault cleanup.
   - Confirm `weft[docker]` still resolves `weft-docker`, but do not add Docker
     runtime smoke tests unless an existing Engram path uses Docker.
   - Done signal: cleanup tests pass and the lock includes the current released
     Docker extra package through `weft[docker]`.

8. Update documentation only where facts changed.
   - Files to touch: `docs/implementation/04-minimum-memory-slice.md`,
     `docs/implementation/05-local-vault-recovery.md`,
     `docs/implementation/07-codex-corpus-validation.md`, and this plan as
     needed.
   - Do not update specs unless behavior changes.
   - Done signal: docs do not describe stale Weft dependency or runtime facts.

## Testing Plan

Use real dependencies for dependency, import, embedded init, SQLite, LanceDB,
and `AgentSection` model validation. Mock only external LLM execution and
process-spawning boundaries where existing tests already do so.

Targeted tests:

```bash
uv lock --check
./.venv/bin/python -m pytest tests/test_constants.py -q
./.venv/bin/python -m pytest tests/test_background.py -q
./.venv/bin/python -m pytest tests/core/test_llm_tasks.py -q
./.venv/bin/python -m pytest tests/index/test_lance.py -q
./.venv/bin/python -m pytest tests/core/test_memory.py -q
./.venv/bin/python -m pytest tests/test_resource_cleanup.py -q
```

Import and version smoke:

```bash
./.venv/bin/python - <<'PY'
import importlib.metadata as md
import simplebroker
import weft

print("weft", md.version("weft"))
print("simplebroker", md.version("simplebroker"))
print("simplebroker-pg", md.version("simplebroker-pg"))
print("weft-docker", md.version("weft-docker"))
print("activity_waiter", hasattr(simplebroker, "create_activity_waiter_for_queues"))
PY
```

Embedded runtime smoke:

```bash
./.venv/bin/python - <<'PY'
from pathlib import Path
import tempfile

from engram.runtime.weft import initialize_embedded_weft_project

root = Path(tempfile.mkdtemp(prefix="engram-weft-refresh-"))
vault = root / ".engram"
initialize_embedded_weft_project(vault, autostart=False)
assert (vault / "broker.db").exists()
print(vault)
PY
```

Final gates:

```bash
./.venv/bin/python -m pytest
./.venv/bin/ruff check engram tests
./.venv/bin/ruff format --check engram tests
./.venv/bin/mypy engram
uv lock --check
```

## Verification And Gates

Per-task verification is listed in the task breakdown. Before claiming done:

- `pyproject.toml` has current lower bounds and no upper caps for Weft or
  SimpleBroker.
- `uv.lock` resolves current Weft, SimpleBroker, SimpleBroker PG, and Weft
  Docker extra packages.
- Embedded Weft init still creates vault-local runtime artifacts.
- Background task submission still uses Engram's code-owned TaskSpec inventory.
- Weft agent summary tests still validate the current Weft agent shape.
- Deterministic embedding and LanceDB tests still pass.
- SQLite sidecar cleanup tests still cover state and broker DB sidecars.
- Any documentation touched by dependency/runtime facts is current.

Operational success after release:

- New installs should no longer fail importing current Weft due to a stale
  SimpleBroker version.
- `engram init` should continue to initialize an embedded Weft runtime under
  the vault.
- `engram record` should continue to store the item even if downstream
  background processing fails, and status should expose the failure.

Observed implementation notes:

- PyPI release check on 2026-07-01 confirmed `weft==0.9.84`,
  `simplebroker==4.9.0`, `simplebroker-pg==2.4.0`, and
  `weft-docker==0.9.70`.
- `pyproject.toml` now declares `simplebroker[pg]>=4.9.0` and
  `weft[docker]>=0.9.84`, with no maximum-version caps.
- `uv lock --upgrade-package weft --upgrade-package simplebroker
  --upgrade-package simplebroker-pg --upgrade-package weft-docker` updated only
  the intended dependency family.
- `uv sync --all-extras` installed `weft==0.9.84`,
  `simplebroker==4.9.0`, `simplebroker-pg==2.4.0`, and
  `weft-docker==0.9.70` into the local environment.
- Import smoke confirmed SimpleBroker exposes
  `create_activity_waiter_for_queues`.
- Embedded Weft init smoke created a vault-local `broker.db` and `config.json`
  with `initialize_embedded_weft_project(..., autostart=False)`.
- Internal TaskSpec smoke confirmed `engram-process-item` still validates as a
  function task targeting `engram.background:process_memory_task`.
- No implementation docs needed updates. The current facts remained true:
  Engram uses Weft's in-process LLM agent path for summaries, LanceDB owns
  retrieval embeddings, and Engram has no production Weft sidecar runner path.

Observed verification:

```bash
uv lock --check
# Resolved 134 packages in 3ms

./.venv/bin/python -m pytest \
  tests/test_constants.py \
  tests/test_background.py \
  tests/core/test_llm_tasks.py \
  tests/index/test_lance.py \
  tests/core/test_memory.py \
  tests/test_resource_cleanup.py \
  -q
# 44 passed

./.venv/bin/python -m pytest
# 203 passed

./.venv/bin/ruff check engram tests
# All checks passed

./.venv/bin/ruff format --check engram tests
# 70 files already formatted

./.venv/bin/mypy engram
# Success: no issues found in 42 source files
```

## Independent Review Loop

Review the final diff with a runtime-boundary focus:

- Does the dependency change avoid upper caps?
- Does the lockfile show only expected resolver movement?
- Does Engram still keep memory truth out of Weft queue history?
- Did the implementer avoid adding unused runner extras or sidecar paths?
- Are the embedded runtime and Weft agent paths tested with real local
  dependencies where it matters?

Use a second reviewer or review agent after local gates pass. If no separate
reviewer is available, perform a fresh self-review against this plan and record
the skipped independent review explicitly.

## Out Of Scope

- Adding Postgres runtime support for Engram's state store.
- Adding Redis, Microsandbox, macOS sandbox, or `weft[all]` extras.
- Changing Engram's embedding model, LanceDB schema, or retrieval ranking.
- Changing internal TaskSpec names or payload shapes without a compatibility
  failure.
- Adding Docker runner smoke tests for Engram unless Engram gains a production
  Docker runner path.
- Updating unrelated dependencies for general freshness.

## Fresh-Eyes Review

Before implementation starts, ask a fresh reviewer to check:

- whether the plan overstates sidecar work, given Engram's current lack of a
  Weft sidecar runner path
- whether the selected dependency floors correctly express "current released
  value, no maximum cap"
- whether the testing plan would catch the import failure found when current
  Weft was run with stale SimpleBroker
- whether any Weft 0.9.84 behavior requires an Engram namespaced env mapping
  for TaskMonitor retention controls
