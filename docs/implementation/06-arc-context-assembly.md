# Arc Context Assembly

## Purpose and Scope

This note explains the current rationale for the first full hierarchy in the
local app: moments, episodes, arcs, and four-bucket context assembly.

It covers:
- why arcs reuse the same summary-item schema as episodes
- why arc creation reuses the same semantic-boundary algorithm
- how the context builder now uses a real medium-term bucket

## Governing Spec References

- `docs/specs/10-minimum-memory-model.md` [MM-9], [MM-12]
- `docs/specs/11-minimum-write-search-context-slice.md` [MWS-20], [MWS-26]
- `docs/specs/13-context-assembly-and-arcs.md` [CAA-1], [CAA-5], [CAA-8]

## Current Design Rationale

### One Summary Schema Above Moments

Moments are the only special-case tier. Everything above tier 0 currently uses
the same durable item schema plus:
- `tier`
- ordered parent-child edges
- summary text
- summary terms

This keeps the hierarchy extensible without pretending that new tiers are
free. Storage can scale to more levels cheaply. Semantics still need to be
earned tier by tier.

### Same Boundary Logic, Different Input Tier

Arc creation reuses the same semantic-boundary coalescing rule already proven
for episodes:
- ordered window
- running centroid
- semantic boundary closes the window
- max window still acts as a ceiling

The difference is only the input tier. Episodes summarize moments. Arcs
summarize episodes.

Current orchestration no longer hard-codes separate episode and arc loops as
the only coalescing shape. The shared storage and selection path now run as
declared tier pairs. The current built-in pairs are still moment -> episode and
episode -> arc, but the coalescing operation itself is no longer tied to those
two names.

### Medium-Term Is Now Real

The skeleton folded the medium-term budget into long-term because arcs did not
exist yet. The current app no longer does that.

Current bucket model:
- immediate: recent moments
- short-term: recent episodes
- medium-term: recent or term-matching arcs
- long-term: high-importance retained background items

Topic bias now prefers arcs for medium-term context and keeps older
moment/episode material in long-term selection. This preserves the bucket roles
instead of flattening them into one search-biased pool.

## Key Files

| Path | Purpose |
|------|---------|
| `engram/core/coalesce.py` | Shared semantic-window logic for declared summary tiers |
| `engram/core/context.py` | Four-bucket budget resolution and context sections |
| `engram/core/memory.py` | Declared tier-pair coalescing, arc recall, and topic-biased assembly |
| `engram/store/sqlite.py` | Generic summary-item creation and ordered parent-child storage |
| `tests/core/test_context.py` | Arc retrieval round-trip and sparse-corpus context coverage |
| `tests/core/test_memory.py` | Arc creation and recall coverage |

## Current Invariants

- Arcs are additive summaries over episodes.
- Arcs do not get their own storage schema.
- Context assembly still does not increment access.
- Sparse corpora may return an empty medium-term bucket instead of filler.
