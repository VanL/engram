# Codex Corpus Validation

## Purpose and Scope

This note explains the internal dogfood harness that replays Codex JSONL
conversation logs into fresh Engram vaults. The goal is validation, not a public
product surface.

It covers:
- supported corpus roots
- why validation uses fresh vaults instead of reset or forget
- where generated artifacts live
- the mechanical smoke command and escalation path

## Governing References

- `docs/plans/2026-04-21-codex-corpus-validation-implementation-plan.md`
- `docs/specs/10-minimum-memory-model.md` [MM-9], [MM-12], [MM-19]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-1], [MWS-23], [MWS-27]
- `docs/specs/12-local-app-surface.md` [LAS-1], [LAS-8], [LAS-19]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-6], [FCI-9],
  [FCI-23]

## Current Design

The dogfood harness lives under `engram/dogfood/`.

`codex_jsonl.py` is read-only. It discovers and parses supported Codex event-log
JSONL files, extracts paired user-plus-assistant conversation units, and reports
malformed or unsupported records. It does not create or mutate Engram vaults.

`codex_replay.py` replays parsed pairs into a new vault through
`EngramClient`, the same app/tool surface future benchmark harnesses should
use. It writes sidecar artifacts that map source pairs to generated Engram
moment ids. Source provenance stays in the run directory, not in
`memory_items` and not in LanceDB.

Mechanical replay initializes the private embedded Weft project but disables
autostart and background submission by default. It then processs through
`EngramClient.process()`, which delegates to the shared command/domain repair
path. This gives the validation run one processing driver while preserving
normal Engram behavior outside the dogfood harness.

## Supported Corpus Roots

The primary supported corpus is:

```bash
~/.codex/sessions/**/*.jsonl
```

Archived sessions are optional smoke input:

```bash
~/.codex/archived_sessions/*.jsonl
```

Archived sessions are excluded by default. Use `--include-archived` only when a
smoke run explicitly needs them.

The harness intentionally ignores live sqlite state, recovery artifacts,
`history.jsonl`, and `session_index.jsonl`. If useful data appears only there,
inspect the format first and update the parser contract before importing it.

## Fresh Vault Rule

Each validation run creates a fresh vault. Do not use `forget --all`, reset, or
delete-in-place workflows for this harness.

The reason is simple: replay validation is an experiment. A fresh vault gives a
clean, auditable state transition from source JSONL to moments, episodes, arcs,
index rows, and context snapshots. Resetting an existing vault would mix
experiment setup with destructive memory semantics and make failures harder to
explain.

## Artifacts

Generated artifacts should live under `.engram-runs/`, which is gitignored
because manifests and context snapshots may contain private conversation text.

Common outputs:

- `manifest.jsonl`: one source-pair to Engram-moment mapping per imported pair.
- `run-summary.json`: parser and import summary.
- `mechanical-report.json`: processing and context snapshot gate report.
- `context-snapshots/*.md`: rendered client context output during replay.

Do not commit raw run artifacts unless the user explicitly asks for a curated
sample.

## Commands

Inspect the local corpus without importing:

```bash
./.venv/bin/python -m engram.dogfood.codex_replay inspect --root ~/.codex
```

Run a small mechanical smoke:

```bash
./.venv/bin/python -m engram.dogfood.codex_replay mechanical \
    --root ~/.codex \
    --vault .engram-runs/codex-smoke/.engram \
    --run-dir .engram-runs/codex-smoke \
    --limit-pairs 200 \
    --snapshot-every 50 \
    --tokens 2048
```

The run directory must be missing or empty, and the vault path must not exist.
If a run needs to be repeated, choose a new run directory.

Export practical-evaluation checkpoint artifacts from a passing manifest:

```bash
./.venv/bin/python -m engram.dogfood.codex_replay checkpoints \
    --manifest .engram-runs/codex-smoke/manifest.jsonl \
    --output .engram-runs/codex-smoke/checkpoints \
    --indices 50,100 \
    --oracle-pairs 3 \
    --tokens 2048
```

If `--indices` is omitted, the helper exports the first eligible checkpoints
after `--min-prior-pairs`. The output directory must be missing or empty. Each
checkpoint directory contains:

- `baseline.md`: current user message only
- `treatment-phase-a.md`: prior-only Engram context plus the same user message
- `oracle.md`: historical assistant answer and future turns, not model input
- `context.md`: rendered prior-only context
- `scorecard.md`: blank manual scoring template
- `metadata.json`: source, prefix, vault, and status metadata

## Mechanical Gate

The mechanical report passes only when:

- at least one moment was imported
- local processing processs to zero pending items
- there are zero processing failures
- SQLite and LanceDB agree on indexed item counts
- context snapshots were written
- episode and arc counts exist once the sample is large enough to require them

This gate proves pipeline shape. It does not prove that the context is useful.

## Escalation

If unsupported parser counts are high, inspect representative JSONL records
before changing Engram. Unsupported formats are a parser-scope issue unless they
force a real source-timestamp or provenance requirement.

If processing failures appear after local process, debug Engram processing before
starting practical evaluation. Practical scoring is meaningless if moments are
not reliably indexed and coalesced.

If context snapshots are noisy but the mechanical gate passes, keep the replay
harness stable and tune context selection separately. Do not hide retrieval or
assembly problems by changing the importer.
