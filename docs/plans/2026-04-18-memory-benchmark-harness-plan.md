# 2026-04-18 Memory Benchmark Harness Plan

Status: Proposed

## 1. Goal

Build a memory-system benchmark (working name: **memeval**) that measures
whether a memory system materially improves multi-turn agent conversation
quality, using real historical conversations as ground truth and hindsight-
briefed simulated users as the test driver. Engram is the first system under
test, but the harness is designed from day one to evaluate any system that
implements a simple shared protocol (NoMemory, LastN, FlatRAG, Engram, and
future additions).

The benchmark is the durable artifact. Engram either wins it or it doesn't;
either way the methodology outlives this specific system. The v0 scope is a
tight pilot that validates the methodology on engram-vs-baselines; v1+ expands
to more systems, more checkpoints, and publishable rigor.

This plan supersedes the eval-methodology portion of
`docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`. The corpus
ingestion infrastructure from that plan remains relevant and is reused here.

## 2. Source Documents

Source workflow spec:
- `docs/specs/01-development-documentation-operating-model.md` [DOM-5],
  [DOM-8], [DOM-10], [DOM-11]

Source product specs (what engram provides that the benchmark evaluates):
- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-19], [MM-27]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-27]
- `docs/specs/12-local-app-surface.md` [LAS-29], [LAS-30]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5], [CAA-10]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-16]

Source spec for the benchmark methodology itself:
- None yet. This plan defines the intended methodology. If the methodology
  stabilizes it should be promoted to a numbered spec, candidate name
  `20-memory-benchmark-methodology.md`.

Relevant prior plans and implementation notes:
- `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md` (superseded
  for methodology; corpus ingestion infra reused)
- `docs/plans/2026-04-21-codex-corpus-validation-implementation-plan.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/06-arc-context-assembly.md`

External tools:
- `llm` (Simon Willison) — already a dependency; used as the cross-provider
  model access layer for every role in the harness
- `sqlite-utils` — transitively present via `llm`; used for logs

External corpora:
- Regular (non-Claude-Code) Claude conversation exports — **primary corpus**.
  Selection rationale: exploratory conversations where memory continuity
  carries more load per turn than in task-execution sessions.
- Codex Claude Code JSONL archives — secondary corpus. Included as a
  cross-check after the primary corpus produces a pilot signal.

## 3. Context and Key Files

Files to create:
- `engram/commands/` — shared command/capability layer used by CLI,
  `EngramClient`, and benchmark adapters. This is the Engram equivalent of
  Weft's command layer: public behavior lives once, while CLI/client/tool
  surfaces adapt arguments and serialization.
  Initial modules:
  - `engram/commands/__init__.py`
  - `engram/commands/memory.py` — open/init helpers plus record, context,
    search, lookup, status, process, and snapshot operations over `Engram`
- `engram/client.py` — public `EngramClient`, analogous to `WeftClient`.
  The client is a thin adapter over `engram.commands`, not a second business
  logic layer and not a benchmark-only helper.
- `memeval/` — new top-level package, sibling to `engram/`, NOT a submodule.
  The benchmark must not live inside `engram/` because the benchmark is
  system-agnostic and engram is one of several systems under test.
  Subpackages:
  - `memeval/__init__.py`
  - `memeval/protocol.py` — `MemorySystem` Protocol + `SearchResult` model
  - `memeval/adapters/nomem.py` — NoMemory reference adapter
  - `memeval/adapters/lastn.py` — Last-N message window adapter
  - `memeval/adapters/flatrag.py` — (v0.5) Flat embedding RAG adapter
  - `memeval/adapters/engram_adapter.py` — Engram adapter (wraps `EngramClient`)
  - `memeval/corpus/` — corpus import, chronological ordering, snapshots
  - `memeval/harness/driver.py` — ping-pong conversation driver
  - `memeval/harness/rotation.py` — rotation matrix orchestrator
  - `memeval/harness/judge.py` — blinded pairwise judge
  - `memeval/harness/van.py` — pseudo-Van wrapper around `llm`
  - `memeval/briefings/` — briefing writer + schema + storage format
  - `memeval/results/` — per-run result logger and aggregator
  - `memeval/cli.py` — `memeval` CLI entry point
- `briefings/` — **repo-committed** benchmark asset directory (NOT under
  memeval/, because briefings are the benchmark not the code). One YAML-
  frontmatter file per checkpoint; schema defined in task T4.2.
- `tests/memeval/` — unit tests for adapters, driver, judge, rotation
- `docs/specs/20-memory-benchmark-methodology.md` — created after v0
  stabilizes; not a v0 deliverable
- `docs/implementation/07-memeval-harness.md` — rationale and boundaries

Files to read first, in order:
1. `README.md` — engram's thesis and current status
2. `engram/__init__.py` — the public engram API surface
3. `engram/core/memory.py` — current `Engram` class
4. `engram/_models.py` — `SearchResult`, `ContextView`, `ContextSection`
5. `engram/core/context.py` — how `build_context()` assembles output
6. `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md` — the
   mechanical-validation work this plan partially supersedes
7. One sample Claude conversation export (any non-Claude-Code thread)
8. `llm` documentation: https://llm.datasette.io/ (especially templates,
   conversations, and tools)

Shared helpers and patterns that MUST be reused:
- `llm.get_model()` is the only model access point. Do not call provider
  SDKs (anthropic, openai, google) directly. All calls go through `llm`.
- `engram.commands` is the shared command layer. CLI, `EngramClient`, and the
  benchmark adapter must use it rather than each reimplementing command
  behavior.
- `EngramClient` is the public programmatic adapter. The benchmark's Engram
  adapter wraps `EngramClient`, not `engram.core.memory.Engram` directly.
- This historical plan predates the foundation API cleanup. The current
  low-level direct lookup surface is `Engram.lookup()`. Do not reintroduce
  `Engram.get()` as a backwards-compatibility alias.
- `engram/_models.py::SearchResult` is the canonical result shape. The
  benchmark's own `SearchResult` in `memeval/protocol.py` may need to be
  a narrower structural shape; if so, adapters convert at the boundary.
- `engram/_models.py::SearchResult` is a dataclass, not a Pydantic model.
  Tool serialization must use an explicit serializer such as `asdict()` or a
  command-layer DTO function, not `model_dump()`.
- Briefing files are committed artifacts. Never edit a briefing after a
  benchmark run has used it. Create `briefings/v1/` when the methodology
  shifts materially.

Important existing behavior the harness must not break:
- `record()` submits a weft task and returns immediately. The benchmark's
  warming phase must wait for all submitted tasks to complete before
  snapshotting, otherwise coalescing/indexing may be partial.
- `engram.core.memory.Engram` is not cheap to instantiate. Snapshot/restore
  by copying the vault directory, not by rebuilding an `Engram` instance
  from scratch each checkpoint.
- `Engram.build_context()` takes optional term-bias parameters. The adapter
  must expose this, but the benchmark's default policy is to call it with
  the upcoming user message as `term`.
- Benchmark responder tools must be read-only unless a task explicitly tests
  write behavior. For this plan, expose `context`, `search`, and `lookup` as
  LLM tools; do not expose `record` during evaluation because the vault is
  frozen at T-1.

Which current code owns the behavior being extended:
- `engram.Engram` — the low-level memory object. It should stay focused on
  domain behavior.
- `engram.commands` — the shared command/capability layer to add before the
  benchmark harness. This is where CLI/client/tool-safe command behavior lives.
- `engram.client.EngramClient` — the public client wrapper to add before the
  benchmark harness. This is the surface benchmark adapters and future agents
  should use.
- No existing code owns the benchmark. This plan creates the `memeval`
  package from scratch.

## 4. Invariants and Constraints

These must hold across every implementation and every run. If a task breaks
one, stop and revise the plan.

**Architecture invariants:**

1. **Chronological warming.** Memory systems are warmed with corpus data
   from time 0 to T-1 inclusive, where T is the checkpoint timestamp. Later
   data never leaks into earlier checkpoints. No separate "warming set" vs.
   "checkpoint set" exists — every moment is both potential warming material
   (for later T) and a potential checkpoint (for earlier T).

2. **Vault frozen during eval turns.** During a checkpoint's multi-turn
   simulation, the memory system's state MUST NOT be updated. Simulation
   turns are not ingested. The vault serves queries at T-1 throughout all
   simulation turns for that checkpoint.

3. **Identical tool surface across all memory systems.** Every
   `MemorySystem` implementation exposes `search(query, limit)` and
   `lookup(item_id)` with identical signatures and result shapes. The
   model cannot tell which system it is talking to from the tool interface.
   Differences live in what the tools return and what
   `context_for_turn()` injects, not in the tool schema.

4. **Same model for responder across arms.** The model-under-test (the
   agent responding to pseudo-Van) is held constant across NoMemory,
   LastN, and Engram arms of a given checkpoint run. We are measuring
   memory systems, not models. Responder model rotation is a v1 question.

5. **Briefings are immutable per eval generation.** Once a briefing is
   committed and a benchmark run uses it, the briefing cannot be edited
   for that generation. Methodology changes require bumping generation:
   `briefings/v1/`, `briefings/v2/`, etc. Prior generations remain in the
   repo for reproducibility.

6. **All model access through `llm`.** No direct provider SDK calls in
   the harness. This keeps the "everything constant except model"
   property intact.

7. **Claim scope.** Results make claims about engram vs. listed baselines
   on the configured corpus. They do not make claims about "memory systems
   in general," "long-term memory," or cross-model generalization. The
   claim lives within the scope of what was actually tested.

8. **Shared Engram command layer.** Any Engram behavior exposed through CLI,
   client, or LLM tools must be backed by the same command/capability layer.
   Do not let `memeval` become the only place where tool-safe Engram behavior
   exists.

**Data invariants:**

9. **Snapshot integrity.** A snapshot must be fully restorable: cloning
   the snapshot produces a vault in exactly the state it was in at
   snapshot time, including pending weft tasks having been processed to
   completion. Incomplete snapshots (tasks still running) are not
   allowed.

10. **Access score isolation per checkpoint.** Running a checkpoint
   MUST NOT affect access scores visible to other checkpoints. Each
   checkpoint gets its own clone; clones are deleted after the run.

11. **Briefing content constraints.** Briefings state intent and
    constraints, not conclusions or specific solutions. Phrases like
    "Van will want..." or "Van's eventual answer is..." are prohibited.
    Violations are fixed in the draft-edit loop, before the briefing is
    committed.

**Operational invariants:**

12. **No simulation turn is ingested.** The pseudo-Van turns and the
    responder turns within a simulation are discarded after the
    checkpoint run. None of them enter any memory system's persistent
    state.

13. **Judge blinding.** The judge sees responses labeled X/Y (or A/B),
    not "engram" vs "nomemory". Label assignment is randomized per
    judgment call. The harness tracks the mapping for result aggregation;
    the judge never does.

## 5. Hidden Couplings and Gotchas

**Coupling: `record()` is async.** A warming pass that returns
immediately has not necessarily finished indexing. Before snapshotting,
call `work_until_idle()` or the equivalent process API. Without this, a
snapshot captures partial state.

**Coupling: LanceDB + SQLite dual-write.** Engram's state store is
authoritative; LanceDB is rebuildable. Snapshot BOTH; if only SQLite is
snapshotted, the restored vault is missing embeddings until reindexed.
Document the snapshot layout explicitly.

**Coupling: `llm` conversation_id is per-model.** You cannot hand off a
conversation between models. Each role (responder, pseudo-Van, judge) uses
one model within a checkpoint; rotations change the model between
checkpoints, not within.

**Coupling: tool result serialization.** `llm` passes tool call results
back to the model as JSON. Tool returns must be plain JSON-serializable
dicts/lists/scalars. Engram's `SearchResult` is a dataclass, while
`MemoryItem` and status objects are Pydantic models. The command layer owns
serialization so CLI, `EngramClient`, and tools do not drift.

**Coupling: LLM tools are agent-facing public API.** Once `EngramClient`
exposes `context`, `search`, and `lookup` as tools, prompt authors will depend
on names, descriptions, argument schemas, and return shapes. Version these
carefully and avoid leaking benchmark-only concepts into the Engram client.

**Gotcha: System prompts and tool schemas differ per provider.** Even
though `llm` abstracts the call, the rendered tool schema differs between
Claude, GPT, Gemini. A tool that "works" on one may fail on another due
to schema quirks. Test every responder family with every adapter's tool
surface in the pilot.

**Gotcha: Rate limits.** A rotation run makes hundreds of LLM calls in
sequence. Implement retry with exponential backoff at the `llm` call
boundary. Record the backoff events in the run log; a run with many
backoffs may have stretched timing that affects provider-side state.

**Gotcha: Model version drift.** `gemini-2.5-pro` as written here is a
moving target. Pin specific model versions in the rotation config. Record
the exact model IDs used in each run's result file; when they change,
re-run the benchmark rather than comparing across versions.

## 6. Tasks

Tasks are dependency-ordered. Each has its own test requirement stated
inline. Do not skip the red-green test-first pattern where the task
marks it explicitly. Do not treat later tasks as blockers for earlier
ones; each should verify independently.

### Phase 0 — Engram client and shared command layer

**T0.1 — Create the shared Engram command layer.**
Create `engram/commands/` with a narrow command surface over
`engram.core.memory.Engram`. This layer should own command-style behavior and
serialization so CLI, `EngramClient`, and future LLM tools stay aligned.

Initial commands:
- `open_vault(path, create=False, ...) -> Engram`
- `record(memory, text) -> int`
- `context(memory, term=None, total_tokens=...) -> str`
- `search(memory, query, limit=...) -> list[dict[str, object]]`
- `lookup(memory, item_id) -> dict[str, object] | None`
- `status(memory) -> dict[str, object]`
- `process(memory, max_passes=...) -> dict[str, object]`
- `snapshot_vault(memory_or_path, output_path) -> None`

Do not add new domain behavior here. Commands delegate to `Engram` and adapt
inputs/outputs. If a command requires behavior `Engram` does not expose, stop
and decide whether that behavior belongs in the product API first.

Test: unit tests call commands against a real temporary vault. Verify search
and lookup return plain JSON-serializable dictionaries, `context` returns the
same rendered text as `Engram.build_context()`, and `process` reaches idle on a
small corpus.

**T0.2 — Add `EngramClient`.**
Create `engram/client.py` with a public `EngramClient`, analogous to
`WeftClient`.

Required shape:
```python
class EngramClient:
    def __init__(self, memory: Engram | None = None, *, path: str | Path | None = None): ...
    @classmethod
    def init(cls, path: str | Path | None = None, **options: object) -> EngramClient: ...
    @classmethod
    def open(cls, path: str | Path | None = None, **options: object) -> EngramClient: ...

    def record(self, text: str) -> int: ...
    def context(self, query: str | None = None, max_tokens: int = DEFAULT_CONTEXT_TOKENS) -> str: ...
    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]: ...
    def lookup(self, item_id: str | int) -> dict[str, object] | None: ...
    def status(self) -> dict[str, object]: ...
    def process(self, max_passes: int = 1000) -> dict[str, object]: ...
    def close(self) -> None: ...
```

`EngramClient` must call `engram.commands`; it must not duplicate command
logic. Re-export it from `engram/__init__.py` after it exists.

Test: client tests should prove parity with command outputs and prove `lookup`
uses `Engram.lookup()` without incrementing access unless the command explicitly
opts into access counting.

**T0.3 — Add read-only LLM tool constructors.**
Add a small tool-construction helper on or near `EngramClient`. Prefer
returning `llm.Tool` objects if `llm` is available; otherwise keep a
backend-neutral descriptor that the harness can convert to `llm.Tool`.

Required tools for this plan:
- `engram_context(query: str | None = None, max_tokens: int = 2048) -> str`
- `engram_search(query: str, limit: int = 10) -> list[dict[str, object]]`
- `engram_lookup(item_id: str) -> dict[str, object] | None`

Do not expose `record` as a responder tool in this benchmark. Simulation
turns must not mutate the frozen checkpoint vault.

Test: tool call tests invoke each tool against a real temporary vault and assert
plain JSON-serializable return values. If using `llm.Tool`, include one cheap
integration smoke with a tool-capable model only after unit tests pass.

### Phase 1 — Foundation (protocol and types)

**T1.1 — Define `MemorySystem` Protocol and shared types.**
Create `memeval/protocol.py`. Export:
- `SearchResult` dataclass (frozen, slots): `id: str`, `text: str`,
  `score: float`, `timestamp: int | None`, `tier: int | None`. Nothing
  else. Engram's richer shape is converted at the adapter boundary.
- `MemorySystem` Protocol:
  ```python
  def ingest(self, text: str, timestamp: int) -> None: ...
  def context_for_turn(self, prefix: list[Message], user_message: str) -> str: ...
  def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...
  def lookup(self, item_id: str) -> SearchResult | None: ...
  def snapshot(self, path: Path) -> None: ...
  def restore(self, path: Path) -> None: ...
  def process(self) -> None: ...  # block until async work is complete
  ```
- `Message` dataclass for the prefix: `role`, `text`, `timestamp`.

Test: structural — `isinstance(NoMemoryStub(), MemorySystem)` passes;
a class missing `search` does not.

**T1.2 — Add adapter stubs.**
Create `memeval/adapters/{nomem,lastn,flatrag,engram_adapter}.py` each
with a class raising `NotImplementedError` for every method. Purpose:
establish package structure and enable import-time validation before
implementing any adapter.

Test: each stub class is a structural `MemorySystem`.

### Phase 2 — Baselines

**T2.1 — Implement `NoMemory` adapter.**
`ingest` is a no-op. `context_for_turn` returns empty string. `search`
returns `[]`. `lookup` returns `None`. `snapshot`/`restore` touch a
sentinel file for layout uniformity. `process` is a no-op.

Test: round-trip — ingest 10 items, search returns empty, context is
empty, snapshot-then-restore preserves identity.

**T2.2 — Implement `LastN` adapter.**
Stores ingested texts in an in-memory deque of size N (configurable,
default 40). `context_for_turn` joins the deque contents with role
markers. `search` does case-insensitive substring match over the deque
contents. `lookup` by integer turn index. `snapshot`/`restore` use JSON.

Test: ingest 100 items; deque size stays at N; snapshot+restore preserves
order and contents.

**T2.3 — Implement `Engram` adapter.**
Wraps `engram.client.EngramClient`, not `engram.core.memory.Engram`
directly. `ingest` calls `EngramClient.record(text)` unless the timestamp
API has been explicitly added before this task. `context_for_turn` calls
`EngramClient.context(query=user_message)`. `search` and `lookup` call the
client and convert returned JSON dictionaries to `memeval.protocol.SearchResult`
at the benchmark boundary. `snapshot` calls `process()` then copies the vault
directory. `restore` must construct a fresh client over the restored clone
rather than replacing a directory underneath open SQLite/LanceDB handles.

Test: warm with 50 moments, process, snapshot, create new vault, restore,
verify search over the restored vault returns identical results.

**T2.4 — Implement `FlatRAG` adapter.** *(v0.5 target; skip if pilot
shows engram does not beat LastN — no point adding a stronger baseline.)*
Stores moments with embeddings in a flat LanceDB table (no tiering, no
access scoring). `context_for_turn` returns top-K cosine similarity
matches to the user message concatenated. `search` returns the same
top-K, ranked. Uses the same embedding model as engram for fair
comparison.

Test: warm with 100 moments, search for a phrase from a specific moment,
verify that moment is in the top-3 results.

### Phase 3 — Corpus, warming, and snapshots

**T3.1 — Corpus import.**
Write `memeval/corpus/loader.py`. Read Claude conversation exports from
a configured directory. Emit a stream of `Turn` records with fields:
`thread_id`, `pair_index`, `role`, `text`, `timestamp_ns`. The timestamp
must be nanosecond-precision and stable (re-importing the same source
file produces identical timestamps). If source timestamps are coarser,
use the source timestamp plus a deterministic intra-pair offset.

Reuse: the existing Codex JSONL parser from the 2026-04-18 Codex plan if
it landed; otherwise write a new one with the same shape.

Test: import a known-shape fixture; verify deterministic ordering across
two runs; verify timestamps monotonically increase within a thread.

**T3.2 — Global chronological ordering.**
Write `memeval/corpus/chronology.py`. Sort all turns globally by timestamp.
Tie-breaking: by thread_id (lexicographic), then by pair_index. Document
this rule in the module docstring; it's a reproducibility concern.

Test: given two threads with overlapping timestamps, produce a stable
ordering; verify the same ordering across two imports.

**T3.3 — Snapshot orchestrator.**
Write `memeval/corpus/warming.py`. Given a `MemorySystem` and a stream
of turns in chronological order, ingest into the system, calling
`process()` every N ingest (default N=100 to amortize process cost). Take
incremental snapshots at configurable intervals (default: every 500
turns). Produce a manifest `snapshots.json` mapping timestamp cutoffs
to snapshot paths.

Test: warm 1000 turns with snapshots every 250; verify 4 snapshots
exist; verify each snapshot restores to the expected state (exact
turn count equal to cutoff).

**T3.4 — Fast-forward applier.**
Given a snapshot manifest and a target timestamp T, select the latest
snapshot ≤ T-1, clone it, and ingest any remaining turns up to T-1.
Produce a temporary vault usable for a single checkpoint. Clean up
after.

Test: fast-forward to a timestamp that sits exactly on a snapshot
boundary (zero deltas to apply); fast-forward to a timestamp that
requires applying 300 deltas; both produce vaults with correct turn
counts.

### Phase 4 — Briefings

**T4.1 — Writer-agent prompt.**
Author `memeval/briefings/writer_prompt.txt`. The prompt must produce
a briefing that:
- States Van's intent, open questions, constraints, and concerns at T
- Is 3-6 sentences
- Does NOT reveal conclusions, specific solutions, or outcome phrasings
- Uses "Van is trying to understand X" style, not "Van wants Y"

Include two in-prompt examples: one good briefing, one bad briefing
(leaks outcome), with explicit commentary.

Version-pin: commit the prompt file. Any change requires a new briefing
generation (`briefings/v2/`).

Test: run the prompt against 5 hand-picked checkpoints from a test
thread; verify drafts do not contain prohibited phrasing. This is a
human-review test; document the review output.

**T4.2 — Briefing file schema.**
Each briefing lives at `briefings/v1/<thread_id>__<pair_index>.md` with
YAML frontmatter:
```yaml
---
checkpoint_id: <string, stable>
thread_id: <string>
pair_index: <int>
timestamp_ns: <int>  # T
confidence: high | medium | low
writer_model: <llm model id>
writer_prompt_version: v1
editor: van
editor_delta: minor | moderate | rewrite
---
```
Body is the briefing prose.

Write `memeval/briefings/schema.py` with Pydantic models to parse and
validate briefings at load time.

Test: parse a known-good briefing; verify a briefing with missing
frontmatter fields fails validation with a useful error.

**T4.3 — Checkpoint selection.**
Write `memeval/briefings/selection.py`. Criteria:
- Draw from the primary corpus (regular Claude exports)
- Skip turns where the user message is trivially short (< 30 chars)
  or is clearly meta-conversational ("thanks", "ok", etc.)
- Stratify across T values so the selection covers low/mid/high memory
  maturity
- Deterministic: given a corpus fingerprint and a target count, produce
  the same checkpoint set every time

For v0: target 20-30 checkpoints.

Test: given a fixture corpus, produce a reproducible selection; verify
stratification by emitting a histogram of T values.

**T4.4 — Draft and edit briefings.**
For each selected checkpoint, run the writer agent and produce a draft
under `briefings/v1/drafts/`. Human (Van) edits and commits to
`briefings/v1/`. Record `editor_delta` in the frontmatter based on
git-diff magnitude (automatable: minor < 20% line change; rewrite > 60%).

This task is a manual checkpoint with a required artifact: all 20-30
briefings committed before Phase 6 can begin.

Verification: `memeval briefings validate` (added with the harness CLI) passes for all
briefings; all `confidence: high` briefings have `editor_delta` recorded.

### Phase 5 — Harness

**T5.1 — `llm` invocation wrapper.**
Write `memeval/harness/llm_client.py`. Thin wrapper around
`llm.get_model().prompt()` that:
- Accepts model_id, system prompt, user message, tools, conversation_id
- Returns response text + tool call trace + token counts
- Retries with exponential backoff on rate-limit errors
- Records each call to a per-run JSONL log

Do not use `llm`'s built-in conversation store for evaluation
conversations; the harness owns conversation state. `llm`'s SQLite logs
are still on for provenance.

Test: mock `llm.get_model` and verify the wrapper produces the expected
call shape; test retry logic against a stubbed rate-limit error.

**T5.2 — Ping-pong driver.**
Write `memeval/harness/driver.py`. Given a checkpoint, a `MemorySystem`,
a pseudo-Van model, and a turn budget, run a linear conversation:
- Seed turn 0 with the historical user message at T
- Alternate agent / pseudo-Van responses for N turns
- At each agent turn, call `context_for_turn` and inject as system prompt
  preamble; expose tools via the llm wrapper
- At each pseudo-Van turn, system prompt is identity + briefing
- Log every turn, tool call, and context injection

The vault passed in is the restored clone at T-1. The driver does not
call `ingest()` on the vault during simulation — that's in the Invariants.

Test: with a `NoMemory` vault and a trivial briefing, run a 3-turn
conversation; verify 3 agent turns + 3 pseudo-Van turns + correct
logging.

**T5.3 — Rotation orchestrator.**
Write `memeval/harness/rotation.py`. Configurable rotation matrix:
- Responder model (fixed per run; v0 = `claude-sonnet-latest`)
- Pseudo-Van models (list; v0 = `[gemini-2.5-pro, gpt-5-mini]`)
- Judge models (list; v0 = `[gemini-2.5-pro, gpt-5-mini]`)
- Diagonal rule: pseudo-Van and judge within a rotation must be
  different model families
- Response sampling: run each (memory system, rotation) configuration
  K times with temperature=0.7 (v0 K=3)

For each checkpoint, the rotation produces K × |rotations| runs per
memory system.

Test: configure a 2×2 rotation with K=1; verify the expected number
of runs are produced; verify no rotation has the same model in two roles.

**T5.4 — Blinded pairwise judge.**
Write `memeval/harness/judge.py`. Input: checkpoint context,
response_A, response_B (labels pre-shuffled by the caller). Output:
structured JSON with `winner: "X" | "Y" | "tie"` and `reasoning: str`.

Use `llm`'s schema flag for structured output. Do not trust regex
parsing. The judge prompt template lives at
`memeval/harness/judge_prompt.txt`, version-pinned.

Test: the judge, given two obviously-differently-quality responses
(one actually addresses the question, one is "I don't know"), reliably
picks the right one across 5 independent calls.

**T5.5 — Result logger and aggregator.**
Write `memeval/results/logger.py`. Each run produces
`.engram-runs/<run_id>/` with:
- `config.json` — rotation matrix, model pins, pseudo-Van prompt hash,
  briefing generation, corpus fingerprint
- `checkpoints/<checkpoint_id>.jsonl` — one line per turn per rotation
- `judgments/<checkpoint_id>.jsonl` — judge outputs
- `summary.json` — aggregates: per-system win rate, per-rotation
  agreement, per-temporal-distance breakdown

Write `memeval/results/aggregate.py` to compute summary from raw logs.
Include bootstrap confidence intervals on win rates.

Test: feed fixture judgments in; verify summary.json matches expected
values.

### Phase 6 — Pilot

**T6.1 — Select 5 pilot checkpoints.**
A deliberate hand-picked subset for methodology shakedown, not a
statistical sample. Choose checkpoints that span:
- Early (T small, little vault history)
- Mid (T medium, episodes present, maybe first arc)
- Late (T large, multiple arcs, decay has accumulated)

Commit the selection to `briefings/v1/pilot.txt` (list of checkpoint_ids).

**T6.2 — Run pilot.**
Configuration:
- Memory systems: NoMemory, Engram
- Rotation: one (pseudo-Van=Gemini, judge=GPT)
- Response samples: K=3
- Turns per checkpoint: 3

Execute via `memeval run --config pilot.yaml`. Output to
`.engram-runs/pilot-<date>/`.

**T6.3 — Pseudo-Van fidelity check.**
For each pilot checkpoint, compare pseudo-Van's turn 1 response to the
actual historical user's response at pair_index+1. Score qualitatively:
does pseudo-Van pursue the same intent as real-Van did? Annotate the
pilot output with fidelity notes.

This is NOT an automated test — it's a human-review task. Document
findings in `.engram-runs/pilot-<date>/fidelity_notes.md`.

**T6.4 — Judge calibration check.**
Examine the judge's reasoning across pilot judgments. Are the
reasonings coherent? Are "same" judgments dominant (>60%)? If so,
the judge is under-discriminating and the prompt needs tightening.

Document in `.engram-runs/pilot-<date>/judge_notes.md`.

**T6.5 — Pilot go/no-go.**
After reviewing fidelity and judge notes, decide:
- **Go to v0**: pseudo-Van fidelity is acceptable, judge discriminates,
  engram shows at least a directional signal vs. NoMemory.
- **Iterate first**: one or more of the above fails. Revise prompts,
  re-run pilot. Do not advance to v0 on broken methodology.

Document the decision and reasoning in
`.engram-runs/pilot-<date>/decision.md`.

### Phase 7 — v0 benchmark

**T7.1 — Draft remaining briefings.** Draft and edit briefings for the
remaining 15-25 checkpoints (total 20-30 for v0). Follow T4.4. Commit
all before any v0 runs start.

**T7.2 — Run v0.**
Configuration:
- Memory systems: NoMemory, LastN (N=40), Engram
- Rotations: 2 `[(Gemini, GPT), (GPT, Gemini)]`
- Response samples: K=3
- Turns per checkpoint: 5

Execute via `memeval run --config v0.yaml`. Output to
`.engram-runs/v0-<date>/`.

Expected total LLM calls: ~30 checkpoints × 3 systems × 2 rotations × 3
samples × 5 turns × 3 roles (responder, van, judge-fraction) ≈ 4000
calls. Budget accordingly; expect ~$50-200 in LLM costs.

**T7.3 — Aggregate and report.**
Run `memeval aggregate --run v0-<date>`. Inspect `summary.json`:
- Per-pair win rates with 95% bootstrap CIs
- Per-rotation agreement (does engram's advantage hold across both
  rotations?)
- Per-temporal-distance stratification (does engram's advantage grow
  with T?)

**T7.4 — Results document.**
Write `docs/implementation/08-memeval-v0-results.md`. Structure:
- What was tested (systems, corpus, rotation)
- Headline finding (with CIs, not point estimates)
- Per-strata findings
- Methodology caveats (author-editor bias, asymmetric oracle,
  scope limits)
- What v1 would require

### Phase 8 — Post-v0

**T8.1 — Commit v0 as a frozen artifact.**
Tag the repo at v0 completion. `briefings/v1/` is now immutable for
this generation. The `.engram-runs/v0-<date>/` directory is preserved;
aggregated results are in version control.

**T8.2 — Plan v1 based on v0 findings.**
Out of scope for this plan, but the output of v0 is input to a v1
plan. Decisions to surface:
- Is FlatRAG worth implementing as a stronger baseline?
- Are more checkpoints warranted (targeting 100+)?
- Should v1 include cross-model responder rotation?
- Is there enough signal to write a methodology spec?

## 7. Testing Plan

Each task above has an inline test requirement. Aggregated testing
principles:

**Engram command/client tests (T0.x):**
- Commands run against real temporary vaults and return tool-safe,
  JSON-serializable values.
- `EngramClient` method outputs match command-layer outputs.
- Read-only LLM tools expose only `context`, `search`, and `lookup`.

**Adapter tests (T2.1-T2.4):**
- All adapters round-trip through snapshot/restore.
- All adapters implement the Protocol structurally.
- Adapters are tested against the real underlying system (for Engram,
  real SQLite + LanceDB; no mocking of storage layers).

**Corpus tests (T3.x):**
- Deterministic ordering: same corpus → same snapshot timestamps
  across runs.
- Chronological invariant: no turn at T_n has T > any turn at T_{n+1}.
- Fast-forward correctness: vault at reconstructed T-1 equals vault
  at originally-warmed T-1.

**Briefing tests (T4.x):**
- Schema parse/validation against both valid and invalid fixtures.
- Prohibited-phrasing filter: draft briefings are scanned for outcome
  leakage patterns before being shown to the editor.

**Harness tests (T5.x):**
- Driver test with a stubbed memory system that records all calls;
  verify the expected sequence of `ingest` / `context_for_turn` /
  `search` / `lookup` calls.
- Judge test with hand-crafted response pairs where the winner is
  obvious.
- Rotation test with a mocked model pool; verify the expected set of
  configurations is generated.

**What must NOT be mocked:**
- The actual engram `Engram` class. The Engram adapter is tested
  against the real class.
- LanceDB and SQLite storage. Adapters run against real temporary
  directories.
- `llm` model calls in integration tests. Unit tests mock `llm`;
  integration tests use a cheap real model (e.g., haiku or flash)
  and assert on structural properties, not specific content.
- The briefing edit step. Never script around human editing; the
  pipeline stops at "drafts ready for human review" and resumes at
  "edits committed."

**What should be mocked:**
- `llm` model calls in unit tests (use a stub that returns a canned
  response).
- Timestamps in some corpus tests (use fixed timestamp fixtures).
- File-system operations can be patched in unit tests but real temp
  directories are preferred where feasible.

## 8. Verification and Gates

Pre-implementation checks:
- `docs/specs/` linked specs exist and are readable
- `engram/` public API is stable (no planned breaking changes mid-plan)
- At least one sample Claude conversation export is available

Per-phase gates:

**After Phase 0:** `pytest tests/client tests/commands` passes, and
`EngramClient` can expose read-only LLM tools backed by the shared command
layer.

**After Phase 1:** `pytest tests/memeval/` protocol/import tests pass, and
every adapter stub is structurally compatible with `MemorySystem`.

**After Phase 2:** `pytest tests/memeval/adapters/` passes; each
adapter can `ingest(), search(), context_for_turn(), snapshot()`,
`restore()`.

**After Phase 3:** A fixture corpus can be warmed, snapshotted, and
fast-forwarded. Reproducible across two runs.

**After Phase 4:** `memeval briefings validate` passes for all pilot
briefings. Writer prompt is version-pinned and committed.

**After Phase 5:** A single full checkpoint run with NoMemory vs.
Engram completes end-to-end with logged output.

**After Phase 6:** Pilot complete; go/no-go decision documented.

**After Phase 7:** v0 run complete; aggregated results show
non-zero directional finding for engram vs. NoMemory. (If this
gate fails, the plan's conclusion is "engram did not win" — which
is a valid outcome, not a rework trigger.)

**After Phase 8:** `briefings/v1/` is tagged as immutable;
`docs/implementation/08-memeval-v0-results.md` is written and
reviewed.

## 9. Independent Review Loop

Reviewer: different agent family than the implementer. Preferred
order:
1. Gemini-based agent (if available at review time)
2. GPT-based agent
3. Claude with a separate persona/profile and zero context from this
   planning conversation

Materials for reviewer:
- This plan
- `engram/client.py` and representative command-layer files (after Phase 0)
- `memeval/protocol.py` (after T1.1 lands)
- One implemented adapter (after T2.3 lands)
- The pilot output (after Phase 6)

Review prompt (paraphrase):
> You are reviewing a plan and implementation for a memory-system
> benchmark. The goal is to measure whether engram's tiered memory
> system beats simpler baselines on real conversational corpora.
> Read the plan and linked code. Answer: (1) could a competent
> engineer unfamiliar with this codebase implement this correctly
> on the first pass? (2) which invariants are most likely to be
> violated in practice? (3) is the v0 sample size and rotation
> plan likely to produce a signal that answers the question? (4)
> what author-bias risks do you see that are not addressed?

The review is not complete until each finding is either addressed
in code/plan or documented in a "rejected with reasoning" section.

## 10. Out of Scope

Explicitly not in this plan:

- Cross-model responder rotation (testing whether engram helps Gemini
  or GPT, not just Claude). v1+ question.
- Publishable methodology paper. Potential v2+ output, not a v0
  deliverable.
- Standalone benchmark repo extraction. memeval lives under engram's
  repo for now. If the methodology matures, extract.
- Third-party memory system adapters (Mem0, Letta/MemGPT, Zep). v1+.
- Corpus curation tooling (browsing exports, selecting threads,
  annotating). Manual for v0.
- Web UI for inspecting results. `cat summary.json` is sufficient.
- CI integration for benchmark runs. Runs are local, human-triggered.

## 11. Rollback and Rollout

**Rollout sequencing:**

The plan is additive but not isolated to `memeval/`: Phase 0 adds
`engram.commands` and `engram.client`. Those surfaces are product-facing
because they are useful beyond the benchmark. After Phase 0, `memeval/` is a
new package layered on top of those public surfaces.

The main cross-cutting concern is keeping CLI, `EngramClient`, LLM tools, and
benchmark adapters on the same command path. If Engram's public API changes,
update the command layer first, then let the client and benchmark consume the
same command behavior.

**Rollback:**

Before any v0 run: benchmark-specific code can be reverted by removing
`memeval/`, `tests/memeval/`, and benchmark docs. Phase 0 client/command-layer
code should be evaluated separately; if it has become part of the product
surface, do not remove it just because the benchmark methodology changes.

After v0 run: `briefings/v1/` and `.engram-runs/v0-*/` are
committed artifacts. Do not delete. If the methodology is flawed,
write `briefings/v2/` and leave v1 in place for reproducibility.

**One-way doors:**

The only one-way door is briefing commitment. Once a briefing is
used in a run, editing it invalidates that run and any comparison
against it. The mitigation is generation numbering: v1, v2, v3
coexist in the repo and runs cite which generation they used.

## 12. Fresh-Eyes Review

Before calling this plan ready, re-read as a new engineer:

- Can I identify the minimum set of files to read before writing
  code? (Section 3 lists them; is the list correct?)
- Can I explain what "chronological warming" means in one sentence?
  (If not, Section 4 invariant 1 needs more detail.)
- Do I understand why briefings must be immutable per generation?
  (If not, Section 4 invariant 5 needs more rationale.)
- Do I know which file to start editing for Phase 0?
  (`engram/commands/memory.py`, then `engram/client.py`.)
- Can I run the pilot with the documented commands? (After Phase 5
  lands, `memeval run --config pilot.yaml` is the entry point.
  Document this as it lands.)

Comprehension questions for reviewers:

1. Why is the vault frozen during simulation turns?
2. Why is the responder model held constant across memory system
   arms?
3. What's the difference between a "rotation" and a "response
   sample," and why do you want both?
4. What's in a briefing, and what's NOT in a briefing?
5. What happens if engram's coalescing is slow enough that warming
   doesn't finish before a checkpoint runs?

A reviewer who can answer all five without re-reading the plan has
understood it.

## 13. Relation to Prior Plans

This plan supersedes the evaluation methodology sections of
`docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`. That
plan's mechanical validation (ingest-and-verify) work remains
relevant and is reused in Phase 3 (corpus import, chronological
ordering).

Specifically:
- The Codex JSONL parser from the prior plan is reused in T3.1 if
  it has landed; otherwise written here.
- The `record()` source-timestamp work from the prior plan is a
  prerequisite for warming with historical timestamps; if that is
  not yet implemented in `engram/core/memory.py`, this plan adds
  that to T3.1 as a sub-task.
- The prior plan's "practical validation" A/B test is replaced by
  the benchmark's rotation + blind judge protocol. Simpler
  single-arm validation is no longer the primary test.

The prior plan's "status" should be updated to "Superseded by
2026-04-18-memory-benchmark-harness-plan.md for methodology; ingest
infrastructure still referenced." Making that edit is out of scope
for this plan but should be done as a small follow-up.
