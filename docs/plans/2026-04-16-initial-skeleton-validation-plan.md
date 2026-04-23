# 2026-04-16 Initial Skeleton Validation Plan

Status: Proposed

## 1. Goal

Build the smallest end-to-end Engram slice that can validate the core thesis:
budgeted multi-horizon context is more useful to an agent than naive
conversation replay or flat search alone.

This slice should be real enough to test the product idea, not a fake demo. It
should support local vault creation, recording text, indexing it, coalescing
it into episodes, searching it, and assembling context from it. It should stay
small enough that failure teaches us something product-level, not just that we
overbuilt too early.

Validation target for this plan:
- Build a small labeled fixture corpus of agent-work scenarios.
- For each scenario, label the prior memory items that are required for the
  later task to be done correctly.
- Compare Engram context output against a same-budget last-N baseline.
- Treat the thesis as provisionally validated only if:
  - Engram includes all labeled required items in at least 3 of 4 scenarios
  - last-N misses at least one required item in at least 2 of those scenarios
  - Engram stays within the same memory-token budget used for the baseline
- Treat any weaker result as "working plumbing, thesis still unproven."

## 2. Source Documents

Source workflow spec:
- `docs/specs/01-development-documentation-operating-model.md` [DOM-5],
  [DOM-8], [DOM-10], [DOM-11]

Source product spec:
- None. The product behavior is still described in `README.md` and
  `engram/_constants.py`. Task 1 in this plan writes the missing minimum specs
  before implementation starts.

Supporting product context:
- `README.md`
- `engram/_constants.py`
- `docs/lessons.md`
- `docs/implementation/02-repository-map.md`

## 3. Context and Key Files

Read first:
- `README.md`
  - This is the current product thesis. The important sections are:
    "The Approach", "Context Assembly", "Retrieval", "Access Scoring and
    Decay", "Architecture", "Async by Default", and "Key Design Decisions".
- `engram/_constants.py`
  - This already fixes many defaults: tiers, budget splits, decay defaults,
    storage names, and the intended embedding model.
- `docs/lessons.md`
  - The "Design Phase (2026-04-16)" lessons already capture load-bearing
    choices about context assembly, coalescing, scoring, storage split, and
    async writes.
- `pyproject.toml`
  - This declares the intended dependency surface and a CLI entry point that is
    not yet implemented.

Current code reality:
- `engram/__init__.py` exports only constants.
- `engram/cli.py` does not exist yet even though `pyproject.toml` declares it.
- No tests exist yet.
- The only real source-of-truth spec today is the documentation operating
  model, not the Engram product.

Execution-context decision for this plan:
- The minimum slice does not ship an always-on worker.
- It does ship a durable pending-work state in SQLite plus one canonical process
  path that can be invoked from tests and the CLI via `engram work once`.
- This is intentional. It validates the async boundary, retry/recovery model,
  and source-of-truth split without forcing early daemon or supervisor design.
- The follow-on app plan may wrap this same process path in a continuous worker,
  but it should not replace the underlying processing model.

Expected new files and directories for this slice:
- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `engram/core/memory.py`
- `engram/core/coalesce.py`
- `engram/core/context.py`
- `engram/core/scoring.py`
- `engram/store/base.py`
- `engram/store/sqlite.py`
- `engram/index/lance.py`
- `engram/cli.py`
- `tests/core/`
- `tests/store/`
- `tests/index/`
- `tests/cli/`

Required reading comprehension questions before code:
1. Which operations must complete against SQLite before `record()` returns?
2. Which operations are allowed to lag behind in background work?
3. Which parts of the thesis actually need proof in this slice, and which
   features are only supporting ideas that can wait?

## 4. Invariants and Constraints

- Respect the two-layer split from the first real slice.
  - SQLite is the source of truth for state, parent-child links, and processing
    state.
  - LanceDB is the retrieval index.
  - Do not move access scores, decay, or parent traversal into LanceDB.
  - Do not fake search by replacing LanceDB with SQLite-only text search.

- Keep the public write path non-blocking at the product boundary.
  - `record()` should return after the moment is durable in SQLite and marked
    pending for downstream work.
  - Embedding, LanceDB upsert, and coalescing may complete later.
  - Background submission failures should not lose the recorded moment if the
    pending state is already durable.
  - In this slice, "background" means deferred work recorded durably and processed
    through the same processing path from tests or `engram work once`.

- Moments are immutable and never deleted by coalescing.
  - Episode creation is additive.
  - The shared ID space remains immutable after write.

- Validate the thesis with a real vertical slice.
  - The slice is not done if it only has unit tests for helpers.
  - The slice must include a small evaluation harness or fixture corpus that
    compares Engram context output against a naive baseline.

- Keep the slice intentionally narrow.
  - SQLite only. No Postgres implementation in this slice.
  - Moment and episode tiers only. No arc tier yet.
  - Text moments only. No blobs.
  - No tag hindsight refinement.
  - No dump/load.
  - No deletion semantics yet.

- Keep one core path.
  - The Python API and CLI should call the same core logic.
  - Do not create one sync code path for tests and a different async code path
    for production. If test helpers are needed, they should process the same
    pending work queue or state.

- Retrieval semantics must stay sharp.
  - Explicit retrieval increments access.
  - Context inclusion does not increment access.
  - Summary quality must be checked with retrieval round-trip assertions on a
    fixture corpus.

- Anti-mocking posture:
  - Use real SQLite and real LanceDB in integration tests.
  - Mock only external, slow, or nondeterministic boundaries such as the LLM
    summarizer and the heavy embedding model.

Rollback and sequencing constraints:
- Keep schema changes additive while the slice is unstable.
- Avoid any destructive migration or irreversible ID/storage-format change.
- If the background path proves too loose, keep the public API stable and
  simplify the worker orchestration before broadening scope.

Observable success for this slice:
- A developer can initialize a vault, record several items, process background
  work, search for them, and build a context view.
- On a small curated corpus, the Engram context view surfaces earlier relevant
  decisions more reliably than a last-N baseline under the fixed acceptance bar
  above.

## 5. Tasks

1. Write the minimum product specs needed to start coding.
   - Files to touch:
     - `docs/specs/10-minimum-memory-model.md`
     - `docs/specs/11-minimum-write-search-context-slice.md`
     - `docs/specs/00-specs-index.md`
   - Read first:
     - `README.md`
     - `engram/_constants.py`
     - `docs/lessons.md`
   - Capture:
     - vault model
     - moment and episode contracts
     - write lifecycle
     - the exact deferred-processing model for the skeleton
     - retrieval semantics
     - context assembly rules for the minimum slice
     - fixture-corpus acceptance criteria for thesis validation
     - explicit out-of-scope items
   - Stop and re-evaluate if:
     - the spec starts describing arc tiers, blobs, or Postgres in normative
       detail
     - deletion semantics become necessary to explain the slice
   - Done signal:
     - the product no longer depends on `README.md` alone as the behavior spec

2. Create the minimum package skeleton and persistent state contract.
   - Files to touch:
     - `engram/__init__.py`
     - `engram/core/memory.py`
     - `engram/store/base.py`
     - `engram/store/sqlite.py`
     - `engram/index/lance.py`
   - Read first:
     - new minimum specs from Task 1
     - `engram/_constants.py`
   - Reuse:
     - the directory shape already described in `AGENTS.md`
   - Outcome:
     - a real `Engram` entry point exists
     - vault init/open works
     - SQLite schema stores moments, relevance/access data, and pending work
       state
   - Stop and re-evaluate if:
     - a second storage path appears
     - Postgres support starts driving interface design
   - Done signal:
     - tests can create a temp vault and persist a moment record

3. Implement the minimum write, index, and coalesce path.
   - Files to touch:
     - `engram/core/memory.py`
     - `engram/core/coalesce.py`
     - `engram/store/sqlite.py`
     - `engram/index/lance.py`
     - `tests/core/test_memory.py`
     - `tests/store/test_sqlite.py`
   - Read first:
     - minimum slice spec sections for write lifecycle and coalescing
   - Outcome:
     - `record()` writes a durable moment row and pending processing state
     - one canonical process function performs embedding, LanceDB upsert, and
       episode coalescing for both tests and `engram work once`
     - coalescing uses semantic-boundary logic with the existing constants
     - the minimum coalescing algorithm is explicit:
       - ordered moments accumulate in a running window
       - once the minimum window is reached, compare the next moment embedding
         to the running-centroid embedding
       - if similarity drops below the configured threshold, close the episode
       - if the maximum window size is reached, force-close the episode
       - summarize the closed window with preserved distinctive terms
   - Stop and re-evaluate if:
     - the worker requires a second write API
     - the implementation needs arc-tier logic to feel coherent
   - Done signal:
     - integration tests show a recorded moment becomes searchable and can
       participate in an episode after processing pending work

4. Implement retrieval, pinning, direct lookup, and minimum context assembly.
   - Files to touch:
     - `engram/core/context.py`
     - `engram/core/scoring.py`
     - `engram/core/memory.py`
     - `tests/core/test_context.py`
     - `tests/index/test_lance.py`
   - Read first:
     - minimum slice spec sections for retrieval and context assembly
   - Outcome:
     - hybrid search works through LanceDB
     - access-weighted ranking uses `access * relevance`
     - explicit lookup and search increment access
     - built context uses recent moments, recent episodes, and pinned/high-value
       items without incrementing access
   - Stop and re-evaluate if:
     - context assembly starts depending on arc-tier behavior
     - access updates force point writes back into LanceDB
   - Done signal:
     - targeted tests prove the scoring rule and context inclusion rule

5. Add a thesis-validation harness and thin CLI for manual dogfooding.
   - Files to touch:
     - `engram/cli.py`
     - `tests/cli/test_cli.py`
     - `tests/fixtures/`
     - `README.md`
   - Read first:
     - `README.md`
     - minimum slice specs
   - Minimum commands:
     - `engram init`
     - `engram record`
     - `engram search`
     - `engram context`
     - `engram moment`
     - `engram episode`
     - `engram pin`
     - `engram work once`
   - Validation harness outcome:
     - one command or documented test path compares Engram output against
       last-N replay for a curated corpus with labeled required-item IDs
     - the harness records, per scenario:
       - token budget used
       - required prior item IDs
       - which required items appear in Engram context
       - which required items appear in last-N context
     - the slice only passes if it meets the validation target stated in
       Section 1
   - Stop and re-evaluate if:
     - the harness cannot state what counts as a better context result
     - manual CLI use diverges from the Python API path
   - Done signal:
     - a new developer can run the slice locally and see the thesis under test

## 6. Testing Plan

Docs and spec work:
- Verify by inspection and link consistency.

Unit proofs:
- Tier naming, budget validation, score calculation, and small coalescing
  decisions can use plain unit tests.

Integration proofs that must stay real:
- SQLite schema and persistence
- LanceDB indexing and retrieval
- the write -> pending -> process -> searchable lifecycle
- context assembly behavior against stored data

Acceptable mocks:
- LLM summarizer
- heavy embedding-model inference

Required fixture proof:
- Use a small, curated corpus with known earlier decisions and later tasks.
- Assert that:
  - search can still find original moments using terms preserved in episode
    summaries
  - the assembled context contains the required prior item IDs for each
    scenario
  - Engram satisfies the fixed acceptance bar from Section 1
  - last-N is measured with the same token budget rather than an arbitrary
    larger window

Expected commands once implementation exists:
- `./.venv/bin/python -m pytest tests/core/test_memory.py`
- `./.venv/bin/python -m pytest tests/core/test_context.py`
- `./.venv/bin/python -m pytest tests/index/test_lance.py`
- `./.venv/bin/python -m pytest tests/cli/test_cli.py`
- `./.venv/bin/python -m pytest`
- `./.venv/bin/mypy engram`
- `./.venv/bin/ruff check engram`

## 7. Verification and Gates

Implementation is not ready to start until:
- Task 1 lands the minimum product specs
- the validation harness has the fixed acceptance rule from Section 1

Implementation is not ready to broaden after the first slice unless:
- the fixture corpus shows real thesis signal
- the CLI and Python API exercise the same core path
- retrieval round-trip checks pass for coalesced summaries

Residual-risk gates to call out at completion:
- whether the fixture corpus is still too synthetic
- whether the deferred-processing model is sufficient, or whether the next
  milestone needs a continuous worker
- whether the minimum slice proves "better context" or only "working plumbing"

## 8. Independent Review Loop

Before implementation:
- Run an independent plan review with the governing workflow spec, this plan,
  `README.md`, and `engram/_constants.py`.

During implementation:
- After Task 3, run a fresh review focused on whether the write/index/coalesce
  path stayed on one canonical path and whether the validation harness still
  proves the thesis rather than the plumbing.

Before calling the slice done:
- Run a final independent review over the touched specs, code, tests, and the
  validation results.

## 9. Out of Scope

- Postgres backend
- arc tier
- blobs and blob registry
- hindsight tag refinement and clustering
- dump/load
- deletion semantics
- hosted service, daemon management, or web UI
- scale benchmarks and tuning
- backward compatibility guarantees for external users

## 10. Fresh-Eyes Review

Questions the reviewer should answer:
1. Could you implement this slice confidently without rediscovering the
   intended boundaries?
2. Does the slice prove the thesis, or only that a storage/index pipeline can
   be assembled?
3. Are any promised CLI or API surfaces still too broad for a minimum slice?
