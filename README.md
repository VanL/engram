# Engram

**Hierarchical memory for AI agents.**

Engram gives one-shot agents persistent, multi-horizon context -- what you're
doing now, what you just did, the broader workstream, and important background
-- without replaying entire conversation histories.

## Current Status

The repository now has a first usable local-app slice:

- local vaults
- text moments
- episode coalescing
- arc coalescing
- SQLite state store
- LanceDB hybrid retrieval
- importance updates
- direct recall
- multi-horizon context assembly
- Weft-backed background processing
- status inspection
- optional local repair tooling via `engram vault process`
- one-way `vault rebuild-index` recovery from SQLite into LanceDB
- shared command layer and `EngramClient` for programmatic/tool use

Still deferred:

- blobs
- deletion
- dump/load
- Postgres backend
- always-on worker orchestration beyond Weft submission

The code is intentionally at the "validate the thesis" stage, not the "full
app shipped" stage.

## The Problem

An agent invoked with a one-shot prompt has no memory. The standard fix is
replaying the full conversation, which is expensive (O(n) tokens, all weighted
equally) and noisy. Truncating to the last N messages is cheap but amnesiac.
RAG over a flat store finds specific facts but gives no situational awareness.

The sections below describe the target design. The "Current Status" section
above is the source of truth for what is implemented today.

## The Approach

Engram maintains a **tiered memory** modeled on how human memory works:

| Tier | Name | What it holds |
|------|------|---------------|
| 0 | **Moment** | Raw unit of experience -- a timestamp and some text |
| 1 | **Episode** | Summary of a semantically coherent sequence of moments |
| 2 | **Arc** | Summary-of-summaries spanning multiple episodes |
| 3+ | Extensible | Additional tiers (e.g., **Epoch**) via depth parameter |

All tiers above moment share the same schema. Coalescing (summarization into
the next tier) happens at **semantic boundaries**, not fixed counts -- when the
topic shifts, the episode closes. A configurable maximum window size acts as a
ceiling.

### Context Assembly

A context is built by budgeting a finite token window across time horizons.
The defaults:

```
[immediate]   recent moments, verbatim           ~40%
[short-term]  recent episodes                     ~25%
[medium-term] relevant arcs                       ~20%
[long-term]   high-importance retained items      ~15%
```

These are starting defaults, not fixed allocations. `build_context()` accepts
custom splits and optional search terms to bias the assembly:

```python
# Default: balanced multi-horizon context
context = memory.build_context()

# Focused: weight toward long-term, filtered by topic
context = memory.build_context(term="sqlite", long_term=0.40)
```

The agent gets situational awareness at every scale. Hybrid search (BM25 +
vector) is the fallback for drill-down into specific memories.

### Retrieval

Engram uses **hybrid search** combining:
- **BM25 keyword search** for exact term matching (via LanceDB native FTS)
- **Vector similarity** for semantic/conceptual matching (Lance-managed
  embeddings in LanceDB)
- **Access-weighted scoring** to surface hot and important items

Results from BM25 and vector search are merged via Reciprocal Rank Fusion,
then boosted by `access * relevance` to promote important items without
polluting unrelated queries.

### Access Scoring and Decay

Every time an agent explicitly retrieves a memory item, its access score
increments. Periodically, all scores decay multiplicatively. Items can receive
an importance multiplier (default 1.0) that acts as a floor. Structurally
important decisions do not fade below retrieval threshold as quickly.

Note: being included in an assembled context does **not** increment access
scores. Only explicit retrieval (search, direct recall) counts. This prevents
a feedback loop where items in context perpetually boost themselves.

This naturally handles contradiction: when migrating from PostgreSQL to SQLite,
both items are hot during cutover. Over time, the new system dominates because
it keeps getting accessed while the old decision decays.

### Associative Links

Items carry tags -- lightweight associative links. At write time, the LLM
suggests tags (the corpus is too small for statistical methods early on). As
the corpus grows, TF-IDF can supplement the LLM as an additional signal. Tags
are stored as embeddings and clustered, avoiding the controlled-vocabulary
problem ("auth" and "authentication" are the same cluster without string
normalization).

Tags are periodically refined with hindsight -- only items that appeared in
recent retrieval results are re-tagged, not the full corpus.

### Blobs

Binary content (images, PDFs, code files) is stored externally and represented
in Engram as a moment containing an LLM-generated summary. The summary is the
searchable proxy; the blob itself is never in the index. Content-hashed for
dedup. Blobs get a higher default relevance floor because explicit attachment
signals importance.

## Architecture

```
Agent --> engram record "text" --> Moment stored + Weft task submitted
                                             |
                                   +---------+---------+
                                   |                   |
                              State Store         Retrieval Index
                                 (SQLite)           (LanceDB)
                                   |                   |
                              access scores       BM25 + vectors
                              parent/child        hybrid search
                              lag + failure       embeddings
                              vault metadata
                                   |                   |
                                   +---------+---------+
                                             |
Agent <-- engram context <----------- Context Assembly
```

**Two storage layers, one ID space:**
- **LanceDB** -- retrieval index. Read-heavy, search-oriented. Stores text,
  embeddings, embedding-function metadata, and search state for hybrid search.
- **SQLite/PG** -- state store. Write-heavy, transactional. Handles access
  score updates, decay sweeps, parent-child traversal, coalescing state,
  blob registry, and configuration. Dual-backend: SQLite for local use,
  Postgres for shared/production.

SQLite/PG is the source of truth. LanceDB is a rebuildable index.

IDs are state-store-allocated hybrid timestamp integers, shared across both
stores. They are format-compatible with `time.time_ns()` values: nanosecond
epoch integers, with low-order bits reserved for a logical counter. Moments get
clock-allocated IDs. Episodes, arcs, and higher summaries are derived items, so
their IDs are anchored immediately after the child IDs they summarize.
`created_at` is the memory timeline timestamp: physical creation time for
moments, max child `created_at` for summaries.

### Async by Default

`record()` returns as soon as the moment is stored in SQLite and a Weft task
is submitted. Embedding, LanceDB upsert, and coalescing happen asynchronously
in the background. Frontend retrieval never blocks on background operations.
If the two storage layers become inconsistent (partial write failure), SQLite
remains authoritative and LanceDB can be rebuilt.

For the default local sqlite-backed path, Engram-owned Weft runtime state also
lives inside the vault directory. That keeps Engram's background broker state
separate from an ordinary project `.weft/` directory.

Embedded Weft settings should use the Engram env namespace: plain `ENGRAM_*`
where names do not collide with Engram's own app config, and `ENGRAM_WEFT_*`
for the few conflicting names such as backend and debug. Engram translates that
surface into Weft's config for the embedded runtime while still deriving the
embedded metadata directory name and default sqlite broker path from the vault
path.

### Namespacing

Each engram instance is a **vault** -- an isolated memory namespace with its
own data directory, state store, and retrieval index.

```bash
engram init                        # Initialize a vault in ./.engram/
engram --vault /other/project record "..."
```

Multiple vaults can coexist. Agents specify which vault to use.

In the current app slice, `engram init` creates a vault. Other CLI commands
expect an existing initialized vault and do not silently create one.
It also initializes the embedded Weft project for that vault, which puts the
default broker at `.engram/broker.db`.

## Quick Start

### CLI (`engram`)

```bash
engram init                                   # Initialize a vault
engram record "Decided to use JWT for auth"  # Store a moment
engram record --importance 5 "Ship decision" # Store a high-importance moment
engram record "SQLite wins for our scale"    # Store another
engram vault status                            # Inspect domain lag, failures, and index drift
engram vault process                           # Local repair helper for lagging or failed items
engram vault rebuild-index                     # Restore LanceDB from SQLite
engram context                                 # Build multi-horizon context
engram search "auth"                           # Search for specific memories
engram set-importance <id> 5                   # Update importance for an existing item
engram recall <id>                             # Read a specific item
engram recall episode <mid>                    # Read the episode containing a MID
engram recall arc <mid>                        # Read the arc containing a MID
engram recall 2 <mid>                          # Read the tier-2 summary containing a MID
```

Commands that need machine-readable output support `--json`, for example
`engram search "auth" --json` and `engram vault status --json`.

`record --importance INT` sets the initial importance for a moment. Internally
this uses the existing relevance multiplier; `set-importance` updates that
multiplier after a moment already exists.

### Python API

```python
from engram import Engram, EngramClient

# Default app/tool surface: initialize the vault once
client = EngramClient.init()

# Later sessions: reopen the existing vault
# client = EngramClient.open()

# Record something (returns immediately; indexing is async)
client.record("Decided to use JWT for API authentication")
client.record(
    "Benchmarked SQLite vs PostgreSQL -- SQLite wins for our scale",
    importance=5,
)

# Optional local repair/test helper
client.process()

# Inspect vault and recovery state
print(client.status())

# Build context for an agent (default budget split)
context = client.context()
print(context)

# Build context focused on a topic
context = client.context(query="sqlite")

# Search for specific memories
results = client.search("authentication approach")

# Recall a specific item or containing summary
item = client.recall(results[0]["id"])
episode = client.recall(results[0]["id"], scope="episode")
arc = client.recall(results[0]["id"], scope="arc")
same_arc = client.recall(results[0]["id"], scope=2)

# Thin client surface for read-only LLM tools
tools = client.llm_tools()
client.close()
```

Use the lower-level `Engram` domain object when writing Engram internals or
tests that need direct access to typed models:

```python
from engram import Engram

memory = Engram.init()
moment_id = memory.record("Important local decision.", importance=5)
memory.process()
memory.set_importance(moment_id, importance=5)

# Recall a specific item or containing summary
memory.recall(moment_id, count_access=False)
memory.recall(moment_id, scope="episode", count_access=False)
memory.recall(moment_id, scope="arc", count_access=False)
memory.recall(moment_id, scope=2, count_access=False)

# Restore LanceDB from authoritative SQLite state
memory.rebuild_index()
memory.close()
```

## Dependencies

The current validation slice depends on:

- **LanceDB** + **PyArrow** -- hybrid search index (BM25 + vector), columnar
  storage.
- **Pydantic** -- data validation.
- **weft** -- background task execution.
- **llm** + Gemini plugin -- structured summary and keyword extraction.
- **sentence-transformers** -- the default Lance embedding-function backend.
- **SQLite** -- authoritative local state store (via stdlib `sqlite3`).

The local repair path still exists for tests and operator recovery, but it is
not the primary background path. Weft owns execution and queueing.

## Key Design Decisions

**Why tiered summarization?**
Not for retrieval (hybrid search handles that) -- for **context assembly**. A
finite context window needs structured forgetting. The hierarchy budgets token
space across time horizons so the agent gets situational awareness, not just
search results.

**Why LanceDB?**
Embedded, hybrid BM25+vector search with fusion and reranking built in.
Arrow-columnar storage. No server to run. The search features it bundles
would otherwise require wiring together multiple libraries (tantivy, hnswlib,
a fusion layer).

Lance also owns the dense-retrieval embedding path in the current app slice.
Engram reuses that same embedding function for semantic-boundary coalescing so
retrieval and coalescing stay on one model family instead of drifting.

**Why a separate state store?**
LanceDB is append-optimized. Frequent point updates (access score increments,
decay sweeps) and transactional operations (coalescing state machines,
parent-child traversal) need a relational store. SQLite for local, Postgres
when you need shared access.

**Why semantic boundaries for coalescing?**
Fixed-N windowing ignores topic shifts -- you get episodes that split coherent
threads or jam unrelated topics together. Detecting topic shifts (via embedding
similarity to running centroid) gives semantically coherent episodes that map
to natural units of work.

**Why multiplicative relevance scoring?**
Additive (`access + relevance`) makes an important item and a hot item look the
same. Multiplicative (`access * relevance`) means an important item that is also
hot dominates, while an important cold item still has a floor.

**Why LLM-suggested terms instead of TF-IDF for anchoring summaries?**
TF-IDF needs a corpus to compute meaningful IDF scores. Early on, the corpus
is tiny and IDF is noise. The LLM is better at identifying distinctive terms
from a small window. As the corpus grows, TF-IDF becomes a useful
supplementary signal, but the LLM is the primary term extractor.

**Why async writes via weft?**
`record()` must be fast. Embedding computation, LanceDB indexing, and
coalescing are all heavier operations that should not block the caller. The
state store gets the moment synchronously (source of truth); everything else
runs as weft tasks in the background -- with retry, timeout, observability,
and resource limits built in. No need to build a second task substrate.

## Development

```bash
. ./.envrc                       # Or direnv allow
uv sync --all-extras             # Install dev tools
./.venv/bin/python -m pytest     # Run tests
./.venv/bin/mypy engram          # Type check
./.venv/bin/ruff check engram    # Lint
```

## Project Status

The repo now has a real local app slice: write, search, status, rebuild,
episodes, arcs, and multi-horizon context assembly, plus a labeled validation
corpus that compares Engram against a same-budget last-N baseline.

## License

MIT License. See [LICENSE](LICENSE) for details.
