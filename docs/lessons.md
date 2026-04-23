# Lessons Learned

Use this file for durable, project-level lessons that should influence future
sessions.

## When To Add A Lesson

- A correction exposed a repeated failure mode.
- A missing document or runbook caused rework.
- A plan or spec was too ambiguous to execute safely.
- A completed change revealed a stronger general rule than the repo previously
  encoded.

## Lessons

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
