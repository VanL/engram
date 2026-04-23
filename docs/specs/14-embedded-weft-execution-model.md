# Embedded Weft Execution Model

Status: Active

This spec defines the execution boundary between Engram and its embedded Weft
runtime.

## 1. Purpose and Scope

This spec governs:
- embedded Weft as part of a vault
- internal TaskSpec ownership and naming
- one-shot versus persistent task classes
- Weft-task correlation versus Engram-owned domain state
- local repair-tooling boundaries

It does not govern:
- Weft internals outside Engram's integration boundary
- hosted scheduling or multi-user coordination
- alternate execution substrates
- the memory schema itself

## 2. Mental Model

Engram is a domain system over:
- authoritative SQLite memory state
- rebuildable LanceDB retrieval
- embedded Weft execution

Weft owns durable queueing and task execution. Engram owns memory truth.

Those truths are different:
- Weft is authoritative for task lifecycle state
- Engram is authoritative for memory content, hierarchy, and retrieval-related
  domain facts

Engram may project selected task outcomes or failure correlations into SQLite
for inspection and recovery. It must not require Weft queue history to recover
the memory graph.

## 3. Requirements

### Ownership Boundary

- [EWM-1] Embedded Weft must own deferred task queueing and execution for
  Engram's internal background work.
- [EWM-2] Engram must not introduce a second durable task substrate.
- [EWM-3] Engram must not encode durable memory truth in Weft queue state,
  task history, or endpoint records.
- [EWM-4] SQLite remains authoritative for memory state even when Weft task
  history is missing, stale, or pruned.
- [EWM-5] Weft correlation data may be stored for inspection, but it must not
  be required to reconstruct the memory graph or retrieval projection.

### Internal Task Inventory

- [EWM-6] Engram's deferred operations must be expressed as Engram-owned
  internal TaskSpecs.
- [EWM-7] Internal TaskSpecs must use stable names across invocations while
  their contract remains unchanged.
- [EWM-8] The internal task inventory must distinguish at least:
  - per-item indexing work
  - tier-coalescing work
  - repair or rebuild work
  - later maintenance work when introduced
- [EWM-9] Coalescing tasks should be tier-generic `source_tier -> target_tier`
  operations rather than separate bespoke task families for each named tier.

### Task Classes and Naming

- [EWM-10] Finite deferred operations should use one-shot tasks by default.
- [EWM-11] Persistent named tasks may be used for vault-local coalescers,
  maintenance services, or similar long-lived execution when they materially
  improve operability.
- [EWM-12] Named tasks and endpoint claims are discovery and operator surfaces
  only; they must not become durable Engram domain state.

### Submission and Integration Boundary

- [EWM-13] Engram should submit internal work through Weft's Python APIs, not
  by shelling out to `weft run`.
- [EWM-14] Task payloads should carry Engram domain identifiers and task input,
  not mirror the full memory state.
- [EWM-15] Engram should prefer a code-owned or otherwise versioned internal
  TaskSpec library. If TaskSpecs are materialized into vault state, init and
  open behavior must reconcile drift explicitly.
- [EWM-16] Local repair helpers must call the same domain operation that the
  corresponding internal TaskSpec runs.

### Failure and Recovery

- [EWM-17] A task failure must preserve Engram's durable memory state.
- [EWM-18] Engram must expose enough inspection data to find the affected item,
  the recorded error, and the last known Weft correlation when available.
- [EWM-19] Recovery may resubmit internal tasks or invoke the same domain
  operation locally, but it must not depend on replaying Weft queue history.

## 4. Invariants and Constraints

- [EWM-20] Weft is the execution substrate, not the memory source of truth.
- [EWM-21] Engram must not build a shadow workflow router over named endpoints.
- [EWM-22] The same domain operation should stay reusable across Weft-executed
  and local-repair contexts.
- [EWM-23] The embedded Weft runtime must remain isolated to the vault in the
  default sqlite-backed local path.

## 5. Interfaces and Data Contracts

This spec does not require one specific internal task inventory shape, but the
minimum contract categories are:

```text
index-item(item_id)
coalesce-tier(source_tier, target_tier)
rebuild-index()
repair-item(item_id)
```

These may be implemented as one-shot TaskSpecs, persistent named tasks, or a
mix, as long as the ownership rules above remain true.

## 6. Failure Modes and Edge Cases

- [EWM-24] If embedded Weft is unavailable during init, the vault must fail
  initialization clearly rather than silently creating a half-configured app.
- [EWM-25] If a task fails after the durable write succeeds, the moment must
  remain valid and inspectable.
- [EWM-26] If named persistent tasks are not running, Engram must still have a
  recoverable path for required work.

## 7. Verification Expectations

Changes governed by this spec should be proven with:
- embedded-Weft initialization coverage
- proof that internal task submission resolves inside the embedded vault
  context
- tests showing the same domain operation can run through Weft and through the
  local repair path
- tests showing domain recovery does not require Weft queue-history replay
- stable-name coverage for Engram-owned internal TaskSpecs when the contract is
  unchanged

## Related Plans

- `docs/plans/2026-04-16-weft-background-and-llm-integration-plan.md`
- `docs/plans/2026-04-16-engram-weft-vault-alignment-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
