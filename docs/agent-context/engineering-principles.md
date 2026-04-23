# Engineering Principles

These are the reusable engineering rules that most often prevent agentic work
from drifting. Adapted for the engram memory system.

## 1. Extend the Existing Path Before Adding a New One

If a change touches an established flow, start by extending the current flow.
Do not introduce a second path, side channel, or compatibility shim. If a
contract changes, update the canonical path and move all repo users in the same
change.

## 2. Respect the Two-Layer Split

LanceDB handles retrieval (search, embeddings, FTS). SQLite/PG handles state
(access scores, decay, coalescing, parent-child, blobs, config). Both share
the state-store-allocated hybrid timestamp ID space. Don't make one layer do
the other's job. IDs stay format-compatible with `time.time_ns()` values while
using low-order bits for a logical counter. Summary IDs are derived from their
support set: first unused ID after the maximum child ID.

If you need transactional updates (access score increments, decay sweeps),
that's the state store. If you need similarity search or keyword matching,
that's LanceDB. If you're tempted to query LanceDB for parent-child
traversal, stop -- that's a relational operation.

## 3. Coalescing Is Lossy by Design

Episode and arc summaries intentionally lose detail. The contract is:

- Summaries must preserve distinctive TF-IDF terms from constituent items
- Summaries must pass a retrieval round-trip test: can you find the
  constituent moments by searching with terms from the summary?
- Original moments are never deleted by coalescing

If a summary doesn't preserve enough signal to serve as a retrieval cue
back to the originals, the summary is broken, not the moments.

## 4. Read Spec, Code, Test, and Plan Before Inference

Do not infer behavior from file names or mental models alone. Read:

1. the relevant spec
2. the current implementation
3. the closest existing test
4. the active plan or implementation note

Then decide what to change.

## 5. Prefer Real Behavior Over Mock-Heavy Proof

For important lifecycle, integration, or contract behavior, test the real
surface whenever practical. Mock only boundaries that are external, slow, or
nondeterministic (e.g., LLM calls for summarization can be mocked; LanceDB
search and SQLite state should be real).

## 6. Keep Traceability Bidirectional

Treat documentation traceability as part of implementation, not optional
cleanup.

- Plans cite exact spec sections.
- Specs backlink the plans that implement them.
- Implementation docs explain the current rationale and ownership.
- Code points back to governing specs when ownership would otherwise be
  ambiguous.

## 7. Reuse Local Paths and Helpers Before Inventing New Ones

Prefer existing helpers, utilities, and patterns over new abstractions.
DRY means reusing the known good path, not creating a more generic one because
it feels elegant in the abstract.

## 8. Keep Future-Proofing Out Unless the Current Work Requires It

Apply YAGNI aggressively. The tier system is extensible by depth integer --
don't add tier-specific logic for tiers that don't exist yet. Don't build
plugin systems for embedding models when one model works. Don't add
configuration for things that have sensible defaults.

## 9. Use Independent Review to Reduce Author Blindness

For non-trivial plans and implementations, run an independent review pass with
the governing specs, plan, implementation note, and touched files in view.

Prefer a different agent family or model from the original author when
available.

## 10. Plan the Boundaries Before the Tasks

Strong plans do not only describe the new behavior. They describe what must not
change, where state crosses boundaries, and which proof must stay real.

For risky work, name up front:

- invariants and existing contracts that must survive
- which storage layer owns each operation
- what must not be mocked
- rollback or rollout sequencing
- one-way doors or destructive edges

## Warning Signs

Sessions usually go sideways when one of these happens:

- a second path appears instead of extending the canonical one
- LanceDB is used for transactional state or SQLite for search
- a change relies on intuition rather than reading the relevant docs and code
- a failing regression is replaced by a shallow happy-path test
- the docs are treated as post-hoc cleanup rather than part of delivery
- a later stage quietly changes the direction of the earlier plan
- the plan says what to build but not what must stay true
- coalescing quality is assumed rather than tested with retrieval round-trips

## Foundation Review Checklist

Use this quick check before approving foundation changes:

- Which layer owns this behavior: domain, command, client, CLI, tool,
  background, dogfood, storage, or retrieval?
- Is there already a command-layer path that should be reused?
- Does this operation mutate access scores? If yes, is it explicit retrieval?
- Does this cross SQLite, LanceDB, or Weft ownership?
- Does this need CLI, client, tool, and dogfood parity?
- What must stay real in tests? Default to real SQLite, LanceDB, commands, and
  client surfaces.
- Which public shape or error contract could drift?
- Is this current behavior or a planned idea?
- Is this adding a backwards-compatibility path instead of moving all users to
  the canonical path?
