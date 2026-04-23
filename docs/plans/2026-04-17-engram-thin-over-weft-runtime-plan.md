# 2026-04-17 Engram Thin-Over-Weft Runtime Plan

Status: Proposed

## 1. Goal

Realign Engram so embedded Weft is the execution substrate for deferred and
background work, while Engram remains the owner of memory state, hierarchy,
retrieval semantics, and context assembly. The main shift is from a
single bundled "process item" worker path toward a stable internal TaskSpec
inventory plus tier-generic coalescing.

## 2. Source Documents

Source workflow spec:
- `docs/specs/01-development-documentation-operating-model.md` [DOM-5],
  [DOM-8], [DOM-10], [DOM-11]

Source product specs:
- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-19], [MM-25]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-5],
  [MWS-9.2], [MWS-10], [MWS-27]
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-17], [LAS-19], [LAS-20]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5], [CAA-10],
  [CAA-11]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-6],
  [EWM-9], [EWM-13], [EWM-16], [EWM-19]

Historical plans and rationale:
- `docs/plans/2026-04-16-weft-background-and-llm-integration-plan.md`
- `docs/plans/2026-04-16-engram-weft-vault-alignment-plan.md`
- `docs/plans/2026-04-16-basic-working-app-plan.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`

Cross-repo execution substrate references:
- `../weft/docs/specifications/02-TaskSpec.md`
- `../weft/docs/specifications/05-Message_Flow_and_State.md`
- `../weft/docs/specifications/10-CLI_Interface.md`

## 3. Context and Key Files

Files to modify:
- `engram/background.py`
- `engram/core/memory.py`
- `engram/core/coalesce.py`
- `engram/store/sqlite.py`
- `engram/cli.py`
- `engram/_models.py`
- `engram/_constants.py`
- new internal-task code or bundle path if needed under `engram/`
- `tests/core/`
- `tests/cli/`
- `tests/store/`
- implementation notes that explain the new execution boundary

Files to read first:
- `engram/background.py`
- `engram/core/memory.py`
- `engram/core/coalesce.py`
- `engram/store/sqlite.py`
- `engram/index/lance.py`
- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/12-local-app-surface.md`
- `docs/specs/13-context-assembly-and-arcs.md`
- `docs/specs/14-embedded-weft-execution-model.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`

Current load-bearing ownership:
- `engram/core/memory.py` currently owns public API orchestration, direct item
  indexing, and bundled post-index coalescing.
- `engram/background.py` currently hand-builds a Weft TaskSpec and routes it to
  a single worker entry point.
- `engram/store/sqlite.py` currently stores both durable memory state and
  queue-shaped processing projections.
- `engram/core/coalesce.py` already contains generic semantic-window logic, but
  orchestration above it still treats episodes and arcs as separate flows.

Required reading comprehension questions before code:
1. Which facts must remain recoverable from SQLite alone if all Weft task logs
   disappeared?
2. Which current status fields are domain facts versus queue-shaped execution
   projections?
3. What would break if `coalesce-tier` stayed special-cased for episodes and
   arcs instead of becoming a true tier-generic operation?
4. Where would drift appear first if internal TaskSpecs were materialized per
   vault instead of remaining code-owned?

## 4. Invariants and Constraints

- Weft owns execution and queueing.
  - Do not introduce a second durable queue, scheduler, or shadow workflow
    router in Engram.
  - Do not let Engram depend on replaying Weft queue history to recover memory
    truth.

- Engram owns memory truth.
  - SQLite remains authoritative for memory items, hierarchy, and score state.
  - LanceDB remains the rebuildable retrieval projection.
  - Named endpoints and Weft task history remain operator surfaces, not durable
    domain state.

- Extend the existing path before inventing a new one.
  - Reuse the current embedded Weft bootstrap and vault-local runtime.
  - Reuse the current domain logic where possible instead of rebuilding the
    memory pipeline around task wrappers.

- Keep the tier model generic above tier 0.
  - Moments stay special.
  - Higher tiers share the same durable summary-item schema.
  - Tier-specific helpers such as `arc` are named public surfaces, but task
    and storage logic should not fork by named tier when a generic path works.

- Do not shell out to `weft run` from Engram.
  - The integration boundary is Weft's Python API and TaskSpec model.
  - CLI behavior is user UX, not the embedding interface.

- Preserve the current public local-user surface unless a spec explicitly says
  otherwise.
  - `record`, `search`, `context`, `moment`, `episode`, `arc`, `pin`,
    `status`, and `rebuild-index` should stay coherent while internals change.

- Anti-mocking posture:
  - Real SQLite, real LanceDB, and real embedded-Weft init should stay real in
    integration tests.
  - Mock only external model calls and truly external Weft boundaries when the
    proof does not depend on them.

- Rollout constraints:
  - Keep schema and on-disk changes additive where practical.
  - Status may change from queue-shaped wording to domain-projection wording,
    but the app must stay inspectable throughout.
  - If internal TaskSpec materialization proves too drift-prone, stop and keep
    the inventory code-owned rather than persisting mutable copies into vaults.

## 5. Tasks

1. Replace the current ad hoc background-task shape with a stable internal
   TaskSpec inventory.
   - Files to touch:
     - `engram/background.py`
     - new internal-task module or bundle path under `engram/`
     - `tests/` background-focused coverage
   - Read first:
     - `docs/specs/14-embedded-weft-execution-model.md`
     - `../weft/docs/specifications/02-TaskSpec.md`
     - `engram/background.py`
   - Reuse:
     - the existing embedded Weft runtime root/config helper
     - the existing vault-local isolation model
   - Outcome:
     - Engram-owned internal TaskSpecs exist with stable names
     - submission no longer depends on one hand-built inline spec per task
   - Stop and re-evaluate if:
     - the design starts depending on per-vault spec drift management without a
       clear reconciliation path
   - Done signal:
     - internal task submission resolves through one stable inventory path

2. Split the bundled processing path into reusable domain operations.
   - Files to touch:
     - `engram/core/memory.py`
     - `engram/core/coalesce.py`
     - possibly one new core operations module if needed
     - `tests/core/test_memory.py`
   - Read first:
     - `engram/core/memory.py`
     - `docs/specs/11-minimum-write-search-context-slice.md`
     - `docs/specs/14-embedded-weft-execution-model.md`
   - Reuse:
     - current indexing path
     - current summary-window selection logic
   - Outcome:
     - indexing, coalescing, rebuild, and repair are explicit domain
       operations that both Weft tasks and local repair helpers can call
   - Stop and re-evaluate if:
     - a second code path appears for local repair versus Weft execution
   - Done signal:
     - the same core operation is provably reusable in both contexts

3. Generalize coalescing from named tiers to declared tiers.
   - Files to touch:
     - `engram/core/coalesce.py`
     - `engram/core/memory.py`
     - `engram/store/sqlite.py`
     - `tests/core/test_coalesce.py`
     - `tests/core/test_context.py`
   - Read first:
     - `docs/specs/10-minimum-memory-model.md`
     - `docs/specs/13-context-assembly-and-arcs.md`
     - `docs/implementation/06-arc-context-assembly.md`
   - Reuse:
     - the current shared semantic-boundary window logic
     - the current shared summary-item storage path
   - Outcome:
     - `coalesce-tier(source_tier, target_tier)` becomes the canonical
       higher-tier creation shape
     - `episode` and `arc` remain named concepts without forcing separate core
       logic families
   - Stop and re-evaluate if:
     - a proposed abstraction weakens retrieval round-trip quality or requires
       tier-specific storage branching
   - Done signal:
     - adding another declared tier would not require a new durable schema

4. Simplify queue-shaped processing projections into domain-owned inspection
   state.
   - Files to touch:
     - `engram/store/sqlite.py`
     - `engram/_models.py`
     - `engram/core/memory.py`
     - `engram/cli.py`
     - `tests/store/test_sqlite.py`
     - `tests/cli/test_cli.py`
   - Read first:
     - `docs/specs/12-local-app-surface.md`
     - `docs/specs/14-embedded-weft-execution-model.md`
     - `engram/store/sqlite.py`
   - Outcome:
     - status surfaces report domain lag, failure, and correlation cleanly
     - Engram no longer looks like it owns its own task lifecycle model
   - Stop and re-evaluate if:
     - removing a status field would hide a real recovery action the user needs
   - Done signal:
     - status stays useful without mirroring Weft internals wholesale

5. Decide whether any persistent named tasks are worth adding in the local app.
   - Files to touch:
     - `engram/background.py`
     - `engram/cli.py`
     - `tests/cli/test_cli.py`
     - relevant docs if the answer is yes
   - Read first:
     - `docs/specs/14-embedded-weft-execution-model.md`
     - `../weft/docs/specifications/05-Message_Flow_and_State.md`
   - Outcome:
     - either persistent named coalescer or maintenance services are added
       with clear value, or the plan records why one-shot tasks remain enough
   - Stop and re-evaluate if:
     - the design starts treating endpoints as a service framework or durable
       domain registry
   - Done signal:
     - the choice is explicit and documented rather than implicit drift

6. Dogfood the embedded-runtime model and tighten rough edges.
   - Files to touch:
     - `README.md`
     - implementation notes for the new boundary
     - regression tests driven by findings
   - Read first:
     - the updated specs
     - current implementation notes
   - Outcome:
     - at least one real workflow uses Engram with the embedded Weft runtime
       without manual queue surgery
     - the main friction points become fixes, tests, or explicit defers
   - Stop and re-evaluate if:
     - dogfooding repeatedly depends on features outside the current scope
   - Done signal:
     - real usage validates that Engram is thinner over Weft without becoming a
       thin wrapper with no domain shape

## 6. Testing Plan

Docs and specs:
- Verify by inspection, stable reference-code continuity, and backlink
  consistency.

Runtime behavior that must stay real:
- embedded-Weft vault initialization
- task submission against the vault-local runtime
- SQLite durability and recovery behavior
- LanceDB indexing and search
- coalescing and context assembly through the public API
- CLI behavior through the public command surface

Targeted tests to add or update:
- background submission tests for stable internal TaskSpec names
- core tests proving the same domain operation runs through Weft and local
  repair helpers
- coalescing tests for tier-generic source-tier to target-tier behavior
- status tests for domain lag and failure projection
- recovery tests proving SQLite-based restoration does not require Weft queue
  replay

Commands to run:
- `./.venv/bin/python -m pytest`
- `./.venv/bin/mypy engram`
- `./.venv/bin/ruff check engram tests docs`

## 7. Verification and Gates

Per-task verification:
- each task lands with the smallest targeted tests that prove the new boundary
  without weakening current public behavior

Final gates before claiming completion:
- embedded Weft remains isolated per vault
- no second durable task substrate exists in Engram
- SQLite remains authoritative and LanceDB rebuildable
- at least one higher-tier path is provably generic above tier 0
- status remains actionable for recovery
- full `pytest`, `mypy`, and `ruff` gates pass

Rollback and replan gates:
- if the internal TaskSpec inventory cannot stay stable without per-vault drift
  problems, keep specs code-owned and do not persist mutable copies
- if queue-shaped status proves necessary for recovery, name the exact missing
  recovery action before widening Engram's projected state again
- if tier-generic coalescing weakens retrieval round-trip quality, stop and
  tighten the generic policy before broadening tiers further

## 8. Independent Review Loop

Plan review should happen before code work starts.

Recommended review stance:
> Read the plan at
> `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`. Carefully
> examine the plan and the associated code. Look for errors, bad ideas, and
> latent ambiguities. Do not implement anything. Answer one question: could you
> implement this confidently and correctly if asked?

Reviewer inputs:
- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/12-local-app-surface.md`
- `docs/specs/13-context-assembly-and-arcs.md`
- `docs/specs/14-embedded-weft-execution-model.md`
- `engram/background.py`
- `engram/core/memory.py`
- `engram/store/sqlite.py`
- `engram/core/coalesce.py`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`

Feedback handling:
- update the plan if the reviewer exposes a real ambiguity or bad boundary
- if retaining the current path, answer the objection explicitly in the plan or
  implementation notes before code starts
