# 2026-04-21 Codex Corpus Validation Implementation Plan

Status: Proposed

This plan refines `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`
into an implementation-ready task list. It keeps the same product direction:
use real Codex conversation history to validate Engram mechanically first, then
holistically.

## 1. Goal

Build a disciplined dogfooding harness that replays Codex JSONL conversations
into fresh Engram vaults in temporal order, proves the memory pipeline works
mechanically, and then evaluates whether periodic `build_context()` output would
have helped a fresh-start agent answer later turns. The harness is development
tooling, not a polished user-facing product surface.

The first proof must answer two different questions:

1. Mechanical: can Engram ingest real conversation-derived moments and produce
   indexed moments, episodes, arcs, valid status output, and context snapshots?
2. Practical: at selected checkpoints, would Engram context have improved
   continuity, correctness, or reduced user restatement compared with no memory?

## 2. Source Documents

Workflow and planning guidance:

- `AGENTS.md`
- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/lessons.md`

Product specs:

- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-3], [MM-6],
  [MM-7], [MM-9], [MM-12], [MM-19], [MM-20], [MM-21], [MM-27],
  [MM-28]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1],
  [MWS-3], [MWS-5], [MWS-7], [MWS-10], [MWS-16], [MWS-17],
  [MWS-20], [MWS-23], [MWS-25], [MWS-27], [MWS-33], [MWS-34],
  [MWS-37], [MWS-38], [MWS-39]
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-2], [LAS-8],
  [LAS-10], [LAS-12], [LAS-17], [LAS-19], [LAS-22], [LAS-23],
  [LAS-24]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-3],
  [CAA-4], [CAA-5], [CAA-6], [CAA-9], [CAA-10], [CAA-12],
  [CAA-15]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1], [EWM-2],
  [EWM-4], [EWM-13], [EWM-16], [EWM-18], [EWM-19], [EWM-20],
  [EWM-22], [EWM-23]

Current implementation rationale:

- `README.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
- `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`

External corpus sources:

- Primary corpus: `~/.codex/sessions/**/*.jsonl`
- Smoke and fixture corpus: `~/.codex/archived_sessions/*.jsonl`
- Optional metadata source: `~/.codex/session_index.jsonl`
- Explicitly deferred: live Codex sqlite state, recovery artifacts, and
  `~/.codex/history.jsonl`

Source spec for this harness:

- None yet. This plan defines a development harness. If the workflow becomes a
  durable product surface, promote its stable behavior into `docs/specs/`.

## 3. Audience, Style, And Tooling Assumptions

Assume the implementing engineer is strong but has no project context and tends
to over-mock. Follow the repository guidance literally.

Code style:

- Put `from __future__ import annotations` at the top of every new Python file.
- Use `Path` from `pathlib`; do not use `os.path`.
- Use `collections.abc` for abstract collection types.
- Use `list[T]`, `dict[K, V]`, and `X | None`; do not introduce old
  `typing.List` / `typing.Optional` style.
- Prefer small dataclasses for immutable parsed values and Pydantic only when
  runtime validation is useful at a boundary.
- Keep imports grouped stdlib, third-party, local.
- Do not add a new dependency for JSONL parsing, CLI parsing, progress bars,
  dataframe output, or scoring.
- Do not create a generic plugin system, importer framework, or corpus registry.
  This is a Codex-corpus dogfooding harness only.

Development loop:

- Use red-green TDD for parser, manifest, importer, and report behavior.
- Write the smallest failing test that proves the intended behavior before
  implementation whenever practical.
- If red-green is not practical for a manual dogfood run, document the concrete
  command and observable result that replaces it.
- Use `rg` and `rg --files` for code search.
- Use the in-repo virtualenv binaries:
  - `./.venv/bin/python -m pytest ...`
  - `./.venv/bin/mypy engram`
  - `./.venv/bin/ruff check engram tests docs README.md`

Testing posture:

- Use real SQLite and real LanceDB in integration tests.
- Use the existing deterministic test fixtures for embeddings and summary
  generation unless the test is specifically proving the live external model
  boundary.
- Do not mock the parser, manifest writer, importer state changes, SQLite store,
  LanceDB index, or context builder in tests that are meant to prove those
  contracts.
- It is acceptable for ordinary pytest runs to use the current autouse test
  shims in `tests/conftest.py` for Weft submission, embeddings, and LLM summary
  generation. The live dogfood command is the proof for the full runtime shape.

## 4. Current State And Key Files

Current Engram behavior to understand before editing:

- `engram/core/memory.py`
  - `Engram.init(path)` creates a vault and initializes embedded Weft.
  - `Engram.open(path)` opens an existing vault only.
  - `record(text)` creates a tier-0 moment with a fresh nanosecond ID, stores it
    in SQLite, and submits one Weft-backed processing task.
  - `work_once()` and `work_until_idle()` are local repair/dogfood helpers that
    run the same domain operation used by Weft workers. They are not a second
    durable queue.
  - `build_context(...)` is the thesis surface. It must not increment access
    scores.
- `engram/store/sqlite.py`
  - SQLite is authoritative for memory items, parent-child edges, metadata,
    processing attempts, failures, and last known Weft correlation.
- `engram/index/lance.py`
  - LanceDB is a rebuildable retrieval projection. Do not store provenance or
    evaluation labels here.
- `engram/background.py`
  - Embedded Weft is the execution substrate. Do not shell out to `weft run`.
- `engram/cli.py`
  - Current CLI is a local app surface for Engram itself. Avoid broadening this
    into a public dogfood product unless this plan explicitly says to.
- `tests/conftest.py`
  - Existing tests already shim model/task boundaries for deterministic behavior.
    Reuse that posture instead of introducing broad mocks.

Files expected to be added:

- `engram/dogfood/__init__.py`
- `engram/dogfood/codex_jsonl.py`
- `engram/dogfood/codex_replay.py`
- `tests/dogfood/test_codex_jsonl_parser.py`
- `tests/dogfood/test_codex_replay.py`
- `tests/dogfood/fixtures/` with small hand-authored JSONL fixtures
- `docs/implementation/07-codex-corpus-validation.md`
- `docs/evaluation/codex-corpus-protocol.md`

Files that may be touched:

- `.gitignore` to ignore local run artifacts such as `.engram-runs/`
- `README.md` only if a short dogfood note is needed after the harness works
- `docs/lessons.md` only if the work exposes a durable repeated lesson

Files that should not be touched without stopping and replanning:

- `engram/store/sqlite.py`
- `engram/index/lance.py`
- `engram/core/memory.py`
- `engram/background.py`
- `pyproject.toml`
- `uv.lock`

Those files are core product/runtime surfaces. The first implementation should
reuse them through the public `Engram` API, not change them.

Comprehension questions before editing:

1. Why is SQLite the source of truth while LanceDB is disposable?
2. Why must generated corpus provenance live outside core `memory_items`?
3. Why does a fresh validation run use a new vault instead of `forget --all`?
4. Why are future turns oracle evidence, not model input?
5. Which tests should use real SQLite/LanceDB, and which external boundaries may
   remain deterministic shims?

## 5. Corpus Extraction Contract

Observed local corpus facts as of this plan:

- `~/.codex/sessions/**/*.jsonl` contains hundreds of session logs and is the
  primary corpus.
- `~/.codex/archived_sessions/*.jsonl` currently contains a small number of
  archived rollouts and is useful for smoke tests and fixtures.
- `sessions/` and `archived_sessions/` may overlap. Import runs must default to
  `sessions/` only and include archived sessions only when explicitly requested
  for smoke testing.
- Newer files are event logs with records such as `session_meta`,
  `response_item`, `event_msg`, `turn_context`, and `compacted`.
- Useful conversational material in the newer format lives in
  `record["type"] == "response_item"` and
  `record["payload"]["type"] == "message"`.
- `role == "user"` and `role == "assistant"` are eligible for first-pass import.
- `role == "developer"` is not eligible.
- Tool calls, tool outputs, reasoning records, token-count events, turn context,
  compaction records, and telemetry are not eligible.

Parser scope:

- Support the current event-log shape first.
- Detect legacy or unknown JSONL shapes and report them as unsupported with
  counts. Do not silently ingest them.
- Only add support for legacy top-level message shapes after a separate fixture
  proves the role/content/timestamp extraction contract.

Text extraction rules:

- Extract only textual content from eligible user/assistant messages.
- If content is a string, use it after stripping whitespace.
- If content is a list, concatenate text-bearing parts in order. Accept common
  fields such as `text`, `input_text`, and `output_text` when present.
- Ignore non-text parts such as image references, tool call structures, and
  opaque payloads.
- Drop an eligible message if no non-whitespace text remains.

Pairing rule for imported moments:

- A first-pass Engram moment is one paired conversational unit:

  ```text
  User:
  <one or more consecutive user messages>

  Assistant:
  <the next assistant message>
  ```

- Consecutive user messages before an assistant reply are grouped into the user
  side of the same pair.
- Assistant messages with no pending user text are ignored and counted.
- User text with no later assistant reply is ignored for paired-moment import and
  counted as an incomplete pair.
- Pair order is source order within a session.
- Cross-session ordering is by source timestamp where available, then source file
  path, then pair index.
- If the same source file is reachable through more than one configured corpus
  root, import it once. Prefer the `sessions/` path over `archived_sessions/`.

Timestamp rule:

- Do not widen `Engram.record()` to accept source timestamps in this slice.
- Do not add an internal memory insert path just to preserve original source
  timestamps.
- Replay pairs in source order into a fresh vault. Engram's nanosecond IDs will
  represent replay order, which is sufficient for mechanical and time-sliced
  validation.
- Preserve original source timestamps in the sidecar manifest.
- Stop and replan if exact source timestamps become necessary for correctness,
  because that would affect core memory semantics.

Manifest schema:

- Write one JSONL manifest row per imported pair.
- Write one JSON summary file per run.
- Suggested paths under the run directory:
  - `<run_dir>/manifest.jsonl`
  - `<run_dir>/run-summary.json`
  - `<run_dir>/mechanical-report.json`
  - `<run_dir>/context-snapshots/*.md`
  - `<run_dir>/checkpoints/*.json`

Each manifest row must include:

```json
{
  "schema_version": 1,
  "run_id": "codex-YYYYMMDD-HHMMSS",
  "source_kind": "codex-session-jsonl",
  "source_path": "/absolute/path/to/session.jsonl",
  "session_id": "string-or-null",
  "thread_name": "string-or-null",
  "pair_index": 0,
  "global_import_index": 0,
  "source_user_timestamps": ["..."],
  "source_assistant_timestamp": "...",
  "engram_moment_id": 123,
  "moment_text_sha256": "hex",
  "user_preview": "short text",
  "assistant_preview": "short text"
}
```

The manifest is an evaluation artifact. It is not Engram memory truth.

## 6. Invariants And Constraints

Memory invariants:

- Use a fresh vault per validation run.
- Do not implement `forget --all`, `forget --reset`, or any destructive reset as
  part of this plan.
- Do not delete, rewrite, or mutate source Codex JSONL files.
- Do not add source-thread ids, checkpoint labels, or evaluation metadata to
  `memory_items`.
- Do not widen `record()` for this harness.
- Do not store corpus provenance in LanceDB.
- Moments created by replay are normal Engram moments.
- Summary creation must remain additive.
- Context assembly must not increment access scores.

Execution invariants:

- Reuse `Engram.init`, `Engram.open`, `record`, `work_until_idle`, `status`,
  `search`, and `build_context`.
- Do not introduce a second durable queue.
- Do not use heartbeat or persistent named tasks for this validation slice.
- Do not shell out to `weft run` from Engram.
- The harness may call local repair helpers because those already wrap the same
  domain operation as the Weft task path.

Evaluation invariants:

- Mechanical validation and practical validation are different proofs. Do not
  merge them into one score.
- Future turns must be used only as oracle evidence. They must not be included
  in the memory available to the treatment answer.
- Practical evaluation must prefer relatively timeless checkpoints:
  architecture, planning, workflow, design, and conceptual discussions.
- Avoid first-pass checkpoints that depend on exact live workspace state,
  changing library versions, current command outputs, or hidden files.

Artifact and privacy constraints:

- Raw run artifacts may contain private conversation data. Keep generated
  artifacts under a gitignored run directory such as `.engram-runs/`.
- Do not commit raw context snapshots, manifests, or baseline/treatment answers
  unless the user explicitly asks for a curated artifact.
- Documentation committed to `docs/` should describe the workflow and summarize
  non-sensitive findings, not dump raw conversations.

Failure-priority rules:

- Parser failures on malformed lines are recoverable if they are counted and
  reported with source path and line number.
- Manifest write failures are fatal for importer runs. Without a manifest, the
  evaluation cannot be audited.
- Engram `record()` failures are fatal for the current run.
- Processing failures after import are not fatal to import, but they are fatal to
  a successful mechanical validation gate if unresolved.
- Unsupported corpus formats are not fatal if the report clearly separates
  supported, skipped, and malformed records.

DRY and YAGNI rules:

- Do not duplicate Engram processing logic in the dogfood harness.
- Do not add a generic import framework.
- Do not add a scoring model or LLM judge in the first pass.
- Do not create a reusable Codex skill until the prompt protocol works across
  several checkpoints.
- Do not add dependencies.

## 7. Rollout, Rollback, And One-Way Doors

Rollout:

1. Land parser and manifest tests first.
2. Land importer against small fixtures second.
3. Land mechanical validation runner third.
4. Run small real corpus smoke.
5. Only after mechanical gates pass, run practical checkpoint evaluation.

Rollback:

- All new dogfood code should be isolated under `engram/dogfood/`.
- Generated run data should live outside tracked files under `.engram-runs/`.
- Reverting `engram/dogfood/`, `tests/dogfood/`, and the dogfood docs should
  remove the harness without affecting core Engram behavior.

One-way doors:

- None are allowed in this plan.
- If implementation starts requiring schema migration, timestamp-preserving core
  insert APIs, deletion/reset, or new dependencies, stop and replan before
  coding further.

## 8. Bite-Sized Tasks

### Task 1: Add Dogfood Package Skeleton And Artifact Ignore Rules

Outcome:

- A small internal dogfood namespace exists without changing core Engram
  behavior.
- Local generated run artifacts are gitignored.

Files to touch:

- `.gitignore`
- `engram/dogfood/__init__.py`
- `tests/dogfood/` directory scaffold if needed

Read first:

- `.gitignore`
- `engram/__init__.py`
- `docs/implementation/02-repository-map.md`

Required implementation:

- Add `.engram-runs/` to `.gitignore`.
- Create `engram/dogfood/__init__.py` with a short module docstring. Do not
  re-export anything yet.

Tests:

- No runtime test is required for the empty package.
- Run `./.venv/bin/ruff check engram tests docs README.md`.

Stop and re-evaluate if:

- You want to add a public `engram dogfood` CLI command before parser/importer
  behavior exists.
- You want to add a new dependency.

Done signal:

- The package imports and lint passes.

### Task 2: Write Parser Fixtures Before Parser Code

Outcome:

- The intended JSONL extraction contract is captured in test fixtures before
  implementation.

Files to touch:

- `tests/dogfood/fixtures/current_event_log.jsonl`
- `tests/dogfood/fixtures/mixed_noise_event_log.jsonl`
- `tests/dogfood/fixtures/unsupported_legacy_shape.jsonl`
- `tests/dogfood/test_codex_jsonl_parser.py`

Read first:

- The "Corpus Extraction Contract" section of this plan.
- Two representative real files from `~/.codex/sessions/**/*.jsonl`.
- One file from `~/.codex/archived_sessions/*.jsonl`.

Required fixture coverage:

- `current_event_log.jsonl` includes:
  - one `session_meta`
  - one developer `response_item.payload.type == "message"` that must be skipped
  - one user message
  - one assistant message
- `mixed_noise_event_log.jsonl` includes:
  - multiple consecutive user messages before one assistant response
  - a tool call or tool output record
  - a reasoning or token-count record
  - an assistant message without a pending user that must be counted as ignored
  - one trailing user without assistant that must be counted as incomplete
- `unsupported_legacy_shape.jsonl` includes a top-level shape that the parser
  should classify as unsupported rather than ingest.
- Fixtures must be hand-authored minimal examples. Do not copy raw private Codex
  transcripts into the repository.

Tests to write red first:

- `test_parser_extracts_user_assistant_pairs_from_current_event_log`
- `test_parser_groups_consecutive_user_messages_before_assistant`
- `test_parser_excludes_developer_tool_reasoning_and_telemetry_records`
- `test_parser_counts_incomplete_and_unmatched_messages`
- `test_parser_reports_unsupported_legacy_shape_without_ingesting_it`

What not to mock:

- Do not mock file reading.
- Do not mock JSON parsing.

Done signal:

- Tests fail because `engram.dogfood.codex_jsonl` does not exist yet or lacks the
  required behavior.

### Task 3: Implement The Read-Only Codex JSONL Parser

Outcome:

- A parser can turn supported Codex event logs into ordered candidate
  conversation pairs with diagnostics.

Files to touch:

- `engram/dogfood/codex_jsonl.py`
- `tests/dogfood/test_codex_jsonl_parser.py`

Read first:

- `engram/_models.py` for project modeling style.
- `engram/core/coalesce.py` for examples of small pure helpers.

Required implementation:

- Add frozen dataclasses:
  - `CodexMessage`
  - `CodexConversationPair`
  - `CodexParseStats`
  - `ParsedCodexSession`
- Add a parser function with a narrow signature:

  ```python
  def parse_codex_jsonl(path: Path) -> ParsedCodexSession: ...
  ```

- Add pure helper functions for:
  - extracting session metadata
  - identifying eligible message records
  - extracting text from message content
  - grouping messages into pairs
  - counting skipped/unsupported/malformed records
- Include source path, source line, timestamps, role, and session id in parsed
  values when available.
- Skip malformed JSONL lines only if stats record the failure. Do not silently
  ignore them.

Tests:

- Make Task 2 tests pass.
- Add a direct test for malformed JSONL counting.

What not to mock:

- Do not mock the parser helpers.
- Do not mock filesystem reads.

Stop and re-evaluate if:

- The parser needs more than a small number of corpus-specific branches.
- You find a second current Codex format with role/content semantics that are
  materially different from the event-log contract.
- Supporting legacy files requires inference rather than explicit role/content
  fields.

Done signal:

- Parser tests pass.
- No Engram vault is created by parser tests.

### Task 4: Add Corpus Discovery And Inspection

Outcome:

- The harness can inspect the local Codex corpus and report supported versus
  unsupported files before importing anything.

Files to touch:

- `engram/dogfood/codex_jsonl.py`
- `engram/dogfood/codex_replay.py`
- `tests/dogfood/test_codex_jsonl_parser.py`

Read first:

- `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`
- Real corpus root layout under `~/.codex/sessions/`

Required implementation:

- Add corpus discovery:

  ```python
  def discover_codex_jsonl_files(
      root: Path,
      *,
      include_sessions: bool = True,
      include_archived: bool = False,
  ) -> tuple[Path, ...]: ...
  ```

- Discovery must include by default:
  - `<root>/sessions/**/*.jsonl`
- Discovery must include only when `include_archived=True`:
  - `<root>/archived_sessions/*.jsonl`
- Discovery must exclude by default:
  - `<root>/recovery-*`
  - `<root>/history.jsonl`
  - `<root>/session_index.jsonl`
- Discovery must deduplicate resolved file paths and keep deterministic ordering.
- Add an inspection function that returns file counts, pair counts, skipped
  counts, malformed counts, unsupported counts, and date range when available.
- Add a module CLI entry point for inspection:

  ```bash
  ./.venv/bin/python -m engram.dogfood.codex_replay inspect --root ~/.codex
  ```

- This module CLI is internal dogfood tooling. Do not add it to
  `engram/cli.py` yet.

Tests:

- Use a temporary fake `~/.codex` tree.
- Assert discovery includes `sessions/` by default.
- Assert discovery excludes `archived_sessions/` by default.
- Assert discovery includes archived sessions only with `include_archived=True`.
- Assert discovery excludes recovery artifacts and index/history files.
- Assert duplicate resolved paths are imported once.
- Assert inspection reports unsupported files instead of failing the whole run.

What not to mock:

- Do not mock `Path.rglob`; use a temp directory tree.
- Do not mock parser output in the inspection integration test; use fixture
  files.

Stop and re-evaluate if:

- You want to parse live sqlite, `history.jsonl`, or recovery artifacts.
- You want to add a public CLI command before the internal module command is
  proven.

Done signal:

- Inspection command works on fixtures and returns deterministic JSON.

### Task 5: Implement Manifest Writer And Fresh-Vault Importer

Outcome:

- A small corpus sample can be replayed into a fresh Engram vault with a
  manifest mapping source pairs to Engram moment ids.

Files to touch:

- `engram/dogfood/codex_replay.py`
- `tests/dogfood/test_codex_replay.py`

Read first:

- `engram/core/memory.py`
- `tests/core/test_memory.py`
- `tests/cli/test_cli.py`
- `docs/implementation/05-local-vault-recovery.md`

Required implementation:

- Add a `CodexReplayOptions` dataclass with:
  - `root: Path`
  - `vault_path: Path`
  - `run_dir: Path`
  - `limit_files: int | None`
  - `limit_pairs: int | None`
  - `include_archived: bool`
  - `include_sessions: bool`
- Add a manifest row dataclass or Pydantic model matching the schema in this
  plan.
- Add a replay function:

  ```python
  def import_codex_pairs(options: CodexReplayOptions) -> CodexReplayResult: ...
  ```

- `import_codex_pairs` must:
  - require that `vault_path` does not already exist
  - require that `run_dir` does not already exist, or exists and is empty
  - call `Engram.init(vault_path)`
  - parse supported files
  - globally sort pairs by source timestamp, source path, and pair index
  - call `memory.record(pair.to_moment_text())` in order
  - write one manifest JSONL row per imported pair
  - write `run-summary.json`
  - close the Engram handle
- Do not preserve source timestamps in core Engram ids.
- Do not delete an existing vault.

Tests:

- Red first:
  - importer refuses to write into any existing vault path
  - importer refuses to write into a non-empty run directory
  - importer creates a fresh vault and manifest
  - manifest rows map back to `memory.lookup(id)`
  - imported moment text contains only user and assistant text
  - imported moment ids are strictly increasing for replay order
- Use real `Engram.init`, real SQLite, and real LanceDB.
- Rely on existing deterministic test shims for Weft/model boundaries.

What not to mock:

- Do not mock `Engram`.
- Do not mock SQLite or LanceDB.
- Do not mock manifest writes.

Stop and re-evaluate if:

- Import requires changing `record()`.
- Import requires deleting or resetting a vault.
- Manifest data starts leaking into core memory schema.

Done signal:

- A fixture corpus imports into a temp vault with a valid manifest and zero
  developer/tool/reasoning leakage.

### Task 6: Add Mechanical Processing And Report Generation

Outcome:

- One command can import a sample, process local processing, and prove the pipeline
  reaches moments, episodes, arcs, status, and context snapshots.

Files to touch:

- `engram/dogfood/codex_replay.py`
- `tests/dogfood/test_codex_replay.py`
- `docs/implementation/07-codex-corpus-validation.md`

Read first:

- `engram/core/memory.py`
  - especially `work_until_idle`, `status`, `build_context`, and `search`
- `engram/_models.py`
  - especially `VaultStatus`, `ContextView`, and `WorkResult`
- `tests/core/test_context.py`

Required implementation:

- Add a mechanical command:

  ```bash
  ./.venv/bin/python -m engram.dogfood.codex_replay mechanical \
      --root ~/.codex \
      --vault .engram-runs/codex-smoke/.engram \
      --run-dir .engram-runs/codex-smoke \
      --limit-pairs 200 \
      --snapshot-every 50 \
      --tokens 2048
  ```

- The command must:
  - import pairs into a fresh vault
  - call `work_until_idle()` after import batches or after import completes
  - call `status()`
  - call `build_context(total_tokens=...)` periodically based on imported pair
    count
  - save context snapshots as markdown or plain text under the run directory
  - save `mechanical-report.json`
- The report must include:
  - imported moment count
  - total item count
  - moment count
  - episode count
  - arc count
  - index row count
  - items needing processing
  - failed processing count
  - unindexed item count
  - context snapshot count
  - parser skipped/malformed/unsupported counts
  - whether the mechanical gate passed
- The first pass gate is:
  - non-zero imported moments
  - zero failed processing items
  - zero items needing processing after process
  - non-zero indexed items
  - at least one episode for a sample large enough to cross the coalescing
    minimum
  - at least one arc for a larger sample large enough to create multiple episodes

Tests:

- Use a synthetic fixture corpus large enough to produce episodes and arcs with
  deterministic summary shims.
- Assert report fields, not just command exit code.
- Assert context snapshot files exist and are non-empty.
- Assert `build_context()` did not increment access scores for sampled ids.

What not to mock:

- Do not mock `work_until_idle`, `status`, or `build_context`.
- Do not mock SQLite or LanceDB.

Stop and re-evaluate if:

- The mechanical run cannot produce arcs on a sufficiently large deterministic
  fixture.
- Processing failures accumulate after local process.
- Context snapshots are dominated by irrelevant or malformed imported text.

Done signal:

- Fixture mechanical test passes.
- A small real local run produces a report with moments, episodes, no failures,
  and at least one saved context snapshot.

### Task 7: Add Real-Corpus Smoke Commands And Runbook Documentation

Outcome:

- A future engineer can run mechanical validation safely without knowing the
  repo history.

Files to touch:

- `docs/implementation/07-codex-corpus-validation.md`
- possibly `README.md` for a short pointer only

Read first:

- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`

Required documentation:

- Explain the supported corpus roots.
- Explain why fresh vaults are used instead of reset/forget.
- Explain where run artifacts go and why they are gitignored.
- Include exact commands:

  ```bash
  ./.venv/bin/python -m engram.dogfood.codex_replay inspect --root ~/.codex

  ./.venv/bin/python -m engram.dogfood.codex_replay mechanical \
      --root ~/.codex \
      --vault .engram-runs/codex-smoke/.engram \
      --run-dir .engram-runs/codex-smoke \
      --limit-pairs 200 \
      --snapshot-every 50 \
      --tokens 2048
  ```

- Include the escalation path:
  - if parser unsupported counts are high, inspect formats before changing Engram
  - if processing failures appear, debug Engram processing before practical eval
  - if snapshots are noisy, tune context selection after mechanical proof

Tests:

- Docs-only verification by inspection.
- Run ruff over docs.

Stop and re-evaluate if:

- The documentation starts promising polished product behavior.

Done signal:

- A zero-context engineer can run inspect and mechanical smoke from the docs.

### Task 8: Define Practical Checkpoint Selection And Prompt Protocol

Outcome:

- The holistic validation method is explicit before anyone starts scoring by
  vibes.

Files to touch:

- `docs/evaluation/codex-corpus-protocol.md`
- optionally `engram/dogfood/codex_replay.py` for checkpoint candidate export
- `tests/dogfood/test_codex_replay.py` if candidate export is implemented

Read first:

- `README.md` context thesis sections
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-23],
  [MWS-37], [MWS-38], [MWS-39]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-5], [CAA-12],
  [CAA-15]

Required protocol:

- A checkpoint consists of:
  - source file
  - source pair index
  - current user message to answer
  - prior pairs available to memory
  - next one to three source pairs as oracle evidence only
  - reason the checkpoint is considered relatively timeless
- Baseline answer:
  - current user message only
  - no Engram context
  - no future turns
- Treatment answer, phase A:
  - same current user message
  - rendered `build_context()` from a vault containing only prior pairs
  - no Engram search/direct lookup
  - no future turns
- Treatment answer, phase B, later only:
  - same as phase A
  - allow a small fixed number of Engram retrieval calls
- Scoring:
  - `helpful`: likely improves correctness, continuity, or reduces restatement
  - `neutral`: no material difference
  - `harmful`: stale, irrelevant, distracting, or misleading context
- The future oracle is evidence, not truth. It can show whether the actual next
  turns repeated context, corrected an answer, or clarified something memory
  should have supplied.

Optional helper:

- Add a checkpoint export command only if it stays small:

  ```bash
  ./.venv/bin/python -m engram.dogfood.codex_replay checkpoints \
      --manifest .engram-runs/codex-smoke/manifest.jsonl \
      --output .engram-runs/codex-smoke/checkpoints \
      --limit 10
  ```

- If implemented, the helper should only assemble candidate data. It should not
  score answers.

Tests:

- If checkpoint export is implemented, test:
  - it never includes future pairs in the prior-memory set
  - it includes oracle pairs separately
  - it rejects checkpoints without future evidence
  - it records why stateful checkpoints were excluded or not selected

What not to mock:

- Do not mock manifest parsing if implementing export.

Stop and re-evaluate if:

- Candidate selection depends on hidden live workspace state.
- The protocol starts using future turns as treatment input.
- The scoring rubric needs a model judge to be usable.

Done signal:

- A human can evaluate a small checkpoint set using the protocol without asking
  what information is allowed.

### Task 9: Run First Practical Evaluation Manually And Summarize Findings

Outcome:

- The project has a first real answer to whether Engram context is useful on
  this corpus, with auditable evidence.

Files to touch:

- Local generated artifacts under `.engram-runs/<run-id>/`
- `docs/implementation/07-codex-corpus-validation.md` for a non-sensitive summary
- `docs/lessons.md` only if a durable repeated lesson appears
- A follow-up plan under `docs/plans/` only if the findings require new work

Read first:

- `docs/evaluation/codex-corpus-protocol.md`
- The mechanical report for the run being evaluated
- The manifest for the run being evaluated

Required process:

- Select 5 to 10 checkpoints that are relatively timeless.
- For each checkpoint, create or replay a prefix-only vault. Do not use a vault
  that contains future pairs.
- Save:
  - baseline prompt
  - treatment prompt
  - rendered context
  - baseline answer
  - treatment answer
  - oracle future turns
  - score and rationale
- Summarize aggregate findings:
  - helpful / neutral / harmful counts
  - repeated useful memory types
  - repeated missing memory types
  - repeated noise or stale-context patterns
  - recommendation: keep, tune, or defer

Tests:

- Manual evaluation is not a normal automated test.
- The implemented helpers used to produce checkpoint data must already be tested.

Stop and re-evaluate if:

- Most candidate checkpoints are stateful coding turns.
- Treatment answers are often worse because the context surface is too noisy.
- You cannot explain scores using oracle evidence.

Done signal:

- A short, non-sensitive findings summary exists and points to local generated
  artifacts for detailed audit.

### Task 10: Fold Findings Into The Roadmap

Outcome:

- The next engineering step is based on evidence, not architecture taste.

Files to touch:

- `docs/implementation/07-codex-corpus-validation.md`
- `docs/lessons.md` if needed
- a new follow-up plan if needed

Required decision rules:

- If mechanical validation fails, prioritize ingestion/runtime fixes.
- If mechanical validation passes but context is noisy, prioritize context
  selection or summary quality.
- If context-only treatment helps, do not immediately broaden to tool-rich
  retrieval. Keep the thesis surface narrow until the signal is stable.
- If context-only treatment is neutral but errors look like missing drill-down,
  plan a bounded phase-B retrieval evaluation.
- If the practical sample is too stateful, improve checkpoint selection before
  changing Engram.
- If manual repair becomes a real operational pain, write a separate plan for a
  maintenance loop. Do not smuggle heartbeat or persistent services into this
  plan.

Done signal:

- The repo records a clear keep/fix/defer conclusion.

## 9. Testing Plan

Parser tests:

- File: `tests/dogfood/test_codex_jsonl_parser.py`
- Must use real fixture files.
- Must prove eligible extraction, exclusion, grouping, incomplete-pair counting,
  malformed-line counting, and unsupported-format reporting.

Importer tests:

- File: `tests/dogfood/test_codex_replay.py`
- Must use real `Engram.init`, real SQLite, and real LanceDB.
- Must use temp directories for fake Codex roots and run dirs.
- Must prove fresh-vault refusal, manifest rows, moment text safety, id ordering,
  and source-to-memory mapping.

Mechanical validation tests:

- File: `tests/dogfood/test_codex_replay.py`
- Must use fixture corpus large enough to produce episodes and arcs.
- Must assert report fields and context snapshot files.
- Must assert no processing lag remains after local process for deterministic
  fixtures.

Practical protocol tests:

- If checkpoint export code exists, test it.
- If checkpoint export remains documentation-only for the first pass, verify by
  inspection and do not fake a weak automated test.

What should stay real:

- filesystem fixture reads
- manifest writes
- Engram vault lifecycle
- SQLite state store
- LanceDB index
- local repair processing
- context assembly

What may be deterministic shims in tests:

- Weft task submission, via existing autouse fixture
- sentence-transformer embeddings, via `DeterministicEmbedder`
- LLM summary generation, via existing deterministic summary shims

Runtime smoke commands:

```bash
./.venv/bin/python -m pytest tests/dogfood/test_codex_jsonl_parser.py -q
./.venv/bin/python -m pytest tests/dogfood/test_codex_replay.py -q
./.venv/bin/python -m pytest
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests docs README.md
```

Manual real-corpus smoke after automated tests pass:

```bash
./.venv/bin/python -m engram.dogfood.codex_replay inspect --root ~/.codex

./.venv/bin/python -m engram.dogfood.codex_replay mechanical \
    --root ~/.codex \
    --vault .engram-runs/codex-smoke/.engram \
    --run-dir .engram-runs/codex-smoke \
    --limit-pairs 200 \
    --snapshot-every 50 \
    --tokens 2048
```

## 10. Verification And Gates

Per-task gates:

- Task 1: lint passes.
- Task 2: parser tests fail for the intended missing behavior.
- Task 3: parser tests pass.
- Task 4: discovery/inspection tests pass and real inspect command reports
  supported and unsupported counts.
- Task 5: importer tests pass with real Engram vaults and manifests.
- Task 6: mechanical report tests pass and a small real run produces a report.
- Task 7: docs explain exact safe commands and artifact locations.
- Task 8: protocol clearly separates baseline, treatment, and oracle evidence.
- Task 9: first practical pass has auditable local artifacts and a non-sensitive
  summary.
- Task 10: follow-up direction is explicit.

Mechanical pass gate for real corpus:

- `imported_moments > 0`
- `indexed_items > 0`
- `failed_processing_items == 0`
- `items_needing_processing == 0` after local process
- `episode_count > 0` for small sample
- `arc_count > 0` for larger sample
- `context_snapshot_count > 0`
- parser skipped/unsupported counts are visible
- no developer/tool/reasoning content appears in sampled moment text

Practical pass gate:

- At least 5 checkpoints are evaluated.
- Every checkpoint has a baseline answer, treatment answer, rendered context,
  and oracle future turns.
- Every score cites concrete oracle evidence.
- The summary names at least one keep/fix/defer decision.

Final implementation gate:

```bash
./.venv/bin/python -m pytest
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests docs README.md
```

## 11. Independent Review Loop

Before implementation:

- Ask a separate reviewer or agent to read this plan and answer:

  > Read
  > `docs/plans/2026-04-21-codex-corpus-validation-implementation-plan.md`.
  > Carefully examine the plan and the associated specs, implementation notes,
  > and current code. Look for errors, bad ideas, and latent ambiguities. Do not
  > implement anything. Could you implement this confidently and correctly if
  > asked?

Reviewer should read:

- this plan
- `docs/plans/2026-04-18-codex-jsonl-corpus-validation-plan.md`
- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/12-local-app-surface.md`
- `docs/specs/13-context-assembly-and-arcs.md`
- `docs/specs/14-embedded-weft-execution-model.md`
- `engram/core/memory.py`
- `engram/store/sqlite.py`
- `engram/index/lance.py`
- `tests/conftest.py`

Review findings must be handled explicitly:

- fix the plan
- or state why the current plan is still better
- or mark the concern out of scope with reasoning

If the reviewer cannot implement confidently from the plan, that is a blocker.

## 12. Out Of Scope

- `forget`, `forget --all`, reset, tombstone, or deletion semantics
- source timestamp preservation in core Engram IDs
- source provenance columns in `memory_items`
- generic import/export product surface
- support for all possible historical Codex JSONL shapes
- live Codex sqlite import
- recovery artifact import
- `history.jsonl` import
- heartbeat or persistent maintenance loops
- public scheduler behavior
- LLM-as-judge scoring
- new dependencies
- optimizing runtime performance before correctness is proven

## 13. Fresh-Eyes Review Notes

Self-review checklist before implementation:

- Does the plan tell a zero-context engineer which files to read and why?
- Does it name the core boundaries that must not move?
- Does it avoid destructive reset and schema changes?
- Does it split parser, importer, mechanical proof, and practical proof?
- Does it avoid future leakage?
- Does it specify what not to mock?
- Does it give exact commands for tests and real smoke runs?
- Does it define stop-and-replan gates?
- Does it keep the work on the discussed path?

Author self-review result:

- The original 2026-04-18 plan used `archived_sessions` as the main corpus. That
  is too small for serious validation. This plan corrects that by using
  `~/.codex/sessions/**/*.jsonl` as the primary corpus and keeping
  `archived_sessions` for smoke fixtures.
- The plan deliberately does not add reset/forget. Fresh vaults are safer and
  more reproducible.
- The plan deliberately does not preserve original source timestamps in Engram
  IDs. Replay order is enough for the first validation, while source timestamps
  remain auditable in the manifest.
- The plan keeps practical evaluation manual at first. Automating subjective
  scoring or adding a skill now would be premature.
- The plan remains aligned with the discussed direction: temporal replay,
  periodic context snapshots, then usefulness judgment against future turns.
