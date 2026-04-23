# Foundation Contracts And Invariants

Status: Active

This spec defines Engram's current foundation contracts: layer ownership,
public surface roles, access-score mutation rules, command output shapes, and
test guardrails. It does not add new memory capability.

## 1. Purpose and Scope

This spec governs the engineering foundation that keeps Engram's local app
surfaces aligned.

In scope:

- layer ownership
- public Python API roles
- command-layer ownership
- CLI structured-output contracts
- current storage-shape contracts
- access-score mutation semantics
- dogfood and background boundaries
- executable guardrails for architecture drift

Out of scope:

- deletion or forget semantics
- blob ingestion
- Postgres behavior
- hosted service behavior
- benchmark harness implementation beyond public-surface use

## 2. Mental Model

Engram has one domain object and several adapters.

`Engram` is the low-level domain object. It owns durable memory behavior,
state-store interaction, retrieval-index interaction, context assembly,
importance updates, vault status, vault rebuild, and local item-processing
operations.

`engram.commands` is the shared command layer. It owns argument normalization
and JSON-safe return shapes for CLI, client, model-facing tools, and dogfood
adapters. It must delegate domain behavior to `Engram`.

`EngramClient` is the default application, agent, tool, and validation-harness
Python surface. It is a thin wrapper over `engram.commands`.

The CLI owns parsing, exit codes, and presentation. It must not reimplement
domain behavior or command serialization.

`engram.runtime.weft` owns embedded Weft project initialization and internal
task submission. It is a narrow runtime integration boundary, not a domain
owner.

`engram.background` is the Weft worker callback adapter. It may open `Engram`
inside a worker process and call domain methods, but it must not own storage,
indexing, or task-submission setup.

Dogfood and future benchmark code use `EngramClient` for ordinary app
operations. Tests may inspect low-level internals only when proving invariants
that have no public inspection surface.

## 3. Requirements

### Layer Ownership

- [FCI-1] `engram.core.*` must not import CLI, client, command, dogfood, or
  worker-adapter layers. It may call the narrow `engram.runtime.weft` boundary
  for embedded Weft bootstrap/submission.
- [FCI-2] `engram.store.*` and `engram.index.*` must not import CLI, client,
  command, background, dogfood, or benchmark layers.
- [FCI-3] `engram.commands` may import `Engram`, public models, public
  exceptions, and constants. It must not import CLI, client, or dogfood code.
- [FCI-4] `engram.cli` must delegate behavior to `engram.commands` and own
  only parsing, presentation, and exit-code mapping.
- [FCI-5] `EngramClient` must delegate command-shaped behavior to
  `engram.commands`.
- [FCI-6] Production dogfood code must not access `client.memory._store`,
  `client.memory._index`, or storage/index modules.
- [FCI-7] `engram.background` may open `Engram` at the Weft worker boundary,
  but it must use public/domain methods such as `repair_item()` and
  `record_processing_failure_for_vault()` instead of private `_store`,
  `_index`, or storage modules.
- [FCI-7a] `engram.runtime.weft` may import Weft and Engram internal TaskSpec
  inventory. It must not import `engram.core`, `engram.store`, `engram.index`,
  CLI, client, command, dogfood, or background modules.

### Public API Roles

- [FCI-8] `Engram` remains the low-level domain object.
- [FCI-9] `EngramClient` is the recommended app, agent, tool, and validation
  harness surface.
- [FCI-10] `Engram.recall(id, scope?, count_access?)` is the low-level direct
  recall surface. `scope="item"` recalls an exact item; named scopes such as
  `scope="episode"` and `scope="arc"` and integer tiers such as `1`, `2`, or
  `3` recall the summary at that tier whose support contains the anchor ID.
- [FCI-11] Engram must not keep a parallel `get()` compatibility path for
  low-level direct recall.
- [FCI-12] `EngramClient.context(query?, max_tokens?)` is the client context
  method. There is no `EngramClient.build_context()` alias in this contract.
- [FCI-13] `EngramClient.close()` must be idempotent.
- [FCI-14] Calls to public `EngramClient` operations after close must raise
  the public `EngramClosedError`.
- [FCI-15] The package root must re-export stable public types and errors
  needed by local app users.

### Access-Score Mutation

- [FCI-16] Explicit low-level search and direct recall increment access by
  default.
- [FCI-16.1] Scoped recall increments only the returned item, not intermediate
  anchor items used to traverse parent-child links.
- [FCI-17] Command and client search and recall increment access by default.
- [FCI-18] Command and client search and recall must support
  `count_access=False`.
- [FCI-19] Context assembly must not increment access.
- [FCI-20] Status and inspection operations must not increment access.
- [FCI-21] Rebuild may refresh `indexed_at`, but must not increment access.
- [FCI-22] Model-facing tools from `EngramClient.llm_tools()` must not
  increment access.
- [FCI-23] Dogfood context snapshots must not increment access.

### CLI Structured Output

- [FCI-24] Default CLI output must remain unchanged unless a later migration
  spec changes it.
- [FCI-25] Machine-readable CLI output is additive and uses `--json`.
- [FCI-26] `engram init --json` must return an object with exactly:
  `vault_path`.
- [FCI-27] `engram record TEXT --json` and
  `engram record --importance INT TEXT --json` must return an object with
  exactly: `id`.
- [FCI-28] `engram search QUERY --json` must return a list whose items have
  exactly: `id`, `tier`, `text`, `source`, `fused_score`, `access`,
  `relevance`, `score`.
- [FCI-29] `engram context --json` must return an object with exactly:
  `context`, `term`, `total_tokens`.
- [FCI-30] `engram recall [episode|arc|TIER] ID --json` must return the same
  item shape as default recall output: `id`, `tier`, `text`, `created_at`,
  `access`, `relevance`, `indexed_at`, `summary_terms`.
- [FCI-31] `engram set-importance ID IMPORTANCE --json` must return the same
  item shape as recall.
- [FCI-32] `engram vault status --json` must return the
  `VaultStatus.model_dump(mode="json")` shape.
- [FCI-33] `engram vault rebuild-index --json` must return the
  `RebuildResult.model_dump(mode="json")` shape.
- [FCI-34] `engram vault process --json` must return exactly:
  `processed_ids`, `created_episode_ids`, `created_arc_ids`,
  `failed_item_ids`, `processed_count`, `is_idle`.

### Test Guardrails

- [FCI-35] Architecture tests must enforce import boundaries and private
  storage/index access rules.
- [FCI-36] Command/client/CLI contract tests must use real SQLite and LanceDB
  for local deterministic behavior.
- [FCI-37] Tests may shim external, slow, or nondeterministic boundaries:
  Weft submission, LLM summarization, and deterministic embeddings.
- [FCI-38] Tests must not use mock call counts as the primary proof for core
  command, client, CLI, storage, retrieval, or context behavior.

## 4. Implementation Mapping

| Contract family | Owner | Enforcement |
|-----------------|-------|-------------|
| Domain behavior | `engram/core/memory.py` | core tests |
| Command shapes | `engram/commands/memory.py` | command tests |
| Client lifecycle and tools | `engram/client.py` | client tests |
| CLI parsing and presentation | `engram/cli.py` | CLI tests |
| Embedded Weft runtime integration | `engram/runtime/weft.py` | background and architecture tests |
| Weft worker boundary | `engram/background.py` | background and architecture tests |
| Dogfood validation path | `engram/dogfood/codex_replay.py` | dogfood and architecture tests |
| State ownership | `engram/store/sqlite.py` | store/core tests |
| Retrieval ownership | `engram/index/lance.py` | index/core tests |

## 5. Failure Modes and Edge Cases

- [FCI-39] If a shared operation needs a shape not exposed through
  `EngramClient`, add a narrow command/client method instead of reaching into
  private storage or index fields.
- [FCI-40] If a CLI JSON addition would change default output, preserve the
  default output and add structured output only behind `--json`.
- [FCI-41] If architecture tests flag an intended dependency, update this spec
  and the test together. Do not weaken the test silently.
- [FCI-42] If client methods are called after close, fail with
  `EngramClosedError` rather than leaking incidental backend exceptions.
- [FCI-43] If a public surface is renamed or replaced, move all repo users to
  the canonical path in the same change. Do not add backwards-compatibility
  layers; parallel paths hide bugs.
- [FCI-44] If the state-store schema changes, define one current schema shape
  and explicit forward-only migrations for known older Engram shapes. Migrations
  must be ordered, transactional, idempotent, and source-of-truth only. Reject
  unknown, corrupted, wrong-identity, and newer-than-supported stores clearly.

## 6. Verification Expectations

Changes governed by this spec should be proven with:

- architecture/import-boundary tests
- command return-shape tests
- client/command parity tests
- CLI default-output and `--json` tests
- current-vault open tests
- known older Engram shape migration tests
- unknown, corrupted, wrong-identity, and newer store rejection tests
- access-score mutation tests for retrieval, context, tools, and dogfood
- background worker tests showing `repair_item()` owns processing status
- dogfood replay tests using `EngramClient`
- full static gates: pytest, mypy, and ruff

## Related Plans

- `docs/plans/2026-04-22-engram-foundation-excellence-plan.md`
- `docs/plans/2026-04-23-simplebroker-style-backend-foundation-plan.md`
- `docs/plans/2026-04-23-layering-cleanup-plan.md`
- `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`
- `docs/plans/2026-04-23-record-importance-plan.md`
- `docs/plans/2026-04-23-api-vocabulary-process-set-importance-plan.md`
