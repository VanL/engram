# Write, Retrieval, Context, and Deferred Processing

Status: Active

This spec defines Engram's write path, retrieval behavior, context assembly
baseline, and deferred-processing boundary for the local app.

## 1. Purpose and Scope

This spec governs the executable slice that turns stored text into searchable,
coalesced, context-usable memory.

In scope:
- `record()` write behavior
- durable domain projections for deferred work
- embedded-Weft background execution
- indexing and search
- higher-tier coalescing
- importance updates
- direct recall
- context assembly over recent, summarized, and high-value material
- thesis-validation expectations

Out of scope:
- alternate execution substrates
- blob handling
- deletion
- import/export
- hosted or multi-user behavior

## 2. Mental Model

Engram has one synchronous boundary and one deferred boundary:

1. `record()` synchronously writes the moment and records that downstream
   work is required.
2. Weft later executes Engram-owned internal work that indexes the moment and
   attempts coalescing.

Engram does not own a second durable queue. SQLite records domain facts and
selected processing projections; Weft owns queueing and task execution.
Operator tooling may invoke the same domain operations locally for repair or
testing, but that helper is not a second task substrate.

The product thesis under test remains:
- token-budgeted multi-horizon context should surface earlier required
  information more reliably than same-budget last-N replay

## 3. Requirements

### Record Lifecycle

- [MWS-1] `record(text)` must durably store a new moment in the state store
  before it returns.
- [MWS-2] `record(text)` must also durably record that deferred work is
  required before it returns.
- [MWS-3] `record(text)` must not wait for embedding, retrieval-index upsert,
  or higher-tier summary creation before returning.
- [MWS-4] `record(text)` must return the new moment ID.
- [MWS-4.1] `record(text, importance=1)` may set write-time importance. The
  importance value maps to the existing relevance multiplier stored on the
  memory item.
- [MWS-4.2] Write-time importance must be an integer greater than or equal to
  `1`. Omitting importance is equivalent to `importance=1`.

### Deferred Processing Boundary

- [MWS-5] The local app must use embedded Weft for deferred execution.
- [MWS-6] Engram must not introduce a second durable task queue alongside
  Weft.
- [MWS-7] Tests and operator tooling may locally invoke the same domain
  operation used by the Weft task path.
- [MWS-8] A failed deferred-processing attempt must preserve the durable moment
  record and record enough domain state for retry or inspection.
- [MWS-9] The state store must retain enough metadata to inspect whether a
  moment still needs downstream work or has a recorded failure state.
- [MWS-9.1] In the default local sqlite-backed path, Engram-owned Weft broker
  state and runtime artifacts for a vault must live under that vault directory
  so they do not collide with ordinary project-local Weft state.
- [MWS-9.2] Engram's internal deferred work should be expressed as stable
  Engram-owned TaskSpecs rather than an alternate ad hoc execution path.

### Indexing

- [MWS-10] Deferred processing must compute an embedding for a stored item and
  upsert a searchable record into the retrieval index.
- [MWS-11] The local app must support both keyword-oriented search and
  vector-oriented search through the retrieval layer.
- [MWS-11.1] When LanceDB is the retrieval layer, retrieval-side source and
  query embedding should be owned by Lance embedding functions rather than a
  parallel Engram-managed dense retrieval stack.
- [MWS-12] Hybrid search must merge keyword and vector rankings with Reciprocal
  Rank Fusion before score boosting.

### Higher-Tier Coalescing

- [MWS-13] Coalescing must operate over ordered, not shuffled, source items.
- [MWS-14] Coalescing must use semantic-boundary windowing:
  - maintain a running window of candidate items
  - once the minimum window size is reached, compare the next item to the
    running-centroid embedding
  - close the window when similarity drops below the configured threshold
  - force-close the window when the configured maximum size is reached
- [MWS-15] A trailing window smaller than the minimum size may remain
  uncoalesced until more source material arrives.
- [MWS-16] Higher-tier summaries must preserve distinctive terms from their
  constituent items.
- [MWS-17] Summary and keyword extraction for higher-tier items must use an
  LLM-backed structured-output path.

### Retrieval and Scoring

- [MWS-18] Explicit retrieval includes search and direct item recall.
- [MWS-19] Explicit retrieval must increment access for the retrieved items.
- [MWS-19.1] Scoped recall must increment only the returned summary item, not
  the anchor item or intermediate parent-child traversal items.
- [MWS-20] Context assembly must not increment access.
- [MWS-21] Search ranking must boost fused retrieval ranks by
  `access * relevance`.
- [MWS-22] `set_importance(id, importance)` must set update-time importance
  after an item exists. The importance value maps to the existing relevance
  multiplier and must be an integer greater than or equal to `1`.

### Context Assembly

- [MWS-23] The context builder must assemble context from the best available
  mix of:
  - recent moments
  - recent or relevant higher-tier summaries
  - high-importance retained items
- [MWS-24] If a declared time horizon has no usable material, its budget may be
  folded forward rather than filled with synthetic content.
- [MWS-25] Context assembly must respect a total token budget.
- [MWS-26] When a search term is provided, older relevant material may be
  favored, but it must not override the most recent horizons completely.

### Public Surfaces

- [MWS-27] The Python API and CLI must share the same core write, search,
  recall, set-importance, and context-building logic. Any local process helper
  must call the same domain operation used by the Weft task path.
- [MWS-28] The local-user CLI must include:
  - `init`
  - `record`
  - `search`
  - `context`
  - `recall`
  - `set-importance`
  - an optional repair helper such as `vault process`

## 4. Invariants and Constraints

- [MWS-29] The retrieval layer stays owned by LanceDB in this slice.
- [MWS-30] The state store stays owned by SQLite in this slice.
- [MWS-31] The write path must not split into a second path that bypasses
  durable recording of downstream work requirements.
- [MWS-32] The local app should stay narrow enough to keep proving the thesis
  before broadening into unrelated product areas.

## 5. Interfaces and Data Contracts

Minimum Python surface:

```text
Engram.init(path?) -> Engram
Engram.open(path?) -> Engram
Engram(path?, create=False)
Engram.record(text, importance=1) -> int
Engram.search(query, limit=20) -> list[SearchResult]
Engram.recall(id, scope="item" | "episode" | "arc" | int) -> MemoryItem
Engram.set_importance(id, importance) -> MemoryItem
Engram.build_context(...) -> ContextView
Engram.process(max_passes=100) -> ProcessResult  # optional repair helper
```

The exact method signatures may grow optional parameters as long as they do not
break the behavior defined above.

The task inventory, task naming, and Weft integration rules are governed more
specifically by `docs/specs/14-embedded-weft-execution-model.md`.
Foundation ownership, command/client roles, access-score mutation tables, and
CLI JSON output contracts are governed more specifically by
`docs/specs/15-foundation-contracts-and-invariants.md`.

## 6. Failure Modes and Edge Cases

- [MWS-33] A moment may exist but not be searchable yet if deferred processing
  has not run.
- [MWS-34] Deferred-processing failure must be inspectable and retryable.
- [MWS-35] Empty or whitespace-only text input must be rejected.
- [MWS-36] If context assembly cannot fill a later horizon, it should return a
  smaller context rather than fabricate content.

## 7. Verification Expectations

Changes governed by this spec should be proven with:
- real SQLite persistence
- real LanceDB indexing and search
- embedded-Weft submission coverage or equivalent boundary proof
- tests that use the same domain operation as the Weft task path
- retrieval round-trip checks from higher-tier summaries back to constituent
  items
- access-increment tests for explicit retrieval
- non-increment tests for context assembly
- a small labeled fixture corpus comparing Engram against same-budget last-N

The minimum thesis-validation bar is:
- [MWS-37] On a labeled four-scenario fixture corpus, Engram should include all
  required prior items in at least three scenarios.
- [MWS-38] On that same corpus and budget, last-N should miss at least one
  required prior item in at least two scenarios.
- [MWS-39] If those conditions are not met, the slice may be working, but the
  thesis remains unproven.

## Related Plans

- `docs/plans/2026-04-16-initial-skeleton-validation-plan.md`
- `docs/plans/2026-04-16-basic-working-app-plan.md`
- `docs/plans/2026-04-16-weft-background-and-llm-integration-plan.md`
- `docs/plans/2026-04-16-engram-weft-vault-alignment-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
- `docs/plans/2026-04-22-engram-foundation-excellence-plan.md`
- `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`
- `docs/plans/2026-04-23-record-importance-plan.md`
- `docs/plans/2026-04-23-api-vocabulary-process-set-importance-plan.md`
