# 2026-04-22 Engram Foundation Excellence Plan

Status: Implemented on 2026-04-22

## 1. Goal

Bring Engram's foundation to the same dedicated engineering standard as Weft:
clear current contracts, executable architecture guardrails, shared public
surfaces, real behavior tests, and documentation that makes the right path hard
to miss. This plan does not add new memory features. It hardens the foundation
so future memory work naturally extends the existing SQLite/Lance/Weft spine
instead of creating parallel paths.

## 2. Source Documents

Source specs:

- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-3], [MM-6],
  [MM-12], [MM-15], [MM-19], [MM-21]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1],
  [MWS-5], [MWS-12], [MWS-18], [MWS-19], [MWS-20], [MWS-23],
  [MWS-27], [MWS-28]
- `docs/specs/12-local-app-surface.md` [LAS-8], [LAS-12], [LAS-17],
  [LAS-19], [LAS-20], [LAS-21], [LAS-29], [LAS-30]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5],
  [CAA-8], [CAA-9], [CAA-11]
- `docs/specs/14-embedded-weft-execution-model.md` [EWM-1],
  [EWM-16], [EWM-18], [EWM-20], [EWM-22]

Implementation docs:

- `docs/implementation/02-repository-map.md`
- `docs/implementation/04-minimum-memory-slice.md`
- `docs/implementation/05-local-vault-recovery.md`
- `docs/implementation/06-arc-context-assembly.md`
- `docs/implementation/07-codex-corpus-validation.md`

Existing plans to preserve or align with:

- `docs/plans/2026-04-18-memory-benchmark-harness-plan.md`
- `docs/plans/2026-04-21-codex-corpus-validation-implementation-plan.md`

Repository workflow guidance:

- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/lessons.md`

Read-only calibration from the sibling Weft repository. Do not copy code. Use
these only as examples of engineering posture:

- `../weft/weft/client/_client.py`: thin client over shared command layer
- `../weft/tests/architecture/test_import_boundaries.py`: executable layering
  guardrails
- `../weft/docs/specifications/07-System_Invariants.md`: current-state
  invariants with implementation mappings
- `../weft/docs/specifications/11-CLI_Architecture_Crosswalk.md`: command
  ownership map
- `../weft/tests/helpers/weft_harness.py`: real process/broker test cleanup
  discipline

## 3. Audience Assumptions

Assume the implementer is technically skilled but has zero Engram context,
does not know the local tooling, and has questionable taste. In particular,
assume they will:

- over-abstract unless the plan says which path to reuse
- over-mock unless the plan says what must stay real
- change public names unless the compatibility rules are explicit
- treat docs as cleanup unless the task names docs as part of done
- split behavior between CLI, client, and tests unless the command layer is
  named as the owner

This plan must therefore be followed literally. If an implementation step seems
to need a different direction, stop and re-plan instead of improvising.

## 4. Excellence Criteria

Engram is excellent at this foundation layer when these are true:

- A new user sees `EngramClient` as the default app/agent/tool Python surface
  and `Engram` as the lower-level domain object.
- A new implementer can identify the owner of a behavior before editing:
  domain behavior, command adaptation, client surface, CLI formatting, tool
  surface, background execution, storage, retrieval, or dogfood harness.
- CLI, client, LLM tools, and dogfood adapters do not reimplement the same
  operation in parallel. Shared behavior lives in `engram.commands` or below.
- Public surfaces have contract tests that assert exact return shape,
  compatibility behavior, and access-score mutation semantics.
- Context assembly, search, direct lookup, status, rebuild, repair, dogfood,
  and LLM tools have explicit access-score semantics.
- The central mental model remains intact: SQLite owns state, LanceDB owns
  retrieval, Weft owns deferred work, and tiers serve context assembly.
- Runtime wrappers do not reach into private `_store` or `_index` fields when
  an existing public or command-layer path can express the operation.
- Docs, specs, implementation notes, code docstrings, and tests form a
  navigable chain. Future agents should not have to rediscover the layer map.

## 5. Current Context And Key Files

Read these before editing. Do not infer behavior from filenames.

### Package Entry And Public Surfaces

- `engram/__init__.py`
  - Re-exports `Engram`, `EngramClient`, public models, and public errors.
  - Any new public error or model used by app code must be exported here.
- `engram/client.py`
  - Current `EngramClient` wraps an `Engram` and delegates to
    `engram.commands.memory`.
  - It currently exposes `record`, `context`, `search`, `lookup`, `status`,
    `process`, `snapshot`, `llm_tools`, and `close`.
  - It currently imports `Engram` and `EmbeddingModel` directly for types and
    construction. This plan tightens that to reduce runtime coupling.
- `engram/commands/memory.py`
  - Shared command-shaped operations for CLI, client, and tool adapters.
  - Owns argument normalization and JSON-safe serialization.
  - Must not invent domain behavior. It delegates to `Engram`.
- `engram/cli.py`
  - CLI parser and presentation layer.
  - It must delegate real behavior to `engram.commands.memory`.
  - It currently has mixed output formats. This plan adds additive JSON output
    without breaking default output.

### Domain, Background, Storage, Retrieval

- `engram/core/memory.py`
  - Low-level domain object. Owns write path, search, lookup, context assembly,
    pinning, status, rebuild, and shared processing operations.
  - It is allowed to touch SQLite and LanceDB through its store/index fields.
  - Do not split it into services in this plan unless a task explicitly says so.
- `engram/background.py`
  - Embedded Weft setup, submission, and worker entry points.
  - Current worker code opens `Engram` and calls `process_item_operation`, then
    records success through `memory._store`. This plan removes that private
    reach-in by reusing `Engram.repair_item`.
- `engram/store/sqlite.py`
  - Authoritative state store. Owns durable item content, access/relevance,
    parent-child edges, metadata, indexed state, and processing projections.
- `engram/index/lance.py`
  - Rebuildable retrieval projection. Owns FTS/vector search rows and index
    rebuild.

### Dogfood And Benchmark Path

- `engram/dogfood/codex_jsonl.py`
  - Parser-only module. It must remain read-only and should not import Engram
    runtime surfaces.
- `engram/dogfood/codex_replay.py`
  - Internal validation harness.
  - It currently imports `Engram` and uses low-level methods for replay,
    processing, status, and context snapshots.
  - Target rule: production dogfood and future benchmark code use
    `EngramClient` for ordinary app operations. Tests may inspect low-level
    state only when proving invariants that have no public inspection surface.

### Tests

- `tests/conftest.py`
  - Provides deterministic embeddings and summary shims.
  - These shims are allowed because external model calls are slow and
    nondeterministic. Do not mock SQLite, LanceDB, `Engram`, or command-layer
    behavior for foundation contracts.
- `tests/client/test_client.py`
  - Public client surface tests.
- `tests/commands/test_memory_commands.py`
  - Command-layer serialization and behavior tests.
- `tests/cli/test_cli.py`
  - CLI contract tests through `engram.cli.main`.
- `tests/core/test_memory.py`, `tests/core/test_context.py`
  - Low-level behavior and access-score invariants.
- `tests/dogfood/test_codex_replay.py`
  - Dogfood replay and artifact behavior.

### Comprehension Questions

Before editing, the implementer must be able to answer:

1. Which layer should app code call by default: `Engram` or `EngramClient`?
2. Where should a new command-like behavior live: CLI, client, command layer,
   or `Engram`?
3. Which operations are allowed to increment access scores by default?
4. Which model-facing operations must not increment access scores?
5. Which code paths are allowed to touch SQLite and LanceDB directly?
6. Why does `record()` return before indexing and coalescing complete?
7. Why is Weft the deferred execution substrate rather than an Engram queue?
8. What test would fail if a future dogfood adapter reaches into `_store`?
9. What test would fail if CLI `search --json` drifts from command-layer
   search result keys?
10. What would be a one-way door in this plan?

If any answer is uncertain, stop and read the source docs before coding.

## 6. Target Layering And Ownership

Target dependency direction:

```text
CLI adapter ------------------+
                              |
Python apps ---- EngramClient +---- engram.commands ---- Engram domain object
                              |                            |
LLM tools --------------------+                            +-- SQLite state
                                                           +-- LanceDB index
                                                           +-- Weft submission

Weft worker wrapper -------------------------------------> Engram.repair_item()

Dogfood / benchmark harness ----------------------------> EngramClient
```

Rules:

- `engram.core.*` must not import `engram.commands`, `engram.client`,
  `engram.cli`, or `engram.dogfood`.
- `engram.store.*` and `engram.index.*` must not import client, CLI, dogfood,
  commands, background, or benchmark code.
- `engram.commands` may import `Engram`, public models, public exceptions, and
  constants. It adapts arguments and return shapes. It must not own domain
  decisions.
- `EngramClient` delegates to `engram.commands`. It must not duplicate command
  logic.
- `EngramClient` may expose the wrapped low-level `memory` object only as an
  escape hatch for advanced users and tests. New app/dogfood code should not
  use `client.memory` to bypass command/client APIs.
- CLI delegates to `engram.commands`. CLI owns parsing, exit codes, and
  presentation only.
- LLM tools are built from `EngramClient` and are read-only by default.
- Dogfood and future benchmark code must use `EngramClient` for ordinary
  operations: init/open, record, context, search, lookup, status, process, and
  snapshot. If dogfood needs a shape not exposed by the client, add a narrow
  command/client method instead of reaching into `Engram`.
- Tests may inspect `_store` or `_index` only to prove invariants that are not
  visible through public surfaces, such as access score values or forced index
  drift. Production code must not do this.
- `engram.background` is a runtime wrapper. It may open `Engram`, but should
  call public domain methods like `repair_item()` rather than private `_store`
  or `_index` fields.

## 7. Public API Decisions

These decisions are part of the plan. Do not re-decide them during
implementation unless a spec conflict is found.

- `Engram` remains the low-level domain object.
- `EngramClient` is the recommended app, agent, tool, and benchmark-facing
  Python surface.
- `engram.commands` is the shared command/capability layer for CLI, client,
  tool, and dogfood adapters.
- `Engram.lookup(id, *, tier=None, count_access=True)` is the low-level direct
  lookup method.
- Move internal users from `Engram.get(...)` to `Engram.lookup(...)` in the
  same implementation step. Do not keep a `get()` compatibility alias; parallel
  compatibility paths hide bugs.
- Do not add `EngramClient.build_context()` in this plan. The client-facing
  method stays `EngramClient.context(query=None, *, max_tokens=...)`.
- Do not remove or rename existing public methods in this plan.
- Add `EngramClient` context-manager support. `with EngramClient.open(path) as
  client:` must close the client at exit.
- Client `close()` must be idempotent.
- After client close, client methods must raise a deliberate public
  `EngramClosedError`, not an incidental raw SQLite error. Add and export that
  error if it does not exist.
- Do not add context-manager support to low-level `Engram` in this plan. That
  can be considered later after the client contract is stable.

## 8. CLI Output Policy And JSON Schemas

Default CLI output must remain unchanged unless a separate migration plan says
otherwise.

Machine-readable output is additive. Use `--json` on commands where structured
output is useful. Do not replace existing default text output.

### CLI Defaults To Preserve

- `engram init`: prints vault path
- `engram record TEXT`: prints item id
- `engram search QUERY`: prints existing tab-separated rows
- `engram context`: prints rendered context text
- `engram moment|episode|arc ID`: prints JSON item object
- `engram pin ID RELEVANCE`: prints JSON item object
- `engram status`: prints pretty JSON status object
- `engram rebuild-index`: prints pretty JSON rebuild object
- `engram work once`: prints existing human summary

### Additive JSON Output Contracts

Add `--json` to these commands and test exact shapes:

- `engram init --json`
  - Object keys: `vault_path`
- `engram record TEXT --json`
  - Object keys: `id`
- `engram search QUERY --json`
  - JSON list. Each item must have exactly:
    `id`, `tier`, `text`, `source`, `fused_score`, `access`, `relevance`,
    `score`
  - The list must come from `engram.commands.memory.search`.
- `engram context --json`
  - Object keys: `context`, `term`, `total_tokens`
  - `context` is the rendered context string.
  - `term` is the CLI `--term` value or `null`.
  - `total_tokens` is the CLI `--tokens` value.
  - This may be a CLI presentation wrapper around command-layer context. Do
    not introduce a new domain context model just for this output.
- `engram moment|episode|arc ID --json`
  - Same object shape as the current default lookup output. Exact keys:
    `id`, `tier`, `text`, `created_at`, `access`, `relevance`, `indexed_at`,
    `summary_terms`
  - The default output is already JSON; `--json` exists for consistency.
- `engram pin ID RELEVANCE --json`
  - Same item shape as lookup.
- `engram status --json`
  - Same object shape as the current default status output. Exact keys come
    from `VaultStatus.model_dump(mode="json")`:
    `vault_path`, `sqlite_path`, `index_path`, `broker_path`,
    `schema_version`, `item_counts`, `indexed_items`, `index_rows`,
    `items_needing_processing`, `unindexed_items`, `failed_processing_items`,
    `failed_items`, `needs_rebuild`
- `engram rebuild-index --json`
  - Exact keys from `RebuildResult.model_dump(mode="json")`:
    `rebuilt_items`, `index_rows`, `indexed_at`
- `engram work once --json`
  - Exact keys:
    `processed_ids`, `created_episode_ids`, `created_arc_ids`,
    `failed_item_ids`, `processed_count`, `is_idle`

Error output does not need JSON in this plan. Preserve stable nonzero exit
codes for not-found and Engram errors.

## 9. Invariants And Constraints

Behavior invariants:

- SQLite remains authoritative for memory state.
- LanceDB remains rebuildable.
- Weft remains the deferred execution substrate.
- Engram must not introduce a second durable task queue.
- Moment IDs remain nanosecond timestamp integers and immutable.
- Moment text and creation timestamps remain immutable after storage.
- Coalescing remains additive. It may create summaries but must not delete or
  rewrite underlying moments.
- Search and direct low-level lookup count access by default.
- Command/client search and lookup count access by default unless explicitly
  called with `count_access=False`.
- Context assembly must not increment access.
- Status and rebuild inspection must not increment access. Rebuild may update
  `indexed_at` as already specified.
- LLM tools must not increment access by default.
- Dogfood context snapshots must not increment access.
- Pinned relevance must never be less than `1.0`.

Layering invariants:

- Shared behavior must flow through `engram.commands` or `Engram`; do not
  reimplement it in CLI, client, dogfood, or tests.
- Do not add public dependencies for architecture checks. Use `ast` or import
  inspection from the standard library.
- Do not add DTO/Pydantic models just to serialize command responses. Keep
  plain JSON dictionaries unless repeated schema drift creates evidence for a
  model.
- Do not move large chunks of `Engram` just to make the file smaller. Extract
  only when a task has a clear contract and behavior-preserving tests.
- Do not let tests assert only mock call counts for core behavior.
- Do not rely on private `_store` or `_index` in production code.

Compatibility invariants:

- Do not remove public methods.
- Do not rename public methods.
- Do not change default access-counting behavior.
- Do not change persisted IDs or storage schema in this plan.
- Do not change default CLI output except by adding optional `--json`.
- Do not make dogfood or benchmark artifacts public or committed unless
  explicitly curated.

Failure-priority rules:

- Data integrity failures are fatal.
- Invalid public input should fail clearly with public exceptions or stable CLI
  errors.
- Background submission failure must preserve the durable moment and record
  inspectable failure state.
- Snapshot path conflicts are fatal.
- Formatting or presentation helper failure must not silently mutate state.

One-way doors that are out of scope except for the explicit `get()` to
`lookup()` move in this plan:

- removing or renaming other public APIs
- changing persisted item IDs
- changing storage schema
- changing access-counting defaults
- replacing Weft as the execution substrate

## 10. Rollback And Sequencing

This work changes public contracts and shared paths, so every runtime change
must move all repo users to the canonical path in the same step.

Sequencing:

1. Update current contracts and docs before runtime changes.
2. Add failing contract and architecture tests before refactors.
3. Add command/client/CLI hardening while preserving default behavior.
4. Migrate dogfood and background wrappers to public/shared paths.
5. Add watchlists and review checklists only after the executable guardrails
   exist.

Rollback:

- Docs-only contract additions can be reverted independently before runtime
  implementation if review finds a bad direction.
- Contract tests should stay if they encode desired behavior.
- Runtime steps must be individually revertible because they are additive.
- If a step breaks existing CLI default output, revert that step and keep the
  old output until a migration plan exists.
- If a dogfood migration needs a client method that does not exist, add the
  narrow method and tests. Do not temporarily reach into `_store` or `_index`
  in production dogfood to finish the migration.
- If context-manager support introduces confusing lifecycle semantics, revert
  the context-manager task while keeping unrelated command/schema hardening.

Rollback does not require data migration because this plan must not change
storage schema or persisted IDs.

## 11. Tasks

### Phase 0 - Baseline And Contracts

1. Record the current baseline before changing code.
   - Outcome: the implementer knows whether failures are pre-existing.
   - Files to touch: none.
   - Read first:
     - `docs/agent-context/decision-hierarchy.md`
     - this plan
     - `pyproject.toml`
   - Commands:
     - `./.venv/bin/python -m pytest tests/client/test_client.py tests/commands/test_memory_commands.py tests/cli/test_cli.py tests/dogfood/test_codex_replay.py`
     - `./.venv/bin/mypy engram`
     - `./.venv/bin/ruff check engram tests docs README.md`
   - What must stay real:
     - SQLite temp vaults
     - LanceDB temp indexes
     - `Engram`
     - command layer
   - Stop if:
     - failures appear in unrelated areas and cannot be explained as
       pre-existing
     - `.venv` is missing; run `uv sync --all-extras` only after confirming the
       local setup expectation from `.envrc`
   - Done when:
     - baseline results are recorded in the implementation handoff or PR notes.

2. Add a current foundation contracts spec.
   - Outcome: Engram has a Weft-style current-state contract for layer
     ownership, public surfaces, access mutation, and command schema policy.
   - Files to touch:
     - `docs/specs/15-foundation-contracts-and-invariants.md` (new)
     - `docs/specs/00-specs-index.md`
     - `docs/specs/12-local-app-surface.md`
     - `docs/specs/11-minimum-write-search-context-slice.md` only if a public
       surface reference must link to the new spec
   - Read first:
     - `../weft/docs/specifications/07-System_Invariants.md` for structure
       only
     - `docs/specs/10-minimum-memory-model.md`
     - `docs/specs/11-minimum-write-search-context-slice.md`
     - `docs/specs/12-local-app-surface.md`
     - `docs/specs/14-embedded-weft-execution-model.md`
   - Required content:
     - current-state only, not planned wishes
     - implementation mapping table for each contract family
     - layer ownership rules from this plan
     - public API role split: `Engram`, `EngramClient`, `engram.commands`,
       CLI, LLM tools, dogfood
     - access-score mutation table
     - CLI JSON schema table from section 8
     - test enforcement map
   - Do not:
     - define benchmark-only behavior
     - define deletion, blobs, Postgres, or hosted behavior
     - duplicate full text from existing specs
   - Red-green posture:
     - docs-only task. Runtime red-green is not applicable.
   - Verification:
     - inspect links and requirement IDs manually
     - `rg -n "15-foundation|foundation contracts|EngramClient|access-score" docs/specs README.md docs/implementation`
   - Stop if:
     - the new spec starts changing behavior rather than documenting current
       contracts and the explicit additive contracts in this plan.
   - Done when:
     - a zero-context reader can answer the comprehension questions in section
       5 from specs and implementation docs.

3. Update public surface docs and examples.
   - Outcome: README and implementation docs point users to the right surface.
   - Files to touch:
     - `README.md`
     - `docs/implementation/04-minimum-memory-slice.md`
     - `docs/implementation/02-repository-map.md`
     - `docs/implementation/00-implementation-index.md` only if this task
       creates a new implementation note
   - Read first:
     - `README.md` Quick Start and Python API sections
     - `docs/implementation/04-minimum-memory-slice.md`
     - `docs/implementation/02-repository-map.md`
   - Required content:
     - first Python API example uses `EngramClient` for app/tool use
     - a smaller low-level example shows `Engram` for domain/library use
     - public API naming matrix:
       - CLI `engram record` -> `EngramClient.record()` ->
         `engram.commands.memory.record()` -> `Engram.record()`
       - CLI `engram search` -> `EngramClient.search()` ->
         `commands.search()` -> `Engram.search()`
       - CLI `engram context` -> `EngramClient.context()` ->
         `commands.context()` -> `Engram.build_context()`
       - CLI `engram moment|episode|arc` -> `EngramClient.lookup()` ->
         `commands.lookup()` -> `Engram.lookup()` / tier helpers
       - CLI `engram status` -> `EngramClient.status()` ->
         `commands.status()` -> `Engram.status()`
       - CLI `engram rebuild-index` -> command layer -> `Engram.rebuild_index()`
       - CLI `engram work once` -> `commands.work_once()` ->
         `Engram.work_once()`
       - client `process()` -> `commands.process()` -> `Engram.work_until_idle()`
     - repository map includes `engram/client.py`, `engram/commands/`, and
       `tests/architecture/` once the architecture tests are added
   - Do not:
     - turn README into an internals manual
     - imply `EngramClient.build_context()` exists
   - Red-green posture:
     - docs-only task. Use inspection and grep.
   - Verification:
     - `rg -n "EngramClient|Engram\\.lookup|build_context|command layer|commands" README.md docs/implementation`
   - Stop if:
     - examples present two names to the same audience without explaining why.
   - Done when:
     - the first README Python example makes the recommended path obvious.

### Phase 1 - Tests Before Refactor

4. Add executable import-boundary tests.
   - Outcome: layer ownership is enforced like Weft's architecture tests.
   - Files to touch:
     - `tests/architecture/test_import_boundaries.py` (new)
     - `tests/architecture/__init__.py` if needed
   - Read first:
     - `../weft/tests/architecture/test_import_boundaries.py` for pattern only
     - `engram/client.py`
     - `engram/cli.py`
     - `engram/background.py`
     - `engram/dogfood/codex_replay.py`
   - Test rules:
     - `engram.core.*` must not import `engram.commands`, `engram.client`,
       `engram.cli`, or `engram.dogfood`.
     - `engram.store.*` and `engram.index.*` must not import
       `engram.commands`, `engram.client`, `engram.cli`, `engram.background`,
       or `engram.dogfood`.
     - `engram.commands.*` must not import `engram.cli`, `engram.client`, or
       `engram.dogfood`.
     - `engram.cli.*` must not import `engram.core.*` at runtime. If it needs
       an `Engram` type, use `TYPE_CHECKING` or remove the annotation.
     - `engram.client.*` must not import `engram.core.*` at runtime except for
       documented temporary type-only imports. Prefer `TYPE_CHECKING` and
       string annotations.
     - `engram.dogfood.*` must not import `engram.store.*`, `engram.index.*`,
       or private core internals. It should import `EngramClient` for memory
       operations after the dogfood migration task.
     - `engram.background` may import `engram.core.memory.Engram` and
       `engram.store.sqlite.SQLiteStateStore` because it is the Weft worker
       boundary, but tests should flag direct `_store` or `_index` attribute
       access in production code outside `engram.core.memory`.
   - Implementation guidance:
     - use the standard-library `ast` module
     - print violations as `path:line source -> target`
     - ignore imports under `if TYPE_CHECKING:` if the helper can do so
       simply; otherwise allow those exact type-only imports by module name and
       document the allowance in the test
   - Red-green posture:
     - write the tests first
     - they may fail on current `engram.cli`, `engram.client`,
       `engram.background`, and `engram.dogfood`
     - fix failures in later tasks, not by weakening the tests without review
   - What must stay real:
     - source files and AST inspection
   - What may be mocked:
     - nothing; this is static inspection
   - Verification:
     - `./.venv/bin/python -m pytest tests/architecture/test_import_boundaries.py`
   - Stop if:
     - satisfying the test requires a new dependency
     - the test grows into a general linter instead of enforcing the named
       Engram boundaries
   - Done when:
     - violations are precise enough for a future implementer to fix without
       reading the test code.

5. Add command return-shape contract tests.
   - Outcome: command-layer JSON shapes are locked before serializers move.
   - Files to touch:
     - `tests/commands/test_memory_commands.py`
   - Read first:
     - `engram/commands/memory.py`
     - `engram/_models.py`
     - `tests/commands/test_memory_commands.py`
   - Tests to add:
     - `commands.search(..., count_access=False)` returns a non-empty list with
       exact keys:
       `id`, `tier`, `text`, `source`, `fused_score`, `access`, `relevance`,
       `score`
     - `commands.lookup(..., count_access=False)` returns exact keys:
       `id`, `tier`, `text`, `created_at`, `access`, `relevance`, `indexed_at`,
       `summary_terms`
     - `commands.work_once()` and `commands.process()` return exact keys:
       `processed_ids`, `created_episode_ids`, `created_arc_ids`,
       `failed_item_ids`, `processed_count`, `is_idle`
     - `commands.status()` returns the exact status keys named in section 8
     - `commands.rebuild_index()` returns exact rebuild keys named in section 8
     - returned values are `json.dumps(...)` safe
   - Red-green posture:
     - add tests before centralizing serializers
     - if tests pass immediately, keep them as contract locks and still
       centralize serializer helpers only if needed by implementation
   - What must stay real:
     - SQLite
     - LanceDB
     - `Engram`
     - command layer
   - What may be mocked:
     - Weft submission through existing autouse shim
     - LLM summarization through existing deterministic shim
     - deterministic embeddings through existing fixture
   - Verification:
     - `./.venv/bin/python -m pytest tests/commands/test_memory_commands.py`
   - Stop if:
     - tests require private store/index access except to verify access-score
       invariants
     - tests assert mock call counts instead of returned shape and durable state
   - Done when:
     - exact key drift fails in a focused command test.

6. Add public surface parity and access semantics tests.
   - Outcome: client, command, CLI, and tool surfaces prove shared behavior and
     access rules with real dependencies.
   - Files to touch:
     - `tests/client/test_client.py`
     - `tests/cli/test_cli.py`
     - `tests/core/test_context.py` only if a low-level access invariant is
       missing
   - Read first:
     - `engram/client.py`
     - `engram/cli.py`
     - `engram/commands/memory.py`
     - existing tests in the files above
   - Tests to add:
     - `EngramClient` return shapes match command-layer return shapes for
       context, search, lookup, status, and process.
     - For mutating operations like `record`, prove parity by observable
       state: client record returns an int id, command lookup can find it,
       process processes it, and search finds it. Do not call client and command
       record on the same assertion and expect identical ids.
     - `EngramClient.llm_tools()` context/search/lookup are JSON-safe and do
       not increment access.
     - `EngramClient.status()` and `EngramClient.process()` do not increment
       access beyond the explicit retrieval or processing semantics already
       expected.
     - CLI default output remains unchanged for representative commands.
     - CLI `--json` output matches the schemas in section 8 for search,
       context, lookup, status, rebuild, and work.
     - Not-found tier lookup still returns the stable not-found exit code.
   - Red-green posture:
     - write the `--json` CLI tests first; they should fail until CLI support
       is implemented
     - write missing access tests before changing tool/client behavior
   - What must stay real:
     - CLI `main(...)`
     - SQLite
     - LanceDB
     - command layer
     - client layer
   - What may be mocked:
     - external LLM calls through existing summary shim
     - Weft task submission through existing shim
   - Verification:
     - `./.venv/bin/python -m pytest tests/client/test_client.py tests/cli/test_cli.py`
   - Stop if:
     - tests bypass public surfaces and recreate behavior locally
     - tests depend on exact nanosecond IDs except where returned by the
       operation under test
   - Done when:
     - a change to client/CLI access behavior or JSON shape fails a focused
       test.

### Phase 2 - Command, Client, And CLI Hardening

7. Centralize command serializers and normalize command errors.
   - Outcome: command return shapes are produced in one place and errors are
     consistent across client/tool/CLI adapters.
   - Files to touch:
     - `engram/commands/memory.py`
     - `tests/commands/test_memory_commands.py`
   - Read first:
     - command tests from tasks 5 and 6
     - `engram/_models.py`
     - `engram/_exceptions.py`
   - Required implementation:
     - keep plain JSON dictionaries
     - keep `_memory_item_to_dict`, `_search_result_to_dict`, and
       `_work_result_to_dict` or rename them to clearer serializer helpers
     - add a small context JSON helper only if needed for CLI `context --json`
       and do not create a parallel model layer
     - invalid item ID string raises `ValueError`
     - missing lookup returns `None` for command/client/tool surfaces
     - snapshot target same-as-source, inside-source, and non-empty target are
       fatal errors
   - Do not:
     - add Pydantic DTOs for command return values
     - catch broad exceptions and return `None`
     - change default access counting
   - Red-green posture:
     - run command tests before editing and after each serializer/error change
   - Verification:
     - `./.venv/bin/python -m pytest tests/commands/test_memory_commands.py`
   - Stop if:
     - command behavior starts differing between CLI and client without a
       presentation-only reason
   - Done when:
     - command shape and error tests pass without private-store assertions.

8. Move the low-level direct lookup API to `Engram.lookup()`.
   - Outcome: low-level API aligns with CLI/client lookup language without a
     backwards-compatibility alias.
   - Files to touch:
     - `engram/core/memory.py`
     - `tests/core/test_memory.py`
     - `README.md`
     - `docs/implementation/04-minimum-memory-slice.md`
   - Read first:
     - the current low-level direct lookup method
     - `Engram.moment`, `Engram.episode`, `Engram.arc`
     - public API naming matrix from task 3
   - Required implementation:
     - add `Engram.lookup(self, item_id: int, *, tier: int | None = None,
       count_access: bool = True) -> MemoryItem`
     - move the current lookup behavior into that method
     - update internal users and tests from `Engram.get(...)` to
       `Engram.lookup(...)`
     - remove the public `Engram.get(...)` method instead of keeping it as a
       compatibility alias
     - docstring references the foundation contracts spec
     - no `EngramClient.build_context()` alias
   - Tests:
     - lookup returns the stored item with `count_access=False`
     - lookup increments access by default
     - tier mismatch raises `MemoryItemNotFoundError`
   - Red-green posture:
     - add/update tests first; they should fail before the API move
   - Verification:
     - `./.venv/bin/python -m pytest tests/core/test_memory.py tests/client/test_client.py`
   - Stop if:
     - a `get()` compatibility shim appears
     - the change creates two direct lookup implementations
   - Done when:
     - README examples and tests use the chosen names consistently.

9. Add explicit `EngramClient` lifecycle behavior.
   - Outcome: client context-manager support is deliberate and testable.
   - Files to touch:
     - `engram/client.py`
     - `engram/_exceptions.py`
     - `engram/__init__.py`
     - `tests/client/test_client.py`
     - `README.md` if examples need context-manager usage
   - Read first:
     - `EngramClient.close`
     - `engram/_exceptions.py`
     - existing client tests
   - Required implementation:
     - add `EngramClosedError(EngramError, RuntimeError)`
     - export `EngramClosedError` from package root
     - add `EngramClient.__enter__` returning `self`
     - add `EngramClient.__exit__` calling `close()`
     - make `close()` idempotent
     - guard public client methods so calls after close raise
       `EngramClosedError`
   - Do not:
     - add low-level `Engram` context-manager support in this plan
     - rely on raw SQLite closed-handle errors as public behavior
   - Tests:
     - `with EngramClient.open(path) as client:` can run a lookup/context call
       and then closes on exit
     - calling `close()` twice does not fail
     - calling `search`, `lookup`, `context`, `status`, `process`, or
       `llm_tools` after close raises `EngramClosedError`
     - initialization/open errors still propagate and are not hidden by context
       manager behavior
   - Red-green posture:
     - add tests first; closed-client tests should fail before implementation
   - Verification:
     - `./.venv/bin/python -m pytest tests/client/test_client.py`
     - `./.venv/bin/mypy engram`
   - Stop if:
     - closed-state checks spread into low-level `Engram`
     - lifecycle behavior hides open/init failures
   - Done when:
     - client lifecycle has one public error path and no raw SQLite leakage.

10. Implement additive CLI JSON output.
    - Outcome: CLI becomes predictable for scripts without breaking default
      output.
    - Files to touch:
      - `engram/cli.py`
      - `tests/cli/test_cli.py`
      - `README.md`
      - `docs/implementation/04-minimum-memory-slice.md`
    - Read first:
      - section 8 of this plan
      - `engram/commands/memory.py`
      - current CLI tests
    - Required implementation:
      - add `--json` where section 8 requires it
      - preserve default output exactly enough for existing tests to pass
      - use command-layer return values for search, lookup, pin, status,
        rebuild, and work
      - use a small CLI wrapper for context JSON only if command layer still
        returns rendered text
      - errors keep existing exit code behavior
    - Do not:
      - introduce `--format` and `--json`; choose `--json` only for this plan
      - refactor the whole CLI unless parser complexity blocks the task
      - bypass command layer for convenience
    - Red-green posture:
      - CLI JSON tests from task 6 should fail before implementation
    - Verification:
      - `./.venv/bin/python -m pytest tests/cli/test_cli.py`
      - `./.venv/bin/engram --help` if the console script is installed
      - `./.venv/bin/engram search --help`,
        `./.venv/bin/engram context --help`, and
        `./.venv/bin/engram work once --help` if the console script is
        installed
      - if the console script is not installed, inspect parser help with
        `./.venv/bin/python -c "from engram.cli import build_parser; print(build_parser().format_help())"`
    - Stop if:
      - parser changes alter positional argument behavior
      - default output changes without an explicit migration plan
    - Done when:
      - CLI default and JSON output tests both pass.

### Phase 3 - Runtime Boundary Cleanup

11. Route the Weft worker wrapper through public domain repair behavior.
    - Outcome: background workers no longer record processing success through
      private `memory._store` access.
    - Files to touch:
      - `engram/background.py`
      - `tests/test_background.py`
      - `tests/core/test_memory.py` only if a shared repair invariant is
        missing from the core tests
    - Read first:
      - `engram/background.py`
      - `Engram.process_item_operation`
      - `Engram.repair_item`
      - `docs/specs/14-embedded-weft-execution-model.md` [EWM-16], [EWM-18]
    - Required implementation:
      - in `process_memory_task`, call `memory.repair_item(item_id)` for the
        worker path
      - return the shared work-result payload keys:
        `processed_ids`, `created_episode_ids`, `created_arc_ids`,
        `failed_item_ids`, `processed_count`, `is_idle`
      - avoid direct `memory._store` access in production background code
      - avoid double-recording failures if `repair_item` already recorded one
      - keep `_mark_failed` only for failures where an `Engram` handle could
        not run `repair_item`, or remove it if tests prove it is unnecessary
    - Tests:
      - background task success records processing success
      - background task failure records enough status to inspect the failed
        item
      - worker result payload shape matches the shared work-result shape
      - import-boundary/private-access test fails if `_store` is used from
        `engram.background`
   - Red-green posture:
     - add or tighten tests first
    - Verification:
      - `./.venv/bin/python -m pytest tests/test_background.py tests/core/test_memory.py tests/architecture/test_import_boundaries.py`
    - Stop if:
      - implementation starts duplicating `repair_item` success/failure logic
      - a second task queue or processing state machine appears
    - Done when:
      - Weft worker and local repair share the same domain operation and status
        recording path.

12. Migrate production dogfood replay to `EngramClient`.
    - Outcome: dogfood follows the same public app surface future benchmarks
      should use.
    - Files to touch:
      - `engram/dogfood/codex_replay.py`
      - `tests/dogfood/test_codex_replay.py`
      - `docs/implementation/07-codex-corpus-validation.md`
      - `docs/implementation/04-minimum-memory-slice.md` if the boundary note
        needs updating
    - Read first:
      - `engram/client.py`
      - `engram/dogfood/codex_replay.py`
      - `tests/dogfood/test_codex_replay.py`
      - `docs/implementation/07-codex-corpus-validation.md`
    - Required implementation:
      - import `EngramClient` for replay memory operations
      - use `EngramClient.init/open`, `record`, `process`, `context`,
        `status`, and `snapshot` where applicable
      - if dogfood needs structured status as attributes, adapt it to the
        command/client dictionary shape instead of reopening low-level
        `Engram`
      - context snapshots must use client context and must not increment access
      - production dogfood code must not use `client.memory._store` or
        `client.memory._index`
    - Tests:
      - existing mechanical validation tests still pass
      - access scores do not change when context snapshots are written
      - architecture test catches production dogfood imports of storage/index
        internals
   - Red-green posture:
     - add architecture guardrails first; migrate code until they pass
    - Verification:
      - `./.venv/bin/python -m pytest tests/dogfood/test_codex_replay.py tests/architecture/test_import_boundaries.py`
    - Stop if:
      - migration requires adding benchmark-only behavior to local-app specs
      - implementation needs broad client APIs that are only useful for one
        dogfood path
    - Done when:
      - dogfood proves the public app surface is sufficient for validation
        harnesses.

### Phase 4 - Guardrails Against Future Drift

13. Add an Engram foundation review checklist.
    - Outcome: future reviews ask the same layer and access-score questions by
      default.
   - Files to touch:
     - `docs/agent-context/engineering-principles.md`
      - `docs/implementation/08-foundation-review-checklist.md` only if adding
        the checklist to engineering principles would make that file too long
      - `docs/implementation/00-implementation-index.md` only if a new
        implementation note is created
    - Read first:
      - `docs/agent-context/engineering-principles.md`
      - `../weft/docs/specifications/11-CLI_Architecture_Crosswalk.md` for
        checklist style only
    - Required checklist questions:
      - Which layer owns this behavior?
      - Is there already a command-layer path?
      - Does this mutate access scores?
      - Does this cross SQLite, LanceDB, or Weft ownership?
      - Does this need CLI, client, tool, and dogfood parity?
      - What must stay real in tests?
      - Which public shape or error contract could drift?
      - Is this current behavior or a planned idea?
    - Do not:
      - duplicate the whole plan
      - add vague slogans without operational checks
    - Verification:
      - docs inspection
      - `rg -n "Which layer owns|access scores|command-layer" docs/agent-context docs/implementation`
    - Stop if:
      - the checklist is too long to use during reviews
    - Done when:
      - a reviewer can use the checklist in under two minutes.

14. Add a no-god-object regression watchlist without premature extraction.
    - Outcome: `Engram` remains intentionally large until a seam earns
      extraction, but future drift is easier to catch.
    - Files to touch:
      - `docs/implementation/04-minimum-memory-slice.md`
      - `docs/lessons.md` only if implementation uncovers a repeated failure
        mode not already documented
    - Read first:
      - `engram/core/memory.py`
      - `docs/implementation/04-minimum-memory-slice.md`
      - this plan's layering rules
    - Required watchlist:
      - a new public command is added only to `Engram`
      - CLI bypasses `engram.commands`
      - client duplicates command serialization
      - dogfood reaches into `_store` or `_index`
      - background path duplicates local repair logic
      - context assembly starts incrementing access
      - status or docs start describing planned behavior as current
    - Do not:
      - extract services from `Engram` in this task
      - add line-count thresholds
    - Verification:
      - docs inspection
      - architecture tests from task 4
    - Stop if:
      - watchlist turns into a vague aspiration rather than concrete bad
        patterns
    - Done when:
      - implementation docs say where new behavior belongs and what patterns
        are forbidden.

15. Optional only if blocked: extract one seam from `Engram`.
    - Outcome: no extraction happens unless previous tasks expose a concrete
      blockage.
    - Files to touch only if needed:
      - `engram/core/memory.py`
      - one new module under `engram/core/` with a narrow name and contract
      - targeted tests for the extracted behavior
      - relevant implementation doc
    - Candidate seams:
      - lifecycle/status/rebuild orchestration
      - retrieval orchestration
      - context assembly orchestration
      - coalescing orchestration
    - Default decision:
      - do not extract in this plan.
    - If extraction becomes necessary:
      - write behavior-preserving tests first
      - move one seam only
      - do not change behavior and structure in the same step
      - keep public methods on `Engram`
      - keep SQLite/Lance ownership unchanged
    - Verification if extraction occurs:
      - targeted tests for the seam before and after
      - full final gate
      - independent review focused on behavior preservation
    - Stop if:
      - extraction is motivated by file size rather than a proven contract seam
      - extraction creates a second execution path
    - Done when:
      - either no extraction happened and the watchlist explains why, or one
        seam moved with identical behavior.

## 12. Testing Plan

Use real behavior wherever the contract under review is local and deterministic.

Must stay real:

- SQLite temp vaults
- LanceDB temp indexes
- `Engram`
- `EngramClient`
- `engram.commands`
- CLI `main(...)`
- dogfood replay code for replay tests
- background worker wrapper for background tests

Allowed shims or mocks:

- Weft task submission in unit tests, using the existing autouse shim
- LLM summarization, using the existing deterministic summary shim
- deterministic embeddings in tests
- direct private `_store` or `_index` access only in tests that prove
  invariants not exposed publicly, such as access counts or forced index drift

Not allowed as primary proof:

- mock call counts for command/client/CLI behavior
- tests that recreate command behavior locally instead of calling the command
  layer
- tests that mock SQLite or LanceDB for public foundation contracts
- tests that assert only that a function was called but not returned shape,
  durable state, access score, or CLI output

Required test families:

- architecture/import-boundary tests
- command return-shape tests
- client/command parity tests
- CLI default output and `--json` output tests
- access-score mutation tests for explicit retrieval, context assembly, status,
  tools, and dogfood snapshots
- background worker and local repair shared-path tests
- dogfood replay tests using `EngramClient`

Red-green TDD guidance:

- Write architecture tests before moving imports.
- Write command schema tests before changing serializers.
- Write CLI `--json` tests before adding parser flags.
- Write closed-client tests before adding lifecycle state.
- Write background worker tests before removing private `_store` writes.
- Write dogfood boundary tests before migrating replay code.

## 13. Verification And Gates

Per-task verification is listed on each task. Do not skip it.

Final gate before claiming done:

```bash
./.venv/bin/python -m pytest
./.venv/bin/mypy engram
./.venv/bin/ruff check engram tests docs README.md
```

Manual gates:

- Run `./.venv/bin/python -m pytest tests/architecture/test_import_boundaries.py`
  and inspect any failure message for useful file/line output.
- Run `./.venv/bin/engram --help` from the in-repo environment if the console
  script is installed.
- Run key subcommand helps after CLI changes if the console script is
  installed: `search`, `context`, `work once`, `status`, and `rebuild-index`.
- If the console script is not installed, inspect parser help with
  `./.venv/bin/python -c "from engram.cli import build_parser; print(build_parser().format_help())"`.
- Read README Quick Start as a new user and confirm `EngramClient` is the
  first app/tool path.
- Confirm no production code outside `engram/core/memory.py` touches `_store`
  or `_index`.
- Confirm `rg -n "Engram\\.open|Engram\\.init|_store|_index" engram/dogfood`
  does not show production dogfood bypassing the client, except parser-only
  code that does not open memory.
- Confirm `rg -n "count_access=False" engram/client.py engram/dogfood` shows
  tool and snapshot paths that must remain read-only.

Expected post-implementation signals:

- `pytest` passes with real SQLite and LanceDB behavior.
- `mypy` passes with no new ignores.
- `ruff` passes with no broad exclusions.
- CLI default-output tests pass alongside JSON-output tests.
- Architecture test prevents the most likely future drift.

## 14. Independent Review Loop

This plan is non-trivial and touches public contracts. Independent review is
required before broad implementation and again after any optional extraction.

Plan review prompt:

> Read `docs/plans/2026-04-22-engram-foundation-excellence-plan.md`.
> Carefully examine the plan and the associated code. Look for errors, bad
> ideas, and latent ambiguities. Do not implement anything. Answer directly:
> could you implement this confidently and correctly if asked? If not, name the
> blocker and the smallest plan change that would fix it.

Reviewer materials:

- this plan
- `docs/specs/10-minimum-memory-model.md`
- `docs/specs/11-minimum-write-search-context-slice.md`
- `docs/specs/12-local-app-surface.md`
- `docs/specs/14-embedded-weft-execution-model.md`
- `engram/core/memory.py`
- `engram/commands/memory.py`
- `engram/client.py`
- `engram/cli.py`
- `engram/background.py`
- `engram/dogfood/codex_replay.py`
- relevant tests

Review after Phase 1 must focus on:

- Are public surface roles crisp?
- Are architecture tests enforcing the right boundaries?
- Are command return shapes precise enough?
- Are the tests still using real SQLite and LanceDB?
- Is the plan over-abstracting before evidence?

Review after any optional extraction must focus on:

- Did behavior stay identical?
- Did the extraction reduce cognitive load, or only move code around?
- Did the extraction preserve public methods and storage ownership?

The implementer must either update the plan, explain why current direction is
still correct, or mark feedback out of scope with reasoning before continuing.

## 15. Out Of Scope

- New memory features.
- Benchmark harness implementation beyond using clarified public surfaces.
- Postgres backend.
- Blob ingestion.
- Deletion or forget semantics.
- Import/export, except existing dogfood artifacts.
- Changing persisted storage schema.
- Changing default access-counting semantics.
- Rewriting `Engram` wholesale.
- Adding public dependencies for API or architecture checks.
- Adding a scheduler, queue, or background substrate besides Weft.
- Provider setup, login, or hosted service behavior.

## 16. Fresh-Eyes Review Checklist

Before implementation starts, re-read the plan as if you have never seen
Engram. You should be able to answer:

1. Which files must be read before touching public APIs?
2. Which layer owns CLI behavior versus domain behavior?
3. What exact JSON keys should `engram search --json` emit?
4. What exact JSON keys should command lookup emit?
5. Which operations are allowed to mutate access scores?
6. Which tests must use real SQLite and LanceDB?
7. Which private-field uses are allowed only in tests?
8. How does dogfood avoid becoming a private second API?
9. How does the Weft worker avoid duplicating local repair logic?
10. What is the rollback path if CLI JSON support breaks default output?

If any answer is missing or ambiguous, revise the plan before coding.

## 17. Author Fresh-Eyes Notes

This rewrite fixes the known ambiguities in the earlier draft:

- Dogfood now has a clear rule: production dogfood uses `EngramClient`; tests
  may inspect low-level internals only for invariant proof.
- `Engram.lookup` now includes `tier`, and the plan moves users off
  `Engram.get` rather than adding a compatibility alias.
- CLI JSON output has exact schemas instead of a vague "add JSON" request.
- Client context-manager behavior has a deliberate `EngramClosedError`
  contract instead of relying on incidental SQLite errors.
- Background worker cleanup is explicit: call `repair_item()` rather than
  writing through `memory._store`.
- Architecture tests have concrete rules and allowable boundaries.
- Each implementation task names files, tests, real dependencies, allowed
  shims, stop gates, and done signals.

The plan remains aligned with the original goal. It does not add new memory
capabilities. It raises the engineering floor around the existing foundation.
