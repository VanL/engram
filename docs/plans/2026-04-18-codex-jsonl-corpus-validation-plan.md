# 2026-04-18 Codex JSONL Corpus Validation Plan

Status: Proposed

## 1. Goal

Use the real Codex archived thread corpus under `~/.codex/archived_sessions/*.jsonl`
as the first serious dogfooding corpus for Engram. The work has two goals:

1. mechanical validation: prove Engram can ingest real conversational history
   and produce moments, episodes, arcs, and usable status/recovery behavior
2. practical validation: test whether Engram context would materially help a
   fresh-start agent answer better than no memory on selected real checkpoints

The plan should not force heartbeat or a persistent maintenance service. The
current canonical runtime path remains one-shot Weft task submission plus local
repair tooling.

## 2. Source Documents

Source workflow spec:
- `docs/specs/01-development-documentation-operating-model.md` [DOM-5],
  [DOM-8], [DOM-10], [DOM-11]

Source product specs:
- `docs/specs/10-minimum-memory-model.md` [MM-6], [MM-9], [MM-19], [MM-27]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-5],
  [MWS-23], [MWS-25], [MWS-34], [MWS-37], [MWS-38]
- `docs/specs/12-local-app-surface.md` [LAS-8], [LAS-10], [LAS-17], [LAS-19]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5], [CAA-10]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-16],
  [EWM-18], [EWM-19]

Relevant current rationale and historical plans:
- `README.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`
- `docs/plans/2026-04-16-initial-skeleton-validation-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`

External corpus sources to inspect before implementation:
- `~/.codex/archived_sessions/*.jsonl`
- `~/.codex/session_index.jsonl`

Source spec for the Codex corpus ingestion and evaluation harness itself:
- None yet. This plan defines the intended slice. If the workflow becomes
  durable product surface, promote the final contract into numbered specs.

## 3. Context and Key Files

Files to modify:
- `engram/cli.py`
- `engram/core/memory.py`
- one new module under `engram/` or `engram/dogfood/` for Codex corpus parsing
- possibly one narrow internal import helper under `engram/core/` if original
  timestamps must be preserved without widening the public `record()` surface
- `tests/` coverage for parser/import/evaluation helpers
- one new implementation or evaluation doc describing how the harness works

Files to read first:
- `engram/core/memory.py`
- `engram/cli.py`
- `engram/store/sqlite.py`
- `tests/core/test_memory.py`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `~/.codex/session_index.jsonl`
- at least 2 representative files from `~/.codex/archived_sessions/`

Important existing behavior:
- Engram currently stores only memory-item text plus durable memory state. It
  does not persist source-thread metadata, source event ids, or external corpus
  provenance in the core item schema.
- `record()` currently allocates a new timestamped moment and immediately
  submits one Weft-backed task. It does not accept caller-supplied source
  timestamps.
- `build_context()` is the core thesis surface. It is the first thing to test
  in practical validation before allowing richer search/retrieval tool use.
- `work_once()` and `work_until_idle()` are local repair helpers, not a second
  queue or scheduler.
- Archived Codex session JSONL files are event logs, not already-clean turn
  transcripts. They include developer/system context, reasoning records, tool
  calls, tool outputs, token-count events, and assistant/user messages.

Current observed Codex JSONL structure:
- one file begins with `session_meta`
- then alternating `response_item` and `event_msg` records
- the useful user/assistant conversational material lives in
  `response_item.payload.type == "message"`
- the archived files also include developer and system-like injected messages
  that must not become normal user/assistant moments

Required reuse:
- Reuse current Engram write, processing, status, and context surfaces
- Reuse the current embedded-Weft runtime path
- Reuse current summary/coalescing logic instead of adding a corpus-specific
  path
- Reuse current test posture: real SQLite, real LanceDB, real Engram API;
  mock only external model/runtime boundaries when the proof does not depend on
  them

Comprehension questions before coding:
1. Which Codex JSONL record types should become importable conversation content,
   and which must stay excluded from the first slice?
2. Where must source-thread provenance live if Engram's core memory-item schema
   does not include external corpus metadata?
3. Should “next few moments” be used as model input or as judging evidence?
   Why is one of those cleaner than the other?
4. What would break if the importer widened public `record()` instead of
   using a narrow internal import seam?

## 4. Invariants and Constraints

- Keep the first corpus source narrow.
  - Use `~/.codex/archived_sessions/*.jsonl` plus `session_index.jsonl` first.
  - Do not start with `history.jsonl`, live sqlite state, or repaired recovery
    artifacts. Those add ambiguity before the extraction contract is proven.

- Treat mechanical and practical validation as different proofs.
  - Mechanical validation asks whether Engram can ingest and coalesce the corpus
    correctly.
  - Practical validation asks whether the retrieved context would help a
    fresh-start answer.
  - Do not blur those into one score.

- Do not let evaluation contaminate the memory model.
  - Do not add source-thread ids or evaluation labels to core Engram memory
    items just to support the harness.
  - Keep provenance in external manifests or evaluation artifacts unless a
    product need justifies a schema change later.

- Preserve the current public API unless there is a strong reason not to.
  - Prefer a narrow internal import helper if original timestamps or source
    ordering need explicit control.
  - Do not widen `record()` just for corpus import in the first slice.

- Use the “next few moments” as oracle evidence, not as answer input.
  - The actual future turns are good evidence for whether missing memory caused
    clarification, correction, or re-explanation.
  - They are not a clean control input, because they reveal information that was
    not available at answer time.

- Keep practical validation honest about freshness.
  - The evaluation should simulate a fresh-start agent on the current user turn.
  - Baseline gets no Engram memory.
  - Treatment gets Engram memory and the same current turn.
  - Both should be judged against the real future turns and the actual thread
    prefix.

- Start with context-only treatment before richer tool use.
  - First measure whether `build_context()` alone helps.
  - Only after that should the evaluation allow an agent to call `search` and
    direct `moment`/`episode`/`arc` lookups.

- Focus the practical slice on relatively timeless checkpoints.
  - Avoid highly repo-state-dependent or “what files exist right now” turns in
    the first evaluation pass.
  - Prefer conceptual, architectural, workflow, and planning discussions where
    memory continuity matters more than exact current filesystem state.

- No new scheduler assumptions.
  - Do not force heartbeat or a long-lived maintenance service into this slice.
  - The canonical correctness path remains one-shot task submission plus repair.

## 5. Tasks

1. Define the Codex corpus extraction contract.
   - Outcome:
     - one explicit rule set exists for turning archived Codex JSONL into
       importable conversation units
   - Files to touch:
     - new implementation or evaluation note under `docs/implementation/` or
       `docs/`
     - later parser module under `engram/` or `engram/dogfood/`
   - Read first:
     - at least 2 archived session files
     - `~/.codex/session_index.jsonl`
     - `engram/core/memory.py`
   - Required decisions:
     - canonical corpus source is archived session JSONL only for the first pass
     - importable content comes only from `response_item.payload.type == "message"`
     - only `role == "user"` and `role == "assistant"` are eligible for the
       first pass
     - exclude developer/system injections, reasoning records, tool calls, tool
       outputs, token-count events, and other telemetry
     - first moment shape is one paired conversational unit:
       `User: ...` + `Assistant: ...`
     - choose one canonical timestamp for the pair, preferably the assistant
       reply timestamp when present, otherwise the user timestamp
   - Tests to add later:
     - parser tests for ignored record types
     - parser tests for user/assistant extraction
     - parser tests for pairing logic
   - Stop and re-evaluate if:
     - archived JSONL does not support stable user/assistant pairing without
       heavy inference
   - Done signal:
     - one thread can be deterministically parsed into ordered candidate moments
       with no developer/reasoning/tool leakage

2. Implement a read-only parser plus import manifest.
   - Outcome:
     - Engram can ingest parsed Codex conversation units in chronological order
       while preserving external provenance in a sidecar manifest
   - Files to touch:
     - new parser/importer module under `engram/` or `engram/dogfood/`
     - `engram/cli.py`
     - tests for parser/import behavior
   - Read first:
     - `engram/core/memory.py`
     - `engram/cli.py`
     - `tests/core/test_memory.py`
   - Reuse:
     - current Engram init/open/record/work/status flow
   - Required behavior:
     - import threads globally in chronological order across archived sessions
     - write one sidecar manifest mapping:
       - source thread id
       - thread title
       - source file path
       - source pair index
       - source timestamps
       - imported Engram moment id
     - the importer should support a small-sample mode before full corpus import
   - Important design choice:
     - prefer a narrow internal import seam if source timestamps must be
       preserved exactly
     - do not widen the public `record()` signature just for this harness
   - Tests to add:
     - importer creates chronological moment ids or preserves import ordering
     - manifest rows map back to imported items
     - excluded record types do not appear in imported moment text
   - Stop and re-evaluate if:
     - preserving original timestamps requires invasive public API changes
   - Done signal:
     - a small archived-thread sample imports into a vault with a valid manifest

3. Add the mechanical validation harness.
   - Outcome:
     - one command or helper can prove the real corpus ingests and processes as
       designed
   - Files to touch:
     - `engram/cli.py`
     - parser/importer module
     - tests
     - docs for the workflow
   - Read first:
     - `engram/core/memory.py`
     - `engram/store/sqlite.py`
     - `docs/implementation/05-local-vault-recovery.md`
   - Mechanical validation should report:
     - imported moment count
     - episode count
     - arc count
     - items needing processing
     - failed processing count
     - whether status shows rebuild need
   - Required gate:
     - the first successful small-sample import must produce non-zero moments and
       at least some episodes
     - the first larger run should produce arcs too
   - Tests to add:
     - small synthetic archived-session fixture imports and coalesces
   - Stop and re-evaluate if:
     - large imported corpora never produce arcs despite healthy episode counts
     - failures accumulate faster than repair can clear them
   - Done signal:
     - the harness proves moments -> episodes -> arcs on real Codex-derived data

4. Define the practical validation protocol.
   - Outcome:
     - one clear evaluation method exists for asking whether Engram context would
       have improved a fresh-start answer
   - Files to touch:
     - new evaluation protocol doc
     - later evaluation helper module if needed
   - Read first:
     - `README.md`
     - `docs/specs/11-minimum-write-search-context-slice.md`
     - imported manifest format from Task 2
   - Required protocol:
     - choose candidate checkpoints from relatively timeless discussions
     - each checkpoint includes:
       - thread id and title
       - checkpoint source pair index
       - current user message to answer
       - earlier imported memory available at that point
       - next 1-3 real future moments as oracle evidence only
     - baseline answer:
       - current user message only
       - no Engram calls
     - treatment answer phase A:
       - `build_context()` only
       - then answer
     - treatment answer phase B, optional after phase A:
       - `build_context()` plus up to a small bounded number of Engram retrieval
         calls such as `search`, `moment`, `episode`, `arc`
   - Scoring rubric:
     - helpful: likely would have improved correctness, continuity, or reduced
       user restatement
     - neutral: context was not materially useful
     - harmful: context likely would have distracted, overfit, or injected stale
       material
   - Stop and re-evaluate if:
     - checkpoints are too stateful to judge fairly without the original live
       workspace state
   - Done signal:
     - a small set of checkpoints can be scored consistently with the rubric

5. Build a lightweight evaluation prompt pack before creating a skill.
   - Outcome:
     - the evaluation loop is reproducible without prematurely promoting it into
       a general-purpose Codex skill
   - Files to touch:
     - new repo-local prompt or protocol doc
   - Read first:
     - the extracted checkpoint format
     - the practical validation rubric
   - Required content:
     - how the evaluator should call Engram
     - what “fresh start” means
     - what information is allowed in baseline vs treatment
     - how to score usefulness against the future oracle
   - Important constraint:
     - do not create a full reusable Codex skill yet unless the prompt stabilizes
       across several checkpoints
   - Counterargument to document:
     - a skill is attractive, but it is probably premature before the evaluation
       workflow itself is stable
   - Done signal:
     - one consistent prompt/protocol can be reused across a small checkpoint set

6. Run the first practical evaluation pass and log results.
   - Outcome:
     - the repo has a first real answer to “is Engram useful on this corpus?”
   - Files to touch:
     - evaluation helper module or notebook-style script if needed
     - one results artifact directory
     - docs summarizing findings
   - Read first:
     - the practical validation protocol
     - the imported manifest
   - Required output:
     - per-checkpoint baseline answer
     - per-checkpoint treatment answer
     - score
     - short explanation tied to the future oracle
     - any recurring failure mode such as stale context, irrelevant retrieval,
       or useful missing facts
   - Stop and re-evaluate if:
     - treatment is often worse because the context surface is too broad or too
       noisy
     - the chosen checkpoints are not fair tests of memory continuity
   - Done signal:
     - the first evaluation pass yields a clear keep/fix/defer conclusion rather
       than vague impressions

7. Fold dogfooding findings back into the roadmap.
   - Outcome:
     - the dogfooding results directly shape the next implementation task
   - Files to touch:
     - `docs/implementation/` note for findings
     - `docs/lessons.md` if repeated patterns appear
     - if needed, a follow-up plan for the most important fix
   - Required outcomes:
     - if mechanical validation fails, prioritize ingestion/runtime fixes
     - if practical validation is weak, prioritize context quality or retrieval
       tuning
     - only if repeated manual repair becomes a real operational pain should the
       team revisit a long-lived maintenance service or heartbeat-backed loop
   - Done signal:
     - next work is chosen based on corpus evidence, not architectural taste

## 6. Testing Plan

Testing should stay split by proof type.

Mechanical proof:
- use real archived-session-derived fixtures for parser/import tests
- use real SQLite and real LanceDB for importer/mechanical integration tests
- keep embedded-Weft submission real where the proof depends on it
- mock only the external model boundaries when deterministic test control is
  needed

Practical proof:
- do not call the future oracle “ground truth” in a strict sense; it is judging
  evidence, not an absolute label
- log enough per-checkpoint detail that a human can audit the score
- keep baseline and treatment prompts identical except for Engram access

Suggested test files:
- `tests/dogfood/test_codex_jsonl_parser.py`
- `tests/dogfood/test_codex_import.py`
- `tests/dogfood/test_practical_eval_protocol.py`
- plus targeted updates to existing core/cli tests only where the new helper
  surface touches them

Suggested runtime harness commands once implemented:
- `./.venv/bin/python -m pytest tests/dogfood/test_codex_jsonl_parser.py -q`
- `./.venv/bin/python -m pytest tests/dogfood/test_codex_import.py -q`
- `./.venv/bin/python -m pytest tests/dogfood/test_practical_eval_protocol.py -q`
- `./.venv/bin/python -m pytest`
- `./.venv/bin/mypy engram`
- `./.venv/bin/ruff check engram tests docs README.md`

## 7. Verification and Gates

Mechanical gates:
- importer can read archived-session JSONL without developer/reasoning/tool
  leakage
- imported vault shows moments, episodes, and arcs on a sufficiently large real
  sample
- status and repair surfaces remain usable on the imported corpus

Practical gates:
- at least a small curated set of checkpoints is scored with the baseline /
  treatment / oracle protocol
- the evaluation logs are inspectable by a human
- the first pass yields at least one clear fix direction:
  - context too noisy
  - context clearly helpful
  - retrieval drill-down needed
  - checkpoint selection too stateful

Decision gates after the first pass:
- If mechanical validation fails, do not proceed to larger-scale practical
  evaluation.
- If context-only treatment already shows useful signal, keep the first thesis
  surface narrow before adding tool-rich agent evaluation.
- If practical validation is inconclusive because the sampled threads are too
  stateful, tighten the checkpoint selection rules before changing Engram.
- If repeated manual repair pain appears during import runs, create a separate
  plan for an optional maintenance loop; do not smuggle it into this one.

## 8. Non-Goals for This Plan

- importing live Codex sqlite databases
- adding public scheduler or heartbeat dependency to Engram
- turning the evaluation harness into polished end-user product surface
- broadening Engram's core memory schema for external provenance
- declaring the practical validation solved after one small, noisy pass
