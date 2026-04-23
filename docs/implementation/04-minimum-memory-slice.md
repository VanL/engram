# Minimum Memory Slice

## Purpose and Scope

This document explains the first implementation boundary for Engram's minimum
working slice: text moments, episode coalescing, hybrid retrieval, importance
updates, direct recall, the initial local-vault context path, and the shared
command/client surface.

This is not the full target design from the README. It is the first executable
product slice used to validate the thesis before broadening into a larger local
app. Later local-app lifecycle and arc-tier behavior are documented in
`05-local-vault-recovery.md` and `06-arc-context-assembly.md`.

## Governing Spec References

- `docs/specs/10-minimum-memory-model.md` [MM-1], [MM-12], [MM-19], [MM-21]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-5],
  [MWS-10], [MWS-16], [MWS-23], [MWS-27]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-1], [FCI-5],
  [FCI-9], [FCI-16], [FCI-24], [FCI-35]

## Current Design Rationale

### One Durable Write Path

`record()` writes only to SQLite, records durable downstream-work need, and
submits a Weft task before it returns. This keeps the public write path
non-blocking while preserving the state-store-is-authoritative invariant.

The runtime background path is Weft. The local repair path is intentionally
secondary:

- Engram now routes submission through a code-owned internal TaskSpec
  inventory instead of building one ad hoc inline TaskSpec per submission
- Engram submits those TaskSpecs through Weft's public Python client surface,
  so manager startup, spawn reconciliation, and task handles stay owned by Weft
- Engram now routes actual item processing through one shared domain operation;
  Weft workers and local repair helpers wrap the same core processing seam

- in the default local sqlite-backed path, Engram configures Weft so the
  vault directory is also the Weft metadata directory for that vault

- Python: `Engram.process_once()` and `Engram.process()`
- CLI: `engram vault process`

This is deliberate. It preserves a local proof and recovery tool without
reintroducing an Engram-owned queue.

### Two-Layer Ownership From Day One

The first slice already keeps the storage split sharp:

- SQLite owns item records, score state, parent-child links, and lag/failure
  projections
- LanceDB owns keyword retrieval, dense-retrieval embedding, and vector search

The index is rebuildable. The state store is authoritative.

Moment IDs are clock-allocated hybrid timestamp integers. Summary IDs are
support-anchored derived identifiers: an episode, arc, or higher summary uses
the first unused MID after the maximum child MID, and its `created_at` follows
the support set rather than processing time.

### Real Model Boundaries, Deterministic Tests

The current implementation uses:
- Lance's `sentence-transformers` embedding-function integration with
  `all-MiniLM-L6-v2` as the default dense-retrieval model
- `gemini/gemini-3.1-flash-lite-preview` for structured summary and keyword
  extraction
- Weft's built-in `llm` agent runtime with schema-constrained output for
  coalescing

Tests still use deterministic local shims for embeddings, Weft submission, and
summary generation. That keeps CI stable while preserving the real production
shape at the integration boundary.

The important boundary is:
- Lance owns retrieval-side embedding and vector search
- Engram reuses that same embedding function for semantic-boundary coalescing
- the test path is deterministic only at the external boundary

### Context Assembly Bias

In the minimum slice, the context builder used three effective buckets:

- immediate: recent moments
- short-term: recent episodes
- long-term: search-biased older moments plus high-value items

The nominal medium-term budget was folded into long-term until arc support
existed. That bridge behavior is no longer current; the arc-tier and
four-bucket model now live in `06-arc-context-assembly.md`.

### Shared Command and Client Surface

Engram now has a command layer under `engram.commands`. This is the shared
surface for CLI, client, and model-facing tool adapters. It delegates to
`Engram` for domain behavior and owns argument normalization plus
JSON-serializable output shaping.

`EngramClient` is a thin public wrapper over that command layer, analogous to
Weft's `WeftClient`. It should be the default surface for app code and future
agent/tool integrations. LLM tools produced by `EngramClient.llm_tools()` are
read-only: they expose context, search, and recall without incrementing access
scores. The lower-level `Engram` API and default client search/recall still
preserve explicit-retrieval access counting.

The surface map is:

| User action | Client | Command layer | Domain |
|-------------|--------|---------------|--------|
| `engram record [--importance INT]` | `EngramClient.record(..., importance=...)` | `commands.record(..., importance=...)` | `Engram.record(..., importance=...)` |
| `engram search` | `EngramClient.search()` | `commands.search()` | `Engram.search()` |
| `engram context` | `EngramClient.context()` | `commands.context()` | `Engram.build_context()` |
| `engram recall [episode|arc|TIER] ID` | `EngramClient.recall()` | `commands.recall()` | `Engram.recall()` |
| `engram vault status` | `EngramClient.status()` | `commands.status()` | `Engram.status()` |
| `engram vault rebuild-index` | command layer | `commands.rebuild_index()` | `Engram.rebuild_index()` |
| `engram set-importance ID INT` | `EngramClient.set_importance()` | `commands.set_importance()` | `Engram.set_importance()` |
| `engram vault process` | `EngramClient.process()` | `commands.process()` | `Engram.process()` |

Do not add compatibility aliases for renamed public surfaces. If the canonical
surface changes, move code, tests, and docs together so parallel paths do not
hide drift.

## Key Files

| Path | Purpose |
|------|---------|
| `engram/core/memory.py` | Public API, shared item-processing operation, hybrid search, context assembly orchestration |
| `engram/core/coalesce.py` | Semantic-boundary window selection and summary generation |
| `engram/core/context.py` | Token-budget handling and section assembly |
| `engram/core/llm_tasks.py` | Gemini-backed structured summary and keyword extraction |
| `engram/core/embeddings.py` | Lance-backed and deterministic embedding adapters |
| `engram/core/scoring.py` | Reciprocal Rank Fusion and score boosting |
| `engram/commands/memory.py` | Shared command-layer operations and JSON-safe serialization |
| `engram/client.py` | Public client wrapper and read-only LLM tool constructors |
| `engram/_internal_tasks.py` | Stable internal Weft TaskSpec inventory |
| `engram/background.py` | Internal-task submission path plus Weft wrapper around the shared processing operation |
| `engram/store/sqlite.py` | Authoritative state store and lag/failure inspection records |
| `engram/index/lance.py` | LanceDB retrieval projection |
| `engram/cli.py` | Shared-surface CLI entry point |
| `tests/core/test_context.py` | Thesis-validation corpus and context behavior checks |

## Current Invariants

- SQLite is the source of truth.
- LanceDB is rebuildable.
- Moments are immutable and not deleted by coalescing.
- Episode creation is additive.
- Explicit retrieval increments access.
- Context assembly does not increment access.
- CLI, client, and model-facing tools should route through the shared command
  layer rather than reimplementing command behavior.
- Model-facing tools are read-only by default and must not mutate access scores.
- Weft owns background execution; Engram does not own a second durable queue.
- Tests use deterministic shims at the external model and task boundary.

## Foundation Drift Watchlist

Treat these as review failures:

- a new public command is added only to `Engram`
- CLI bypasses `engram.commands`
- client duplicates command serialization
- dogfood reaches into `_store` or `_index`
- background path duplicates local repair logic
- context assembly starts incrementing access
- status or docs describe planned behavior as current
- a backwards-compatibility alias appears for a renamed public surface

## Background Work and Known Gaps

Still deferred:

- blobs
- deletion
- dump/load
- Postgres backend
- richer worker supervision and retry policy control

The biggest current risk is not plumbing correctness. It is whether the
validation corpus remains representative enough as real dogfooding starts.
