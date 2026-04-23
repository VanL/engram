# 2026-04-16 Basic Working App Plan

Status: Superseded

Superseded by `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`.
This plan remains useful as a record of the first usable local-app milestone,
but its assumptions about a manual process path and pending-work model are no
longer the forward execution architecture.

## 1. Goal

Turn the validated skeleton into a usable local Engram app: a single-user,
vault-based Python package and CLI that an agent or developer can actually use
across sessions for text memory.

The milestone is not "all ideas in the README shipped." The milestone is a
stable local product with a coherent API, a real CLI, durable storage, working
background processing, and enough multi-horizon behavior to dogfood on real
agent work.

## 2. Source Documents

Source workflow spec:
- `docs/specs/01-development-documentation-operating-model.md` [DOM-5],
  [DOM-8], [DOM-10], [DOM-11]

Source product specs:
- Expected to exist before implementation starts for this plan:
  - `docs/specs/10-minimum-memory-model.md`
  - `docs/specs/11-minimum-write-search-context-slice.md`

Source plan:
- `docs/plans/2026-04-16-initial-skeleton-validation-plan.md`

Supporting product context:
- `README.md`
- `engram/_constants.py`
- validation findings from the initial skeleton

## 3. Context and Key Files

Read first:
- the two minimum product specs from the skeleton phase
- the skeleton validation plan
- the implementation and test files added during the skeleton phase
- `README.md`
- `engram/_constants.py`

Current expected state before this plan starts:
- a working SQLite + LanceDB local slice exists
- moments and episodes work
- the write path is non-blocking at the public boundary
- the validation harness can compare Engram context to a naive baseline
- one canonical deferred-processing path exists and can be processed manually

Expected new or expanded surfaces in this plan:
- `docs/specs/12-local-app-surface.md`
- `docs/specs/13-context-assembly-and-arcs.md`
- `engram/cli.py`
- `engram/core/memory.py`
- `engram/core/context.py`
- `engram/core/coalesce.py`
- `engram/store/sqlite.py`
- `engram/index/lance.py`
- `tests/core/`
- `tests/cli/`

Required reading comprehension questions before code:
1. Which parts of the skeleton are validation scaffolding, and which are now
   intended product surface?
2. Which commands make the app usable for daily local work, and which README
   ideas should stay deferred?
3. What would need to break for arc tiers to be a mistake rather than a step
   forward?

## 4. Invariants and Constraints

- Extend the skeleton path rather than rewriting it.
  - Do not replace the core write/search/context path with a second app-only
    stack.
  - CLI and Python API must continue to share the same core logic.

- Keep the basic working app local and single-user.
  - SQLite remains the only supported state backend in this milestone.
  - LanceDB remains the retrieval index.
  - No hosted service, multi-user coordination, or Postgres support.

- Preserve rebuildability and source-of-truth ownership.
  - SQLite remains authoritative.
  - LanceDB remains rebuildable.
  - Recovery and reindexing should grow out of this invariant, not around it.

- Broaden the product only where the skeleton proved value.
  - If the validation harness did not show clear value for a feature, do not
    elevate that feature into the app milestone by default.

- Keep destructive semantics narrow.
  - Do not introduce deletion semantics in this milestone unless a spec is
    written first and the rollback story is clear.
  - Prefer pinning, status, rebuild, and inspection over deletion/export
    features in the first usable app.

- Add arcs only after episode quality is already protected.
  - Arc coalescing should not ship before episode summaries pass retrieval
    round-trip checks.
  - Context assembly must degrade gracefully if arc material is sparse.

- Keep background work observable.
  - A local user should be able to see pending, completed, and failed work.
  - Best-effort failures should be visible rather than silent.
  - Grow from the skeleton's durable pending-work model. Do not introduce a
    second execution path that bypasses it.

- Anti-mocking posture:
  - Real SQLite, real LanceDB, and real public CLI/API entry points for
    integration tests.
  - Mock only external model boundaries when necessary.

Rollout and rollback constraints:
- Keep schema and on-disk layout additive where practical.
- Add index rebuild and pending-work recovery before broadening the surface.
- If arc behavior reduces context quality, keep the app usable with the
  moment+episode path while arc work is disabled or hidden.
- If a continuous worker is added in this milestone, it must be a thin wrapper
  around the existing process path, not a replacement for it.

Observable success for this milestone:
- A developer can install the package, initialize a vault, record text across
  sessions, search it, inspect moments/episodes/arcs, build context, pin
  important items, and recover from background lag or index drift.
- The same user can dogfood this on a real local workflow without manually
  touching the underlying SQLite or LanceDB stores.

## 5. Tasks

1. Convert the skeleton contracts into app-level product specs.
   - Files to touch:
     - `docs/specs/12-local-app-surface.md`
     - `docs/specs/13-context-assembly-and-arcs.md`
     - update existing minimum specs as needed
     - `docs/specs/00-specs-index.md`
   - Read first:
     - skeleton specs and validation findings
   - Outcome:
     - stable local-app contracts exist for API, CLI, vault lifecycle,
       retrieval semantics, deferred-processing behavior, context assembly, and
       arc behavior
   - Stop and re-evaluate if:
     - the specs start promising hosted or multi-user behavior
     - deletion, export/import, or blob handling becomes load-bearing to the
       milestone
   - Done signal:
     - the app milestone can be implemented from specs rather than from README

2. Harden local vault lifecycle, recovery, and status surfaces.
   - Files to touch:
     - `engram/core/memory.py`
     - `engram/store/sqlite.py`
     - `engram/cli.py`
     - `tests/store/`
     - `tests/cli/`
   - Read first:
     - local-app spec sections for vault lifecycle and recovery
   - Outcome:
     - vault init/open is stable
     - pending-work status is queryable
     - index rebuild exists as a one-way restore from SQLite state into
       LanceDB, not a bidirectional merge
     - a continuous worker may be added, but only as a wrapper around the same
       process function proven in the skeleton
     - configuration and schema versioning are explicit
   - Stop and re-evaluate if:
     - recovery requires manual SQLite edits
     - the rebuild path starts treating LanceDB as authoritative
   - Done signal:
     - a user can recover a local vault without hand-editing storage

3. Extend context assembly to the first usable full hierarchy.
   - Files to touch:
     - `engram/core/coalesce.py`
     - `engram/core/context.py`
     - `engram/core/memory.py`
     - `tests/core/test_coalesce.py`
     - `tests/core/test_context.py`
   - Read first:
     - context and arc specs from Task 1
   - Outcome:
     - arc tier exists
     - arc creation reuses the same semantic-boundary algorithm already proven
       for episodes, but runs over ordered episodes instead of moments
     - context assembly supports the intended four-bucket model
     - topic-biased context assembly remains available
     - sparse-corpus behavior stays sane when arc material is limited
   - Stop and re-evaluate if:
     - arc generation weakens episode retrieval round-trip quality
     - the context builder becomes dependent on synthetic filler material
   - Done signal:
     - context assembly works with moments, episodes, arcs, and pinned items

4. Complete the first usable local CLI and Python API surface.
   - Files to touch:
     - `engram/__init__.py`
     - `engram/core/memory.py`
     - `engram/cli.py`
     - `tests/cli/test_cli.py`
   - Read first:
     - local-app surface spec
     - current implementation from Tasks 2 and 3
   - Minimum in-scope commands and methods:
     - `init`
     - `record`
     - `search`
     - `context`
     - `moment`
     - `episode`
     - `arc`
     - `pin`
     - `status`
     - `rebuild-index`
   - Keep deferred for later unless a new spec says otherwise:
     - `forget`
     - `dump`
     - `load`
     - blob ingestion
   - Stop and re-evaluate if:
     - the CLI starts owning business logic that should live in the core API
   - Done signal:
     - the package and CLI expose a coherent local-user surface

5. Dogfood the app on a real local workflow and tighten the weak spots.
   - Files to touch:
     - `README.md`
     - test fixtures and regression tests
     - implementation notes if rationale changes materially
   - Read first:
     - validation harness results
     - current app specs
   - Outcome:
     - one named workflow uses Engram across at least 3 separate sessions over
       at least 1 day
     - that workflow stores at least 20 moments and exercises `context`,
       `search`, `pin`, and status inspection
     - rough edges found during dogfooding become targeted regressions
     - README is updated to describe the actual local-app milestone rather than
       the full long-range vision as if it already shipped
   - Stop and re-evaluate if:
     - the real workflow keeps depending on deferred features like blobs or
       deletion
   - Done signal:
     - the workflow log produces at least 5 concrete findings
     - the top 3 findings become either regression tests, immediate fixes, or
       explicit defer decisions recorded in docs
     - dogfooding produces clear keep/fix/defer decisions

## 6. Testing Plan

Specs and docs:
- Verify by inspection and link consistency.

Core behavior that must stay real:
- vault initialization and reopen behavior
- durable write and background processing lifecycle
- LanceDB retrieval
- context assembly across moments, episodes, and arcs
- CLI behavior through the public command surface
- reindex and recovery behavior

Acceptable mocks:
- LLM summarizer
- heavy embedding-model inference

Required regression coverage:
- retrieval round-trip from summaries back to constituent moments
- access-score updates only on explicit retrieval
- sparse-corpus context assembly
- failed/lagging background work remaining visible in status output
- rebuild path restoring LanceDB state from SQLite state

Dogfood proof:
- one end-to-end local workflow should be captured as either a documented smoke
  script or a reproducible test fixture
- it should meet the minimum session and usage thresholds from Task 5

Expected commands once implementation exists:
- `./.venv/bin/python -m pytest tests/core`
- `./.venv/bin/python -m pytest tests/store`
- `./.venv/bin/python -m pytest tests/index`
- `./.venv/bin/python -m pytest tests/cli`
- `./.venv/bin/python -m pytest`
- `./.venv/bin/mypy engram`
- `./.venv/bin/ruff check engram`

## 7. Verification and Gates

Do not start broadening the skeleton unless:
- the initial validation slice showed real product signal
- the weak points are known well enough to write stable app-level specs

Do not call the working-app milestone done unless:
- a user can recover from index lag or drift
- the CLI and API still share one core path
- arc tier improves or at least does not degrade context usefulness
- README and specs describe the actual shipped surface

Residual-risk gates to call out at completion:
- whether the app is still too dependent on synthetic fixtures
- whether background work is robust enough for daily local use
- whether deferred features are blocking real workflows or merely desirable

## 8. Independent Review Loop

Before implementation:
- Run an independent plan review against the skeleton findings, product specs,
  this plan, and the touched implementation files.

During implementation:
- Run a review after Task 2 focused on recovery and source-of-truth ownership.
- Run a review after Task 3 focused on whether arcs actually improve context
  rather than just completing the hierarchy on paper.

Before calling the app milestone done:
- Run a final independent review over specs, code, tests, CLI behavior, and
  dogfood results.

## 9. Out of Scope

- Postgres backend
- hosted or shared service deployment
- multi-user coordination
- blob ingestion and blob registry
- hindsight tag refinement
- deletion semantics
- dump/load and backup portability
- web UI
- large-scale performance tuning

## 10. Fresh-Eyes Review

Questions the reviewer should answer:
1. Is this still a sharply scoped local app, or has it silently turned into a
   platform plan?
2. Are any deferred features actually required for a basic working app?
3. If you were asked to implement this after the skeleton phase, could you do
   it without reopening the product definition?
