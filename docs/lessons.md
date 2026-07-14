# Lessons Learned

Startup context is the Golden Rules plus entries after the watermark in
`docs/coalescing.md`; the rest of this ledger is searchable history.

Use this file for durable, project-level lessons that should influence future
sessions.

## When To Add A Lesson

- A correction exposed a repeated failure mode.
- A missing document or runbook caused rework.
- A plan or spec was too ambiguous to execute safely.
- A completed change revealed a stronger general rule than the repo previously
  encoded.

## Golden Rules

Universal principles that inform every change. The dated sections below are the
incident log; these are the durable rules distilled from it.

1. **Canonicalize once, at the boundary.** Normalize data at ingest/write
   boundaries through one shared helper. Never add runtime dual-case fallback
   readers -- they hide contract bugs.
2. **Fix forward, never fall back.** Don't add read-time fallback modes to mask
   drift or corruption. Detect invariant violations and surface them; repair
   with forward migrations.
3. **One canonical contract across all consumers.** Same keys, shapes, and
   vocabulary everywhere. Mixed legacy keys cause cascading mismatches.
4. **Validate at write time, fail fast.** Catch errors at the point of
   creation, not in downstream batch gates or runtime checks.
5. **Update all consumers in the same change.** When renaming keys, tightening
   schemas, or changing contracts, update all producers and consumers together.
   Partial renames pass isolated checks but fail at runtime.
6. **Test what you ship.** Add a regression test with each behavior-changing
   fix. Generate fixtures through production code paths, not synthesis.
7. **Plans fail at boundaries, not in the middle.** For risky work, name what
   must not change, hidden couplings, anti-mocking rules, rollout/rollback
   constraints, and post-deploy success signals before implementation starts.
8. **If a document is human-clear but agent-ambiguous, tighten it
   immediately.** Missing owner, boundary, verification path, or required action
   makes agents guess wrong even when the prose feels obvious to a human.
9. **Agents suggest dependencies; humans add them.** _(2026-06-30)_ An agent
   must not introduce a new dependency on its own -- propose it with
   justification: what it's for, why the standard library or an already-vendored
   dependency won't do, and the cost of taking it on. Every dependency is
   permanent code we don't control. The human decides whether it enters the
   manifest (`pyproject.toml` / `uv.lock`).
10. **Flag concerns and calibrate uncertainty, even when you did exactly what
    was asked.** _(2026-06-30)_ Surface risks you noticed in passing instead of
    letting a completed task hide a known landmine. Distinguish verified from
    unverified claims with precise language ("I have not confirmed X") rather
    than a vague "this should work." Report blockers with precise causes.
11. **Handle the error path, not just the happy path.** _(2026-06-30)_ A feature
    whose success path works but whose error, empty, or timeout path is silently
    ignored is incomplete. Name the failure cases in the plan's success criteria
    and test at least one. Do not paper over an unexpected null or empty result
    with a defensive check -- find out why it is null first.
12. **Formatting is owned by the project formatters -- run them; don't
    hand-format, and don't reformat incidentally.** _(2026-06-30)_ This repo's
    formatter is `ruff format` and its linter is `ruff check`, run from the
    in-repo virtualenv (`./.venv/bin/ruff format engram tests bin`,
    `./.venv/bin/ruff check engram tests bin`, and `mypy engram`; CI enforces
    `ruff format --check`). Let those tools decide style -- do not impose manual
    whitespace or style changes. In a behavior change, keep the diff to the
    lines the task requires; do not let an editor or formatter reflow untouched
    code into the change. Keep formatting-only churn in its own change. If a
    line changed only because "I was in there," revert it.
13. **Enumerable contracts get executable gates.** _(2026-07-02)_ Any list a
    document asserts — issue codes, exit codes, edge cases, config keys — must
    be mirrored by a machine check that enumerates it (a firing test per
    element, a no-op prevention test per key). Prose binds only what gets
    checked; agents comply uniformly with gates and unevenly with everything
    else. (See engineering-principles §13 and testing-patterns Pattern 6.)

## Lessons

### Cohesion Over File Size (2026-07-06)

- 2026-07-06: File size alone is not a review finding, and a split proposed
  on line count alone is not a fix. Large cohesive files (e.g., the `Engram`
  facade in `engram/core/memory.py`) are pre-joined indexes for grep-driven
  agents; splitting genuinely coupled code manufactures false seams and
  parallel-implementation drift. The real floors: implicit couplings get an
  explicit marker at the edit point, and every live state machine (e.g., the
  deferred item-processing lifecycle) gets a name and a contract test.
  Doctrine and local examples: engineering-principles §15 ("Cohesion Over
  File Size (Floors, Not Line Counts)").

### Guidance Sync (2026-07-02)

- 2026-07-02: Verification-lessons fold synced from agent-guidance (2026-07-02
  working tree; pinned 2026-07-14: that fold landed as agent-guidance
  `5927481`, and the 2026-07-14 wave adopted by
  `docs/plans/2026-07-14-agent-guidance-propagation-plan.md` is
  agent-guidance `2f7eff6`). Source
  incident record: the backstitch repo's `docs/lessons.md`.

### Design Phase (2026-04-16)

- Hierarchical summarization serves context assembly, not retrieval. The tier
  hierarchy exists to budget a finite context window across time horizons.
  Hybrid search (BM25 + vector) handles finding specific memories. Don't
  conflate the two purposes.

- Coalesce at semantic boundaries, not fixed counts. Fixed-N windowing ignores
  topic shifts and produces episodes that split coherent threads or jam
  unrelated topics together. Embedding similarity to a running centroid
  detects natural episode boundaries. The N parameter is a ceiling, not a
  trigger.

- Summaries must preserve distinctive terms. An episode summary that says
  "discussed authentication approaches" is useless for retrieval. One that
  says "evaluated JWT vs session tokens for API auth layer; leaning JWT"
  contains searchable terms that link back to the constituent moments. Use
  LLM-suggested terms to anchor the summarization prompt (TF-IDF needs a
  large corpus to be useful; the LLM works from day one).

- Access scoring should be multiplicative, not additive. `score = access *
  relevance` means hot+pinned dominates, cold+pinned has a floor, and
  cold+unpinned fades. Additive makes a pinned item and a hot item
  indistinguishable.

- Decay needs a floor. Pure exponential decay pushes everything to zero,
  including foundational decisions that are rarely accessed but structurally
  load-bearing. A decay floor (e.g., 0.1) prevents complete disappearance;
  relevance pinning handles truly important items.

- Two storage layers is the right split. LanceDB is append-optimized and
  search-oriented; SQLite/PG is write-optimized and transactional. Frequent
  point updates (access++, decay sweeps), parent-child traversal, and
  coalescing state machines belong in the relational store. Don't force one
  layer to do both jobs.

- Blobs should have a higher default relevance floor. Explicit attachment
  (image, PDF, code file) is a stronger importance signal than conversation
  flow. Default relevance 2.0 for blob-backed moments, 1.0 for everything
  else.

- Context assembly inclusion must not increment access scores. Only explicit
  retrieval (search, direct lookup) should count. Otherwise items in context
  perpetually boost themselves in a positive feedback loop.

- record() must be async. Moment storage returns as soon as the state store
  has the record. Embedding, LanceDB indexing, and coalescing happen in the
  background. Frontend retrieval never blocks on background work.

- State store is the source of truth; LanceDB is a rebuildable index. If the
  two layers become inconsistent, the state store wins and LanceDB is
  reconciled from it.

- CLI verb naming matters. "record" as a CLI name doesn't compose with
  necessary subcommands ("record forget" is absurd). Use the project name
  as the CLI command: `engram record`, `engram forget`, `engram context`.

- Each engram instance should be an isolated namespace (a "vault"). The
  default `~/.engram` is one vault. Agents specify which vault to use. This
  avoids one global memory mixing unrelated workstreams.

- Context budget splits should be defaults, not fixed. Different tasks need
  different splits (bootstrapping vs. deep debugging vs. historical lookup).
  `build_context()` accepts overrides.

- TF-IDF needs corpus scale to work. For term extraction during coalescing,
  the LLM suggests distinctive terms early on. TF-IDF becomes a supplementary
  signal once the corpus passes ~100 items.

- If Weft owns background execution, Engram should store item-processing state,
  not invent a second task queue. Status and retry surfaces can stay, but they
  should speak in terms of item state and Weft submissions rather than
  synthesized Engram tasks.

- Do not add backwards-compatibility layers for renamed public surfaces. Move
  code, tests, docs, and dogfood users to the canonical path in one change.
  Parallel aliases hide bugs and make architecture tests less meaningful.

### Scaffold Lessons (inherited)

- Stable human-facing path strings need an explicit formatter. Native
  `str(Path(...))` and bare `Path.relative_to(...)` are fine for local path
  objects, but CLI or release-helper output that is asserted across platforms
  must either use a stable formatter such as `.as_posix()` or be compared as
  `Path` objects in tests. Otherwise Windows will keep finding the seams.

- Keep canonical agent guidance in shared repo-owned docs and make root agent
  files point to that context instead of carrying divergent copies.
- Non-trivial plans must be executable by a zero-context engineer: exact
  source references, exact files, invariants, verification commands, and a
  fresh-eyes review are required.
- Specs define intended behavior; implementation docs explain why the current
  design exists. Blending those roles causes drift.
- Documentation maintenance is part of the completion gate. If code changes
  without plan/spec/implementation alignment, the work is incomplete.
- Optimize docs for agent usability, not just human readability. If something
  is human-clear but agent-ambiguous, call it out and suggest a specific fix.
