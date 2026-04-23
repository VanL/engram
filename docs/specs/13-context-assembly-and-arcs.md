# Hierarchical Coalescing and Context Assembly

Status: Active

This spec defines Engram's higher-tier coalescing model and its multi-horizon
context assembly behavior.

## 1. Purpose and Scope

This spec governs:
- higher-tier coalescing behavior
- the first named higher tier, `arc`
- four-bucket context assembly
- topic-biased context selection
- sparse-corpus fallback rules

It does not govern:
- vault lifecycle
- rebuild and recovery surfaces
- Weft task execution ownership
- blob handling
- hosted or multi-user behavior

## 2. Mental Model

The hierarchy exists to budget a finite context window across time horizons:

- immediate: recent moments
- short-term: recent lower-tier summaries
- medium-term: recent or relevant higher-tier summaries
- long-term: high-importance retained items

Moments are special. Higher tiers are not. Tier 1 is conventionally called
`episode`. Tier 2 is conventionally called `arc`. Higher tiers may be added by
declaring another summary tier rather than inventing a new storage schema.

Higher-tier items are additive summaries over ordered lower-tier sequences.
They do not replace hybrid search. They are compression layers for context
assembly.

## 3. Requirements

### Higher-Tier Coalescing

- [CAA-1] A higher-tier summary item at tier `N + 1` must be an additive
  summary over an ordered sequence of tier `N` items.
- [CAA-2] Higher-tier creation must reuse the same semantic-boundary approach
  across tiers, even if tier-specific thresholds or prompts evolve later.
- [CAA-3] Creating a higher-tier summary item must not rewrite or delete the
  underlying lower-tier items.
- [CAA-4] Higher-tier summaries must preserve enough distinctive terms to act
  as cues back to their constituent items.

### Named Tier Conventions

- [CAA-4.1] Tier 1 is the default `episode` tier.
- [CAA-4.2] Tier 2 is the default `arc` tier.
- [CAA-4.3] Tiers above 2 may be added by declared tier and policy rather than
  a new storage schema.

### Context Assembly

- [CAA-5] The default context builder must support four buckets:
  - immediate
  - short-term
  - medium-term
  - long-term
- [CAA-6] The context builder must respect a total token budget.
- [CAA-7] When a bucket's material is sparse or absent, the builder must
  return a smaller or rebalanced context rather than fabricate filler.
- [CAA-8] Topic-biased selection may favor matching medium-term or long-term
  material, but it must not override immediate and short-term buckets
  completely.
- [CAA-9] Context assembly must continue to avoid incrementing access scores.

### Transitional and Future-Tier Rule

- [CAA-10] The first named higher-tier expansion after episodes is the `arc`
  tier, but the architecture must not assume tier 2 is the last summary tier.

### Public Surfaces

- [CAA-11] The Python API and CLI must expose arc recall through the canonical
  recall surface. `scope="arc"` or `scope=2` returns the arc whose support
  contains the anchor ID.
- [CAA-11.1] Higher tiers must reuse the same scoped recall surface. Named
  scopes may exist for built-in tiers, and integer scopes remain the generic
  path for deeper tiers.

## 4. Invariants and Constraints

- [CAA-12] Higher tiers exist for compression and context budgeting, not to
  replace hybrid search.
- [CAA-13] Sparse corpora should degrade gracefully.
- [CAA-14] If a higher tier reduces context quality, the app should remain
  usable with the lower tiers while that tier is disabled, hidden, or tuned.

## 5. Interfaces and Data Contracts

Current additions:

```text
Engram.recall(id, scope="arc") -> MemoryItem
engram recall arc <id>
Engram.recall(id, scope=2) -> MemoryItem
engram recall 2 <id>
```

The exact coalescing trigger, tier policy, and bucket allocation can evolve,
but the ownership and fallback rules above should remain stable.

## 6. Failure Modes and Edge Cases

- [CAA-15] If higher-tier summaries stop serving as retrieval cues back to
  lower-tier material, they are broken even if they read well.
- [CAA-16] If the medium-term bucket is empty, the builder should still return
  a valid context from the remaining buckets.

## 7. Verification Expectations

Changes governed by this spec should be proven with:
- retrieval round-trip tests from higher-tier summaries to lower-tier material
- sparse-corpus context tests
- comparison showing higher tiers improve or at least do not degrade context
  utility
- proof that a new declared tier can reuse the same durable summary-item shape
  even if no user-facing helper is added yet

## Related Plans

- `docs/plans/2026-04-16-basic-working-app-plan.md`
- `docs/plans/2026-04-16-weft-background-and-llm-integration-plan.md`
- `docs/plans/2026-04-17-engram-thin-over-weft-runtime-plan.md`
