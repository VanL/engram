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
- When a plan changes intended behavior, exact proposed spec sections live
  in the plan for review; the **spec-promotion slice** applies them per a
  named strategy (in-file text-first, atomic, new file under an in-flight
  classification, or spec-authoring only). Prose `Status:` headers and
  machine classification are different mechanisms. After promotion, the spec
  tree is the single governing contract — not plan appendix text. See
  `runbooks/writing-plans.md` §4b–4d.

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

Review findings are claims, not facts: reproduce a finding before acting on
it, and reproduce your own "done/passing" assertions before making them. The
same discipline applies to status documents — a ledger that says "ship-ready"
is a claim about the past; the evidence is a rerun in the present. Verifier
error is real and its cost compounds, because a wrong finding acted on is a
defect introduced with confidence.

## 10. Plan the Boundaries Before the Tasks

Strong plans do not only describe the new behavior. They describe what must not
change, where state crosses boundaries, and which proof must stay real.

For risky work, name up front:

- invariants and existing contracts that must survive
- which storage layer owns each operation
- what must not be mocked
- rollback or rollout sequencing
- one-way doors or destructive edges

## 11. Prove the Problem with a Failing Test First

Write a failing test that proves the problem exists, watch it fail, then make
it pass. If you cannot write the failing test, you do not understand the
problem well enough to fix it. If something is hard to test, that is
information about the design, not permission to skip the test. Generate
fixtures through production code paths, not synthesis.

This complements principle 5 ("Prefer Real Behavior Over Mock-Heavy Proof"):
that one is about *what* to test; this one is about *when and why*.

The sanctioned exit is `runbooks/testing-patterns.md` Rule 5, and it
is loud, concrete, and falsifiable — never silent. A valid substitute
**always demonstrates the post-change correction**, and additionally
either demonstrates the pre-change failure (or its root cause) or
states why pre-change observation is impossible — never neither half.
Category labels are not reasons: a docs-only change with a
reproducible check available (a link check, a grep gate, a
traceability run) has its failing test and must use it; a broken
verification harness is a blocker to fix, not an exception to claim.
Invoking Rule 5 without the demonstration is skipping the test, and
skipping the test is not permitted at any task class.

## 12. Update All Consumers in the Same Change

When you rename a key, tighten a schema, or change a contract, update every
producer and consumer in the same change. A partial rename passes isolated
checks and fails at runtime; the synchronized update is the fix.

## 13. Enumerable Contracts Get Executable Gates

Any list a document asserts — issue codes, exit codes, edge cases, config
keys, CLI flags — must be mirrored by a machine check that enumerates it:
a firing test per element, a no-op prevention test per behavior-affecting
key.

Prose binds only what gets checked. Given identical written guidance, agents
comply uniformly with automated gates and unevenly with everything else — so
a contract element without a gate is a contract element that will silently
diverge. A declared element with no firing test is an untested contract and a
verification failure, not a style nit.

## 14. Variation Is Declared; Deficiency Is Gated

Plans bend on contact with reality, and different pressures produce
legitimately different designs. Do not build guardrails that force
convergence; build floors that catch deficiency on any path:

- record the baseline (spec version, contract SHA) the work was built against
- log deviations from that baseline where a reviewer will find them —
  deviation is legitimate, undeclared deviation is not
- hold every result, regardless of design, to the invariant floors: no
  crash reaches a user, exit codes and error messages tell the truth, the
  advertised default invocation works, declared contracts have firing tests,
  and the work's own status claims survive a rerun

Divergence between attempts is often productive — harvest it. Deficiency is
the failure mode, and it is orthogonal to which design was chosen.

## 15. Cohesion Over File Size (Floors, Not Line Counts)

Large cohesive files are deliberate, not neglected debt. Do not propose or
perform a file split on size grounds alone, and do not treat file size by
itself as a review finding.

Why: agents navigate by grep and read by offset; a big well-named file is a
pre-joined index. Every module boundary is a place an agent must correctly
guess that relevant code lives elsewhere — agents miss at boundaries far more
often than they miss things in front of them (lazy imports and indirection
are invisible walls). Splitting genuinely coupled code manufactures false
seams, and false seams breed parallel-implementation drift.

Two floors apply instead. Violating a floor IS a finding, however small the
file:

1. **Every implicit coupling gets an explicit marker at the edit point** — a
   blast-radius comment, an invariant note, or an enforcing helper for groups
   that must change together. An agent should never need to already know the
   file to edit it safely.
2. **Every state machine gets a name and a contract test.** Live runtime
   coupling (background-processing ordering, transaction ordering, queue
   semantics) must be a named unit with its own firing test; unnamed state
   machines cannot be contract-tested and silently diverge.

Distinguish the two kinds of coupling. A wide flat method surface sharing one
schema is structural coupling — safe at any size under floor 1; the `Engram`
facade in `engram/core/memory.py` (~850 lines of record/search/recall/
context/status methods over the shared `MemoryItem` schema) is the local
example, and its size is not a defect. Pieces interacting through live state
are behavioral coupling — floor 2 applies; the deferred item-processing
lifecycle (record → index → coalesce, with failure and retry state tracked
via `indexed_at` / `last_processing_error` in the state store) is the local
example: it has a name, explicit `record_processing_success` /
`record_processing_failure` surfaces, and firing tests in
`tests/test_background.py`. For behavioral coupling, extraction is justified
to create the testable boundary, not to shrink the file.

Cost to price in: a hot god file serializes parallel agent write-slices —
keep fan-out write scopes disjoint or sequence them.

## 16. Coalesce on Events, Not Time; Every Fold Keeps a Cue

Ledgers and plan directories are moment streams: raw, dated, append-only
in spirit. Left alone they grow until agents stop reading them. The fix is
periodic coalescing — distill cold entries into rules, harvest and retire
completed plans, promote recurring workflows to skills — governed by three
rules borrowed from tiered-memory design:

- **Trigger on accumulation, not on the calendar.** Repos have different
  pulse rates; event counts derived from a watermark scale automatically.
  A stored counter is state that drifts; a derived count is always honest.
- **Keep the recent tier verbatim.** Never summarize young, hot, or
  still-cited entries — that destroys exactly the detail the next session
  needs. Fold only what is cold and stable.
- **A summary that cannot lead back to its constituents is broken, even if
  it reads well.** Every fold leaves a date range and commit SHA in the
  surviving line. Git is the archive; the cue is what makes the archive
  reachable.

Promotion and decay are citation-driven, not vibes-driven: an entry cited
by later plans and reviews is promotion evidence; an uncited entry whose
subject has churned is decay evidence. Presence in the always-read context
is not evidence of usefulness — only explicit citation in work products
counts. Golden rules and safety invariants carry an importance floor and
never decay. Contradiction is resolved by editing the rule in place — with
a revision marker `(revised YYYY-MM-DD; was: <gist>)` when the meaning
changes, so citations to the rule stay interpretable across history — and
the old version lives in git.

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
- a regression is called "pre-existing" without running it on the base branch
  to prove it
- a file split is proposed on line count alone, without naming the coupling
  it would sever or the testable boundary it would create

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

## The Meta-Principle: Compound Knowledge

Every rule above is an instance of one idea: each unit of engineering work
should make the next one easier. A canonical converter means the next agent
doesn't re-derive the format. A blast-radius note means the next change knows
its impact zone. A failing test means the next debugging session starts from
known-good. A lesson written down means the next session doesn't repeat the
mistake. Treat the guidance docs, the lessons file, and explicit plan
boundaries as compound knowledge -- maintain them so the system gets easier to
work on correctly over time.
