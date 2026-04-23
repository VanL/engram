# Hierarchical Memory Model

Status: Active

This spec defines Engram's durable memory model for the local app. It governs
vault isolation, memory-item tiers, identity, parent-child relationships, and
score-related state. It does not define the full execution model; that belongs
to the embedded-Weft execution spec.

## 1. Purpose and Scope

This spec governs the durable model for Engram's hierarchical text memory.

In scope:
- vault isolation
- moment and higher-tier summary-item contracts
- shared identity rules
- additive parent-child structure
- access and relevance state
- source-of-truth ownership between the state store and retrieval index

Out of scope:
- Weft task execution semantics
- blob ingestion
- deletion semantics
- import/export
- Postgres behavior

## 2. Mental Model

Engram stores memory in isolated vaults. A vault owns:
- one transactional state store
- one retrieval index
- one embedded execution runtime
- one shared ID space across state and retrieval layers

Moments are the only special-case tier:
- tier 0: moment

Every tier above 0 uses the same durable summary-item schema and differs by
declared `tier` plus ordered parent-child relationships:
- tier 1: episode
- tier 2: arc
- tier 3+: extensible higher-tier summaries

Moments are raw text records. Higher-tier items are additive summaries over
ordered lower-tier sequences. The retrieval index is a searchable projection of
the state store, not the source of truth.

## 3. Requirements

### Vault Isolation

- [MM-1] Each Engram instance must operate against exactly one vault.
- [MM-2] A vault must isolate its state store, retrieval index, and domain
  processing projections from every other vault.

### Shared Identity

- [MM-3] Every memory item must have a non-negative hybrid timestamp integer
  ID allocated from the vault state store. The ID is format-compatible with
  `time.time_ns()` values: a nanosecond-format epoch integer whose low-order
  bits are reserved for a logical counter. Real clocks usually expose coarser
  than nanosecond precision, so these low bits are normally zero or low-signal
  physical time.
- [MM-4] IDs must be unique within a vault and immutable after creation. Gaps
  are valid; callers must not infer that an ID exactly equals `created_at`.
- [MM-5] The state store and retrieval index must use the same item ID for the
  same logical item.
- [MM-5.1] Moment IDs are allocated from the vault's hybrid timestamp clock.
  Higher-tier summary IDs are support-anchored: for a non-empty support set,
  the summary ID must be the first unused integer greater than the maximum
  child ID.

### Moment Contract

- [MM-6] A moment must include:
  - `id`
  - `tier=0`
  - `text`
  - `created_at`
  - `access`
  - `relevance`
- [MM-7] A moment's text and creation timestamp are immutable after storage.
- [MM-8] A newly stored moment must start with non-negative access and
  relevance state.

### Higher-Tier Summary Contract

- [MM-9] A higher-tier summary item must include the same core durable fields
  as a moment, except with `tier >= 1` and summary terms when available.
- [MM-10] A higher-tier summary item must summarize an ordered sequence of
  lower-tier items that belong to one semantic window.
- [MM-11] A higher-tier summary item must preserve enough distinctive terms to
  act as a retrieval cue back to its constituent items.
- [MM-11.1] For a non-empty support set, a higher-tier summary's `created_at`
  must be `max(child.created_at)`. Processing and indexing timestamps must use
  separate processing-state fields, not the memory timeline field.

### Parent-Child Structure

- [MM-12] Parent-child relationships must be additive. Creating a higher-tier
  summary item must not delete or rewrite the underlying children.
- [MM-13] The state store must preserve the ordered child membership of every
  higher-tier summary item.
- [MM-13.1] The state store must support exact parent lookup and
  support-range containment over parent-child links. Support-range containment
  for a parent tier means `min(child.id) <= anchor_id <= max(child.id)`.
- [MM-14] A memory item may exist without a parent at the next tier yet. This
  is normal while waiting for more input or deferred coalescing.

### Scoring State

- [MM-15] Each memory item must carry:
  - an access score
  - a relevance multiplier
- [MM-16] Access must be non-negative.
- [MM-17] Relevance must be at least `1.0`.
- [MM-18] Retrieval ranking must combine access and relevance
  multiplicatively, not additively.

### Storage Ownership

- [MM-19] The transactional state store is the source of truth for item
  content, score state, parent-child links, declared tier, and any Engram-owned
  domain processing projections.
- [MM-20] The retrieval index is a rebuildable search projection.
- [MM-21] If the state store and retrieval index disagree, the state store
  wins.

## 4. Invariants and Constraints

- [MM-22] Coalescing must be additive. It may create summaries, but it must not
  delete moments.
- [MM-23] The current local app supports only text items.
- [MM-24] The tier system is open-ended even if only a subset of tiers are
  named or surfaced in the current local app.
- [MM-25] The memory model must preserve one shared ID space across state and
  retrieval layers.
- [MM-25.1] `created_at` is the canonical memory timeline timestamp. For
  moments, it is the observed physical creation timestamp. For summaries, it is
  derived from the support set as `max(child.created_at)`. ID ordering is a
  durable timeline projection and may differ from exact physical timestamp
  order within the low-order logical-counter range.

## 5. Interfaces and Data Contracts

The durable state contract for a memory item is:

```text
id: int
tier: int
text: str
created_at: int
access: float
relevance: float
indexed_at: int | null
summary_terms: list[str]
```

The durable parent-child contract for any summary item is:

```text
parent_id: int
child_id: int
position: int
```

Execution-state details and Weft-task correlation rules are governed by
`docs/specs/14-embedded-weft-execution-model.md`, not by this memory-model
spec.

## 6. Failure Modes and Edge Cases

- [MM-26] If the retrieval index is unavailable or stale, the state store must
  remain authoritative and recoverable.
- [MM-27] A moment may be durable in the state store before it is searchable.
  This is valid deferred-processing lag, not corruption by itself.
- [MM-28] A higher-tier summary item that cannot retrieve or identify its
  constituent lower-tier items is considered broken.

## 7. Verification Expectations

Proof for changes governed by this spec should include:
- persistence of moments and higher-tier summary items in the state store
- additive parent-child structure
- shared-ID consistency between the state store and retrieval index
- memory ID uniqueness and monotonic allocation under repeated or concurrent
  physical timestamps
- support-anchored summary IDs and support-derived summary `created_at`
- score-state invariants
- retrieval round-trip assertions from summaries back to constituent items

## Related Plans

- `docs/plans/2026-04-16-initial-skeleton-validation-plan.md`
- `docs/plans/2026-04-16-basic-working-app-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
- `docs/plans/2026-04-23-hybrid-memory-id-generator-plan.md`
