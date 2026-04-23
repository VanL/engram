# Engram - Agent Entry Point

## Shared Agent Context

Canonical shared context lives in `docs/agent-context/`.

Required read order for any agent operating in this repository:

1. `docs/agent-context/README.md`
2. `docs/agent-context/decision-hierarchy.md`
3. `docs/agent-context/principles.md`
4. `docs/agent-context/engineering-principles.md`
5. Relevant runbook(s) in `docs/agent-context/runbooks/`
6. `docs/agent-context/lessons.md`
7. `docs/lessons.md`

If local defaults conflict with repository guidance, follow the decision policy
in `docs/agent-context/decision-hierarchy.md`.

## 1. Orientation

**What**: Hierarchical memory for AI agents.
**Tagline**: Multi-horizon context without conversation replay.

**When to use engram**:
- Agents that need persistent memory across invocations
- One-shot agents that need situational awareness at multiple time horizons
- Systems that need structured forgetting with decay and importance weighting
- Context assembly that budgets a finite token window across time horizons

**Current state**: First usable local-app slice implemented. Foundation
contracts, public surface roles, and architecture guardrails are defined in
`docs/specs/15-foundation-contracts-and-invariants.md`.

## 1.1 Design Philosophy

Engram is a memory system where **tiered summarization serves context
assembly, not retrieval**. Hybrid search (BM25 + vector) handles finding
specific memories. The tier hierarchy (moments -> episodes -> arcs) exists
to budget a finite context window across time horizons: immediate, short-term,
medium-term, and long-term.

**What this means for you:**

- **Two storage layers by design.** LanceDB handles retrieval (read-heavy,
  search-oriented). SQLite/PG handles state (write-heavy, transactional --
  access scores, decay sweeps, coalescing state, parent-child traversal).
  Same ID space, cross-referenced. Don't try to make one layer do both jobs.

- **Coalescing is lossy and intentional.** Episode summaries lose detail.
  That's the point -- structured forgetting for a finite context window.
  The original moments are always available via search for drill-down.
  Summaries must preserve distinctive terms (TF-IDF extracted) so they
  serve as retrieval cues back to the original moments.

- **Semantic boundaries, not counters.** Episodes close when the topic
  shifts (detected via embedding similarity to running centroid), not after
  a fixed number of moments. A maximum window size acts as a ceiling, not
  a trigger.

- **Access scoring is multiplicative.** `score = access * relevance`.
  Access increments on use and decays over time. Relevance is the stored
  importance multiplier (default 1.0). This means hot+important dominates,
  cold+important has a floor, and cold+ordinary fades but never to zero (decay
  has a floor).

- **Specs are truth, everything else is context.** Specs in `docs/specs/`
  are the authoritative source for behavior. Plans in `docs/plans/` are
  non-normative execution records. Don't treat plans as backlog.

- **Don't infer -- read.** The most common agent mistake is applying generic
  heuristics without reading the specific code. Evaluate whether the code is
  consistent with *its own philosophy*, not whether it matches generic patterns.

## 1.2 If You're New Here

You are a skilled developer with limited context. Keep changes small,
grounded in the specs, and tested. Avoid "clever" abstractions.

**Where to start**:
1. Read this file (you're doing it).
2. Read `README.md` for the full mental model.
3. Read `engram/_constants.py` for all configuration and defaults.
4. (When specs exist) Read `docs/specs/` for intended behavior.

**Key principle**: The two-storage-layer split (LanceDB for retrieval,
SQLite/PG for state) is a core architectural decision, not a temporary
arrangement. Both layers use state-store-allocated hybrid timestamp IDs as the
shared key space. These IDs are format-compatible with `time.time_ns()` while
using low-order bits for a logical counter. Moments get clock-allocated IDs;
summaries get support-anchored IDs immediately after the child IDs they
summarize.

## 2. Architecture

```
Agent --> engram.record(text) --> Moment stored
                                       |
                              +--------+--------+
                              |                  |
                         State Store        Retrieval Index
                        (SQLite / PG)        (LanceDB)
                              |                  |
                         access scores      BM25 + vectors
                         parent/child       hybrid search
                         coalesce state     tag embeddings
                         blob registry
                         config
                              |                  |
                              +--------+---------+
                                       |
Agent <-- engram.context() <----- Context Assembly
```

**Key files**:
| File | Purpose |
|------|---------|
| `engram/__init__.py` | Package entry, public API |
| `engram/_constants.py` | All constants, defaults, env var loading |
| `engram/client.py` | Default app/tool client surface |
| `engram/commands/memory.py` | Shared command layer for CLI, client, tools, dogfood |
| `engram/cli.py` | CLI entry point (`engram` command) |
| `engram/core/memory.py` | Low-level domain object |
| `engram/runtime/weft.py` | Embedded Weft init and internal task submission |
| `engram/background.py` | Weft worker callback boundary |
| `engram/store/sqlite.py` | Public SQLite store wrapper |
| `engram/store/core.py` | Backend-neutral state operations |
| `engram/store/db.py` | SQL runner, retry, transaction, and SQLite connection primitives |
| `engram/store/id_generator.py` | Hybrid timestamp memory ID allocator |
| `engram/store/backends/sqlite/schema.py` | SQLite schema creation, verification, and forward migrations |
| `engram/store/_sql/sqlite.py` | SQLite SQL namespace and ordered column lists |
| `engram/index/lance.py` | Rebuildable LanceDB retrieval projection |

**Tier hierarchy**:
| Depth | Name | Content |
|-------|------|---------|
| 0 | Moment | Raw text + timestamp |
| 1 | Episode | Summary of semantically coherent moment sequence |
| 2 | Arc | Summary-of-summaries spanning episodes |
| 3+ | Extensible | Epoch, or tier-{n} |

**CLI and API are coextensive**:
| CLI | API equivalent |
|-----|---------------|
| `engram init` | `EngramClient.init(path)` / `Engram.init(path)` |
| `engram record [--importance INT] "text"` | `client.record("text", importance=INT)` / `memory.record("text", importance=INT)` |
| `engram recall MID` | `client.recall(MID)` / `memory.recall(MID)` |
| `engram recall episode MID` | `client.recall(MID, scope="episode")` / `memory.recall(MID, scope="episode")` |
| `engram recall arc MID` | `client.recall(MID, scope="arc")` / `memory.recall(MID, scope="arc")` |
| `engram recall 2 MID` | `client.recall(MID, scope=2)` / `memory.recall(MID, scope=2)` |
| `engram context` | `client.context()` / `memory.build_context()` |
| `engram search "query"` | `client.search("query")` / `memory.search("query")` |
| `engram set-importance MID 5` | `client.set_importance(MID, 5)` / `memory.set_importance(MID, importance=5)` |
| `engram vault status` | `client.status()` / `memory.status()` |
| `engram vault rebuild-index` | `memory.rebuild_index()` |
| `engram vault process` | `client.process()` / `memory.process()` |

Do not add backwards-compatibility aliases for renamed public surfaces. Move
all repo users to the canonical path in the same change.

**Vaults**: Each engram instance is a **vault** -- an isolated memory
namespace with its own data directory, state store, and retrieval index.
`engram init` creates a vault. `engram --vault PATH` targets a specific one.
Multiple vaults can coexist.

**Storage split**:
| Concern | Where |
|---------|-------|
| Vector search, BM25 FTS, hybrid retrieval | LanceDB |
| Access scores, decay sweeps | SQLite/PG |
| Parent-child relationships | SQLite/PG |
| Coalescing state machine | SQLite/PG |
| Blob registry | SQLite/PG |
| Configuration | SQLite/PG |
| Tag embeddings | LanceDB |

## 3. Invariants

**NEVER break**:
- IDs are non-negative hybrid timestamp integers, unique, immutable after
  creation, and allocated by the state store
- Moments are immutable after storage (text, embedding, created_at never change)
- Summary IDs and `created_at` values are anchored to their support sets, not
  to processing time
- Tier 0 (moments) are never deleted by coalescing -- summaries are additive
- Access scores are non-negative (decay has a floor)
- Relevance multiplier defaults to 1.0 and is never less than 1.0
- Both storage layers share the same ID space
- SQLite/PG is the source of truth; LanceDB is a rebuildable index

**Safe to change**:
- Default values for coalescing thresholds, decay rates, context budgets
- Embedding model (requires re-indexing)
- Tag generation prompts
- Context assembly formatting
- CLI command names/flags

**Gotchas**:
- `record()` returns as soon as the moment is queued in the state store.
  Embedding, LanceDB indexing, and coalescing happen asynchronously. Frontend
  retrieval never blocks on background operations.
- If the two storage layers become inconsistent (partial write failure),
  background retries reconcile. The state store is always the source of truth.
- Context assembly (inclusion in assembled context) does NOT increment access
  scores. Only explicit retrieval (search, direct recall) counts. This
  prevents a feedback loop where items in context perpetually boost themselves.
- LanceDB is append-optimized. Frequent point updates (access scores) live
  in SQLite/PG, not LanceDB.
- TF-IDF is not useful for term extraction until the corpus is large enough
  to have meaningful document frequencies. Early on, the LLM suggests
  distinctive terms for coalescing prompts. TF-IDF supplements as a factor
  as the corpus grows.

## 4. House Style

### 4.1 File Organization

```
engram/
├── _constants.py       # ALL constants, env vars, config loading
├── _exceptions.py      # Custom exceptions (when needed)
├── __init__.py         # Package entry, public API
├── cli.py              # CLI entry point (argparse-based)
├── runtime/            # Embedded runtime integrations
│   └── weft.py         # Weft init and internal task submission
├── core/               # Business logic
│   ├── memory.py       # Main Engram class
│   ├── coalesce.py     # Coalescing logic
│   ├── context.py      # Context assembly
│   └── scoring.py      # Access scoring and decay
├── store/              # State store (SQLite/PG)
│   ├── base.py         # Store protocol/interface
│   ├── sqlite.py       # Public SQLite store wrapper
│   ├── core.py         # Backend-neutral store operations
│   ├── db.py           # SQL runner and transaction primitives
│   ├── factory.py      # Backend selection boundary
│   ├── id_generator.py # Hybrid timestamp ID allocator
│   ├── _sql/           # Backend SQL namespaces
│   └── backends/       # Backend runtime/schema/validation adapters
└── index/              # Retrieval index (LanceDB)
    └── lance.py        # LanceDB wrapper
```

### 4.2 Imports

```python
"""Module docstring with spec references [EG-1], [EG-2]."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, Field, field_validator

from engram._constants import (
    DEFAULT_CONTEXT_TOKENS,
    TIER_MOMENT,
)
```

**Rules**:
- `from __future__ import annotations` in every file
- All imports at top of module (no late imports; avoid import loops by design)
- Group: stdlib -> third-party -> local, alphabetized within groups
- Use `collections.abc` for abstract types (Callable, Iterator, Mapping, Sequence)
- Use `Path` from pathlib, never `os.path`
- No wildcard imports except in `__init__.py` for re-exports

### 4.3 Type Hints

```python
# Good
def process(data: str | None = None) -> dict[str, Any]: ...
def fetch(ids: list[int]) -> Sequence[Result]: ...
callback: Callable[[str, int], bool]

# Bad
def process(data: Optional[str] = None) -> Dict[str, Any]: ...
from typing import List, Dict, Optional  # Don't import these
```

**Rules**:
- `X | None` not `Optional[X]`
- `list[T]`, `dict[K, V]`, `set[T]` not `List`, `Dict`, `Set`
- `Callable`, `Iterator`, `Mapping`, `Sequence` from `collections.abc`
- `Final[T]` for constants
- `Literal["a", "b"]` for constrained strings
- All functions must have complete type annotations (enforced by mypy)

### 4.4 Constants

All constants live in `_constants.py`, grouped by purpose with docstrings:

```python
from typing import Any, Final

DECAY_FACTOR: Final[float] = 0.95
"""Multiplicative decay applied to access scores periodically.
0.95 means 5% decay per sweep.  After 20 sweeps, score is ~36% of peak."""
```

### 4.5 Docstrings

Structured docstrings with spec references:

```python
def resolve_tier(depth: int) -> str:
    """Return the human-readable name for a tier depth.

    Args:
        depth: Tier depth (0=moment, 1=episode, 2=arc, 3+=extensible).

    Returns:
        Canonical tier name string.

    Example:
        >>> resolve_tier(0)
        'moment'

    Spec: [EG-1.2]
    """
```

Module docstrings include spec references:
```python
"""Context assembly for multi-horizon agent context.

This module builds token-budgeted context views across time horizons:
immediate (recent moments), short-term (episodes), medium-term (arcs),
and long-term (high-importance retained items).

Spec references:
- docs/specs/XX-context-assembly.md [CA-1], [CA-2]
"""
```

### 4.6 Data Modeling

**Pydantic for validated structured data** (moments, episodes, configuration):
```python
from pydantic import BaseModel, Field, field_validator

class Moment(BaseModel):
    """A raw unit of experience in the memory system."""

    id: int = Field(..., ge=0, description="Shared hybrid timestamp ID")
    text: str = Field(..., min_length=1, description="Content text")
    tier: int = Field(0, ge=0, description="Tier depth")
    created_at: int = Field(..., description="Memory timeline timestamp (ns)")
```

**Dataclasses for simple immutable values**:
```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single result from hybrid search."""
    id: int
    text: str
    tier: int
    score: float
    source: str  # "bm25" | "vector" | "hybrid"
```

**Protocol for duck-typed interfaces**:
```python
from typing import Protocol

class StateStore(Protocol):
    """Interface for the state storage backend."""

    def put_moment(self, moment: Moment) -> None: ...
    def get(self, id: int) -> Moment | None: ...
    def increment_access(self, id: int) -> None: ...
    def decay_all(self, factor: float, floor: float) -> int: ...
```

### 4.7 Error Handling

```python
class EngramError(Exception):
    """Base exception for all Engram errors."""
    pass

class MomentNotFoundError(EngramError, KeyError):
    """Raised when a moment/episode/arc ID is not found."""
    def __init__(self, id: int, tier: int | None = None) -> None:
        tier_str = f" (tier {tier})" if tier is not None else ""
        super().__init__(f"Memory item {id}{tier_str} not found")
        self.id = id
        self.tier = tier

class StoreConsistencyError(EngramError, RuntimeError):
    """Raised when state store and retrieval index are inconsistent."""
    pass
```

Defensive exception handling:
```python
# Mark defensive catches with pragma
try:
    risky_operation()
except Exception:  # pragma: no cover - defensive
    logger.debug("Operation failed", exc_info=True)
```

### 4.8 Testing

```
tests/
├── conftest.py          # Shared fixtures
├── core/
│   ├── test_memory.py
│   ├── test_coalesce.py
│   ├── test_context.py
│   └── test_scoring.py
├── store/
│   ├── test_sqlite.py
│   └── test_pg.py
└── index/
    └── test_lance.py
```

**Preferred patterns**:
- Assert observable behavior (search results, context output, score changes)
- Use real SQLite and LanceDB for integration tests (they're fast, in-process)
- Mock LLM calls for coalescing (external, slow, nondeterministic)
- Minimize timing flakiness (deterministic inputs when possible)
- Test coalescing summary quality with retrieval round-trip: can you find
  constituent moments by searching with terms from the summary?

### 4.9 Logging

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Moment stored", extra={"id": mid, "tier": 0})
logger.debug("Coalescing window", extra={"size": len(window), "centroid_sim": sim})
logger.error("Store inconsistency", extra={"id": mid, "error": str(e)}, exc_info=True)
```

### 4.10 Security

**Path validation** at boundaries:
```python
def validate_safe_path(path: str) -> str:
    """Validate path is safe for use."""
    if ".." in path:
        raise ValueError(f"Path contains traversal: {path}")
    dangerous = set(';&|`$(){}[]<>"\'\\')
    if any(c in path for c in dangerous):
        raise ValueError(f"Path contains shell metacharacters: {path}")
    return path
```

## 5. Common Tasks

### Development

```bash
. ./.envrc                       # Or direnv allow
uv sync --all-extras             # Install dev tools
./.venv/bin/python -m pytest     # Fast tests only
./.venv/bin/python -m pytest -m ""  # All tests including slow
./.venv/bin/mypy engram          # Type check
./.venv/bin/ruff check engram    # Lint
```

Do not assume `pytest`, `mypy`, or `ruff` are installed globally. Load
`.envrc` first, then use the in-repo virtualenv binaries.

### Implementation Loop

1. Read the spec + current code that matches your change.
2. Identify the smallest testable change.
3. Write/adjust a test (TDD preferred, be pragmatic).
4. Implement the change.
5. Run the smallest relevant test(s), then expand.

## 6. Project Conventions

- Specs live in `docs/specs/`.
- Plans live in `docs/plans/` (filename: `YYYY-MM-DD-<descriptive-name>.md`).
- Plans are non-normative. Specs in `docs/specs/` are the source of truth.
- Durable lessons live in `docs/lessons.md`.
- Documentation maintenance is part of the definition of done.
- Non-trivial changes start with a dated plan.
- Risky changes also read `docs/agent-context/runbooks/hardening-plans.md`.
- Do not introduce new abstractions unless forced by duplication.
- Do not "future-proof" unless the spec explicitly requires it.

## 7. Handoff Protocol

**Before claiming "done"**:
- [ ] Tests pass
- [ ] Type check passes (`mypy engram`)
- [ ] Lint passes (`ruff check engram`)
- [ ] Changes are minimal (no drive-by refactoring)

**When stuck**: State what you tried, what failed, ask specific question.

**When handing off**: Summarize done, list remaining, note gotchas, update
`docs/lessons.md` if a correction exposed a repeated pattern.

## 8. Agent Boundaries

**Do freely**: Read any file, run tests, make targeted edits, add tests.

**Ask first**: Architectural changes, new dependencies, changes to public API,
deleting files.

**Don't do**: Push to git, modify CI/CD, change project config without
discussion, "improve" unrelated code.
