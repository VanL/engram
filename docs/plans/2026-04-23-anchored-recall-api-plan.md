# 2026-04-23 Anchored Recall API Plan

Status: Implemented

Verification:

- `uv run ruff check --fix engram tests`
- `uv run ruff format engram tests`
- `uv run pytest`
- `uv run mypy engram`
- `uv run ruff check engram tests`
- `uv run ruff format --check engram tests`

Second review:

- `agent-mcp` / Claude review completed with no blocking findings.

## 1. Goal

Replace the current tier-named direct-read public surface with a single recall
surface:

```text
engram recall MID
engram recall episode MID
engram recall arc MID
```

The API meaning is:

- `recall MID`: return the exact memory item with that ID, regardless of tier.
- `recall episode MID`: return the episode whose support range contains `MID`.
- `recall arc MID`: return the arc whose support range contains `MID`.

This change is not a compatibility layer. Remove the old public paths in the
same change:

- CLI: remove `engram moment`, `engram episode`, and `engram arc`.
- Command/client: replace public `lookup` with public `recall`.
- Domain public API: replace public tier helper methods `moment()`,
  `episode()`, and `arc()` with `recall(..., scope=...)`.

Keep storage vocabulary storage-shaped. `StateStore.get_item()` remains the
right name for exact row fetches because the store is not a product API. The
public memory API should speak user intent: recall.

## 2. Source Documents

Read these before editing code:

- `AGENTS.md`
- `README.md`
- `docs/agent-context/README.md`
- `docs/agent-context/decision-hierarchy.md`
- `docs/agent-context/principles.md`
- `docs/agent-context/engineering-principles.md`
- `docs/agent-context/runbooks/writing-plans.md`
- `docs/agent-context/runbooks/hardening-plans.md`
- `docs/agent-context/runbooks/testing-patterns.md`
- `docs/agent-context/runbooks/maintaining-traceability.md`
- `docs/agent-context/lessons.md`
- `docs/lessons.md`

Normative specs to update with this change:

- `docs/specs/10-minimum-memory-model.md`
  - Summary IDs and `created_at` are already support-anchored. Add the
    state-store requirement that parent-child links support exact parent
    lookup and support-range containment queries.
- `docs/specs/11-minimum-write-search-context-slice.md`
  - Update explicit retrieval language from lookup to recall.
  - Update the minimum CLI/API surface.
- `docs/specs/12-local-app-surface.md`
  - Update public surface language from lookup to recall.
- `docs/specs/15-foundation-contracts-and-invariants.md`
  - Update public API roles, access-score mutation language, command output
    contracts, and no-compatibility guardrails.

Related plans and context:

- `docs/plans/2026-04-23-support-anchored-summary-mids-plan.md`
  - Status is implemented.
  - This plan depends on its core invariant: summary IDs are support anchored.
- `docs/plans/2026-04-23-api-vocabulary-process-set-importance-plan.md`
  - Follow the same no-backwards-compatibility approach.
- `docs/implementation/04-minimum-memory-slice.md`
  - Update the surface mapping table and LLM tool language.
- `docs/implementation/06-arc-context-assembly.md`
  - Update references to arc lookup.

## 3. Current Context

### Current Public Surface

The current CLI exposes:

```text
engram moment ID
engram episode ID
engram arc ID
```

Those commands are directionally too narrow. They require the caller to know
which tier the ID belongs to and they cannot express the useful operation we
now want: find the summary tier that contains an anchor MID.

The current client exposes:

```python
client.lookup(item_id)
```

The current domain object exposes:

```python
memory.lookup(item_id, tier=None)
memory.moment(item_id)
memory.episode(item_id)
memory.arc(item_id)
```

This plan changes the public vocabulary to recall. Do not keep aliases.

### Existing Storage Support

The store already records ordered backlinks:

```text
memory_edges(parent_id, child_id, position)
```

The current state-store SQL includes:

- `idx_memory_edges_child_id`
- `idx_memory_edges_parent_position`

That is enough for exact parent lookup and support-range containment. Do not
change the schema for this work.

The current summary allocation behavior is already support anchored:

- For non-empty `child_ids`, summary ID is the first unused ID greater than
  `max(child_ids)`.
- For non-empty `child_ids`, summary `created_at` is
  `max(child.created_at)`.

This matters because `recall episode 2000` should be a timeline operation over
support, not a row lookup against tier 1 item ID `2000`.

### Target Mental Model

Recall has two modes:

1. Exact recall:

   ```text
   recall MID
   ```

   Fetch the item whose ID is exactly `MID`. It may be a moment, episode, arc,
   or later higher-tier item.

2. Anchored summary recall:

   ```text
   recall episode MID
   recall arc MID
   ```

   Treat `MID` as an anchor in memory time. Return the summary at the requested
   tier whose ordered support range contains that anchor.

The support graph is authoritative. Do not infer containment only from summary
IDs. Summary IDs are a helpful projection, but collision skipping means the
only correct source of support membership is `memory_edges` plus the child item
IDs.

Example:

```text
episode A summarizes moments through MID 1000
episode B summarizes moments through MID 3000

engram recall episode 2000
```

The answer is episode B because `1000 < 2000 <= 3000` in the support timeline.
Operationally, compute this from episode child ranges, not from hard-coded
summary-boundary math.

## 4. Target API

### CLI

Add:

```text
engram recall ID [--json]
engram recall episode ID [--json]
engram recall arc ID [--json]
```

Remove:

```text
engram moment ID
engram episode ID
engram arc ID
```

Do not add hidden aliases. Old commands should fail at argparse level with
exit code `2`.

Output:

- Default recall output remains JSON, matching the current `moment`,
  `episode`, and `arc` behavior.
- `--json` is accepted for consistency and explicit machine use. It produces
  the same item object.
- Returned item shape is exactly:

  ```text
  id
  tier
  text
  created_at
  access
  relevance
  indexed_at
  summary_terms
  ```

Invalid CLI shapes:

- `engram recall`
- `engram recall episode`
- `engram recall arc`
- `engram recall moment ID`
- `engram recall item ID`
- `engram recall ID extra`
- `engram recall not-an-int`
- `engram recall episode not-an-int`

These should fail with argparse exit code `2`, not with a stack trace.

Not found:

- Missing exact item returns `EXIT_NOT_FOUND`.
- No containing episode or arc returns `EXIT_NOT_FOUND`.

### Command Layer

Replace public command-layer lookup with recall:

```python
commands.recall(
    memory,
    item_id,
    *,
    scope="item",
    count_access=True,
) -> dict[str, Any] | None
```

Valid scopes:

- `"item"`: exact item recall.
- `"episode"`: containing episode recall.
- `"arc"`: containing arc recall.

Remove `commands.lookup` from `engram/commands/memory.py` and from
`engram/commands/__init__.py`. Tests should assert it is gone.

The command layer owns only:

- argument normalization for command-shaped inputs
- scope validation
- JSON-safe serialization

It must delegate actual recall behavior to `Engram.recall()`.

### Client

Replace public `EngramClient.lookup()` with:

```python
client.recall(
    item_id,
    *,
    scope="item",
    count_access=True,
) -> dict[str, Any] | None
```

Do not keep `client.lookup`.

Update `EngramClient.llm_tools()`:

- Replace `engram_lookup` with `engram_recall`.
- The tool must not increment access scores.
- Tool input schema should accept:

  ```json
  {
    "item_id": "string",
    "scope": "item | episode | arc"
  }
  ```

- `scope` should default to `"item"` if the LLM omits it.

This keeps model-facing tools aligned with the product API while preserving the
read-only tool invariant.

### Domain Object

Add public domain method:

```python
Engram.recall(
    item_id: int,
    *,
    scope: Literal["item", "episode", "arc"] = "item",
    count_access: bool = True,
) -> MemoryItem
```

Remove public tier helpers:

```python
Engram.moment()
Engram.episode()
Engram.arc()
```

Replace public `Engram.lookup()` with `Engram.recall(scope="item")`.

Do not leave `lookup()` as a public compatibility path. If the implementation
needs a private exact-row helper, use a private name such as
`_get_item_or_raise()`.

The domain object owns:

- exact recall behavior
- anchored episode recall behavior
- anchored arc recall behavior
- access-score mutation for returned items

It must not put domain traversal logic in the CLI, client, or command layer.

### Store

Add state-store methods that are storage-shaped, not product-shaped:

```python
StateStore.get_parent(child_id: int, *, parent_tier: int) -> MemoryItem | None

StateStore.find_summary_containing(
    anchor_id: int,
    *,
    parent_tier: int,
) -> MemoryItem | None
```

`get_parent()` finds the immediate parent at the requested tier for an exact
child ID.

`find_summary_containing()` finds a parent item whose immediate child ID range
contains an arbitrary anchor:

```text
MIN(child.id) <= anchor_id <= MAX(child.id)
```

For deterministic behavior when manually crafted overlapping support ranges
exist, return the lowest parent ID. Do not add overlap enforcement in this
change. Normal coalescing should not create overlapping same-tier parent
ranges, but explicit fixtures can.

## 5. Semantics

### `scope="item"`

Algorithm:

1. Fetch exact item by ID.
2. If missing, raise `MemoryItemNotFoundError(item_id)`.
3. If `count_access=True`, increment access for the returned item only.
4. Reload and return the item so the caller sees the updated access score.

This is the replacement for current public `lookup()`.

### `scope="episode"`

Algorithm:

1. If `anchor_id` is exactly an episode item, return that episode.
2. If `anchor_id` is exactly a moment item, check for its direct episode parent.
3. If no direct parent is found, find the episode whose moment-child support
   range contains `anchor_id`.
4. If no containing episode exists, raise `MemoryItemNotFoundError(anchor_id,
   tier=TIER_EPISODE)`.
5. If `count_access=True`, increment access for the returned episode only.

Important access invariant: do not increment access for the anchor moment when
the returned item is an episode.

### `scope="arc"`

Algorithm:

1. If `anchor_id` is exactly an arc item, return that arc.
2. If `anchor_id` is exactly an episode item, check for its direct arc parent.
3. If `anchor_id` is exactly a moment item, find its containing episode, then
   find that episode's arc parent.
4. If `anchor_id` is not an exact item, first find the containing episode by
   moment-child support range, then find that episode's arc parent.
5. If no episode path resolves an arc, try direct arc support-range containment
   over episode-child IDs. This covers callers who pass an episode-timeline
   anchor that is not an exact row.
6. If no containing arc exists, raise `MemoryItemNotFoundError(anchor_id,
   tier=TIER_ARC)`.
7. If `count_access=True`, increment access for the returned arc only.

Do not increment intermediate episode or moment access during traversal.

### Scope Validation

Valid public scopes are only:

```text
item
episode
arc
```

Do not implement `"moment"` scope. Exact recall already handles moments:

```text
engram recall MID
client.recall(mid)
memory.recall(mid)
```

Do not implement future tier names in this change. The tier system is
extensible, but this API should stay narrow until there is a tested product
need for higher-tier anchored recall.

## 6. Files To Touch

### Code

- `engram/_constants.py`
  - Add recall scope constants:
    - `RECALL_SCOPE_ITEM = "item"`
    - `RECALL_SCOPE_EPISODE = "episode"`
    - `RECALL_SCOPE_ARC = "arc"`
    - `RECALL_SCOPES = (...)`
  - Keep this minimal. Do not add a new config system or enum dependency.

- `engram/store/base.py`
  - Add `get_parent()` and `find_summary_containing()` to the protocol.

- `engram/store/core.py`
  - Implement `get_parent()`.
  - Implement `find_summary_containing()`.
  - Keep SQL in this store/core layer. Do not put it in `Engram`.

- `engram/store/sqlite.py`
  - Add thin delegation methods to `StateStoreCore`.
  - Keep this file adapter-thin.

- `engram/core/memory.py`
  - Add `Engram.recall()`.
  - Add private helpers for exact fetch, scoped traversal, and access counting.
  - Remove public `lookup()`, `moment()`, `episode()`, and `arc()`.
  - Update internal exact reads to use the private exact fetch helper.
  - Use public `recall()` only for public API behavior and tests that are
    intentionally exercising recall semantics.
  - Domain traversal belongs here, not in commands or CLI.

- `engram/commands/memory.py`
  - Replace `lookup()` with `recall()`.
  - Update `__all__`.
  - Ensure invalid scope raises `ValueError` with a message that names the
    invalid scope. CLI invalid scope should be caught earlier by parser
    validation.

- `engram/commands/__init__.py`
  - Export `recall`.
  - Stop exporting `lookup`.

- `engram/client.py`
  - Replace `EngramClient.lookup()` with `EngramClient.recall()`.
  - Update `llm_tools()` from `engram_lookup` to `engram_recall`.
  - Update close-guard tests and docstrings.

- `engram/cli.py`
  - Remove `moment`, `episode`, and `arc` parser registrations.
  - Add `recall` parser.
  - Parse flexible recall args in CLI only:
    - one positional means exact item recall
    - two positionals means scoped recall
  - Convert ID strings to `int` in CLI so invalid IDs produce argparse exit
    code `2`.
  - Delegate to `commands.recall()`.
  - Keep output JSON item object.

- `engram/background.py`
  - Search this file for removed public retrieval names. Edit it only if a
    match is found.

- `engram/dogfood/codex_replay.py`
  - Update user-facing text that says "direct lookup" if it names the public
    API. If it only describes conceptual retrieval, use "direct recall".

### Tests

- `tests/store/test_recall_containment.py`
  - New focused store tests for parent and support-range containment.

- `tests/core/test_recall.py`
  - New focused domain tests for exact recall, scoped recall, and access
    mutation.

- `tests/commands/test_memory_commands.py`
  - Replace lookup assertions with recall assertions.
  - Add no-old-command-layer-name assertions.

- `tests/client/test_client.py`
  - Replace lookup calls with recall.
  - Add no `EngramClient.lookup` assertion.
  - Update LLM tool tests for `engram_recall`.

- `tests/cli/test_cli.py`
  - Replace moment/episode/arc tests with recall tests.
  - Add negative old-command tests for `moment`, `episode`, and `arc`.
  - Add invalid recall argument tests.

- `tests/core/test_context.py`
  - Update internal test reads from removed `lookup()` to `recall(...,
    count_access=False)` or to test helpers if they are storage-invariant
    checks.

- Any other test found by:

  ```bash
  rg -n "lookup|moment\\(|episode\\(|arc\\(|engram_lookup|engram moment|engram episode|engram arc" tests engram docs README.md AGENTS.md
  ```

### Docs

- `README.md`
  - Replace CLI examples.
  - Replace client examples.
  - Replace low-level API examples.
  - Replace "direct lookup" wording with "direct recall" where it refers to
    the public API.

- `AGENTS.md`
  - Update the CLI/API equivalence table.
  - Update gotchas and access-score language.

- `docs/specs/11-minimum-write-search-context-slice.md`
  - Update [MWS-18], [MWS-27], [MWS-28], and interface snippets.

- `docs/specs/12-local-app-surface.md`
  - Update [LAS-21] wording from lookup to recall.

- `docs/specs/15-foundation-contracts-and-invariants.md`
  - Update [FCI-10] through [FCI-18] as needed.
  - Update [FCI-30] to `engram recall [episode|arc] ID --json`.
  - Preserve [FCI-43] no backwards-compatibility rule.

- `docs/implementation/04-minimum-memory-slice.md`
  - Update tool and surface mapping.

- `docs/implementation/06-arc-context-assembly.md`
  - Update "arc lookup" wording to "arc recall".

## 7. Implementation Tasks

Follow red-green TDD. Each task should start by adding or adjusting a failing
test, then implementing only enough code to pass it.

### Task 1: Lock Down Store Containment Behavior

Red tests:

1. Add a store test that creates two episode ranges:

   ```text
   episode A children: 900, 999
   episode B children: 1500, 2999
   ```

   Because summary IDs are support anchored, construct the fixture so episode A
   lands at `1000` and episode B lands at `3000`.

   Assert:

   ```python
   store.find_summary_containing(2000, parent_tier=TIER_EPISODE).id == 3000
   ```

2. Add a store test for exact direct parent:

   ```python
   store.get_parent(1500, parent_tier=TIER_EPISODE).id == 3000
   ```

3. Add a store test for no containing summary:

   ```python
   assert store.find_summary_containing(1200, parent_tier=TIER_EPISODE) is None
   ```

4. Add a deterministic overlap test with manual fixture summaries:

   ```python
   assert store.find_summary_containing(anchor, parent_tier=TIER_EPISODE).id == lower_parent_id
   ```

   This proves the documented tie-break. Keep the fixture direct and small. Do
   not add production overlap enforcement.

Green implementation:

1. Update `StateStore` protocol in `engram/store/base.py`.
2. Add methods to `StateStoreCore`.
3. Delegate from `SQLiteStateStore`.

Suggested SQL for `get_parent()`:

```sql
SELECT p.<memory item columns>
FROM memory_edges AS e
JOIN memory_items AS p ON p.id = e.parent_id
WHERE e.child_id = ?
  AND p.tier = ?
ORDER BY p.id ASC
LIMIT 1
```

Suggested SQL shape for `find_summary_containing()`:

```sql
WITH containing AS (
    SELECT e.parent_id
    FROM memory_edges AS e
    JOIN memory_items AS p ON p.id = e.parent_id
    JOIN memory_items AS c ON c.id = e.child_id
    WHERE p.tier = ?
    GROUP BY e.parent_id
    HAVING MIN(c.id) <= ? AND MAX(c.id) >= ?
    ORDER BY e.parent_id ASC
    LIMIT 1
)
SELECT <memory item columns>
FROM memory_items
WHERE id = (SELECT parent_id FROM containing)
```

Use `_item_from_row()` for row conversion. Do not hand-build `MemoryItem`
objects in the new methods.

Run:

```bash
uv run pytest tests/store/test_recall_containment.py tests/store/test_sqlite.py tests/store/test_memory_ids.py
```

### Task 2: Add Domain Recall

Red tests:

1. Exact recall:

   ```python
   item = memory.recall(moment_id, count_access=False)
   assert item.id == moment_id
   assert item.tier == TIER_MOMENT
   ```

2. Exact recall increments access by default:

   ```python
   before = memory.recall(moment_id, count_access=False).access
   memory.recall(moment_id)
   after = memory.recall(moment_id, count_access=False).access
   assert after == before + 1.0
   ```

3. Episode anchored recall by exact child moment:

   ```python
   episode = memory.recall(moment_id, scope="episode")
   assert episode.tier == TIER_EPISODE
   assert moment_id in [child.id for child in children(memory.vault_path, episode.id)]
   ```

4. Episode scoped recall of an exact episode returns itself:

   ```python
   episode = memory.recall(episode_id, scope="episode", count_access=False)
   assert episode.id == episode_id
   assert episode.tier == TIER_EPISODE
   ```

5. Episode anchored recall by in-between anchor:

   Use store fixtures or deterministic manual items so the anchor does not have
   to be an exact memory item:

   ```python
   episode = memory.recall(2000, scope="episode", count_access=False)
   assert episode.id == 3000
   ```

6. Arc scoped recall of an exact arc returns itself:

   ```python
   arc = memory.recall(arc_id, scope="arc", count_access=False)
   assert arc.id == arc_id
   assert arc.tier == TIER_ARC
   ```

7. Arc anchored recall from a moment:

   ```python
   arc = memory.recall(moment_id, scope="arc")
   assert arc.tier == TIER_ARC
   ```

8. Arc anchored recall from an exact episode ID:

   ```python
   arc = memory.recall(episode_id, scope="arc", count_access=False)
   assert arc.tier == TIER_ARC
   ```

9. Access mutation for scoped recall:

   ```python
   before_anchor = memory.recall(moment_id, count_access=False).access
   before_episode = memory.recall(episode_id, count_access=False).access
   memory.recall(moment_id, scope="episode")
   after_anchor = memory.recall(moment_id, count_access=False).access
   after_episode = memory.recall(episode_id, count_access=False).access
   assert after_anchor == before_anchor
   assert after_episode == before_episode + 1.0
   ```

10. Missing containing summary raises:

   ```python
   with pytest.raises(MemoryItemNotFoundError):
       memory.recall(anchor_id, scope="episode")
   ```

11. Invalid domain scope raises `ValueError` with a clear message:

   ```python
   with pytest.raises(ValueError, match="scope"):
       memory.recall(moment_id, scope="bad")  # type: ignore[arg-type]
   ```

12. Removed domain names:

   ```python
   assert not hasattr(Engram, "lookup")
   assert not hasattr(Engram, "moment")
   assert not hasattr(Engram, "episode")
   assert not hasattr(Engram, "arc")
   ```

Green implementation:

1. Add `Engram.recall()`.
2. Add private exact fetch helper:

   ```python
   def _get_item_or_raise(self, item_id: int, *, tier: int | None = None) -> MemoryItem:
       ...
   ```

3. Add private access helper:

   ```python
   def _count_access_and_reload(self, item: MemoryItem) -> MemoryItem:
       ...
   ```

4. Add private scoped helpers:

   ```python
   def _recall_item(...)
   def _recall_episode(...)
   def _recall_arc(...)
   ```

5. Remove public `lookup()`, `moment()`, `episode()`, and `arc()`.
6. Update internal domain callers:
   - Use `_get_item_or_raise()` for internal exact reads that should not expose
     public recall semantics.
   - Use `recall(..., count_access=False)` only where the public behavior is
     being intentionally exercised.

Do not let `_recall_arc()` call `recall(..., count_access=True)` for
intermediate episode traversal. That would increment the wrong item.

Run:

```bash
uv run pytest tests/core/test_recall.py tests/core/test_memory.py tests/core/test_context.py
```

### Task 3: Replace Command-Layer Lookup With Recall

Red tests:

1. `commands.recall(memory, item_id, count_access=False)` returns the same item
   shape as current command lookup.
2. `commands.recall(memory, moment_id, scope="episode", count_access=False)`
   returns an episode item dict.
3. `commands.recall(..., scope="arc")` returns an arc item dict when fixture
   data has arcs.
4. Command recall returns `None` for missing exact or containing recall.
5. Command recall can skip access counting.
6. Invalid command scope raises `ValueError` with a clear message.
7. `not hasattr(commands, "lookup")`.

Green implementation:

1. Rename command function to `recall`.
2. Normalize `item_id` with existing `_normalize_item_id()`.
3. Validate scope against the canonical scope list.
4. Catch `MemoryItemNotFoundError` and return `None`, matching prior command
   missing-item behavior.
5. Update `__all__`.
6. Update `engram/commands/__init__.py`.

Run:

```bash
uv run pytest tests/commands/test_memory_commands.py
```

### Task 4: Replace Client Lookup With Recall

Red tests:

1. `client.recall(item_id, count_access=False)` delegates to
   `commands.recall(...)`.
2. `client.recall(item_id, scope="episode", count_access=False)` works.
3. `client.recall(item_id, scope="arc", count_access=False)` works.
4. Closed clients reject `client.recall(...)`.
5. `not hasattr(EngramClient, "lookup")`.
6. Invalid client scope raises `ValueError` with a clear message.
7. `client.llm_tools()` exposes `engram_recall`, not `engram_lookup`.
8. `engram_recall` does not increment access.
9. `engram_recall` supports omitted scope as exact item recall.
10. `engram_recall` supports `scope="episode"` and `scope="arc"` without access
   mutation.

Green implementation:

1. Add `EngramClient.recall()`.
2. Remove `EngramClient.lookup()`.
3. Update `llm_tools()` tool name, description, schema, and implementation.
4. Update client docstrings.

Run:

```bash
uv run pytest tests/client/test_client.py
```

### Task 5: Add CLI Recall And Remove Tier Commands

Red tests:

1. `engram recall ID` returns exact item JSON.
2. `engram recall ID --json` returns the same JSON shape.
3. `engram recall episode ID` returns containing episode JSON.
4. `engram recall arc ID` returns containing arc JSON.
5. `engram recall episode 2000` works for an in-between anchor fixture.
6. Old commands fail with argparse exit code `2`:
   - `engram moment ID`
   - `engram episode ID`
   - `engram arc ID`
7. Invalid recall forms fail with argparse exit code `2`:
   - no args
   - missing scoped ID
   - bad scope
   - non-integer ID
   - extra args
8. Missing item or missing containing summary returns `EXIT_NOT_FOUND`.

Green implementation:

1. Remove parser registrations for `moment`, `episode`, and `arc`.
2. Add `recall` parser:

   ```python
   recall = subparsers.add_parser("recall")
   recall.add_argument("recall_args", nargs="+")
   recall.add_argument("--json", action="store_true")
   ```

3. Add a small CLI-only parser helper:

   ```python
   def _parse_recall_args(
       recall_args: list[str],
       parser: argparse.ArgumentParser,
   ) -> tuple[str, int]:
       ...
   ```

   It should return `(scope, item_id)`.

4. Accepted forms:

   ```text
   [ID] -> ("item", int(ID))
   ["episode", ID] -> ("episode", int(ID))
   ["arc", ID] -> ("arc", int(ID))
   ```

5. On invalid shape or invalid int, call `parser.error(...)`. Do not let
   `ValueError` escape to the generic exception path.
6. Delegate to `commands.recall()`.
7. If command returns `None`, raise `MemoryItemNotFoundError(item_id, tier=...)`
   for consistent exit-code handling.

Run:

```bash
uv run pytest tests/cli/test_cli.py
```

### Task 6: Update Docs And Specs

Red check:

Run:

```bash
rg -n "engram moment|engram episode|engram arc|client\\.lookup|memory\\.lookup|engram_lookup|direct lookup|moment\\(|episode\\(|arc\\(" README.md AGENTS.md docs engram tests
```

Every remaining hit must be one of:

- internal implementation detail using store `get_item`
- a negative test proving old public names are gone
- historical prose in an old implemented plan, if that plan is explicitly an
  execution record and not current guidance

Update current docs:

1. `README.md`
   - CLI example should show:

     ```bash
     engram recall <id>
     engram recall episode <mid>
     engram recall arc <mid>
     ```

   - Client example should show:

     ```python
     item = client.recall(results[0]["id"])
     episode = client.recall(mid, scope="episode")
     arc = client.recall(mid, scope="arc")
     ```

2. `AGENTS.md`
   - Update the CLI/API table.
   - State that recall is the only public direct-read vocabulary.
   - Preserve the no-backwards-compatibility warning.

3. `docs/specs/11-minimum-write-search-context-slice.md`
   - Replace lookup language with recall language.
   - Update the minimum CLI list.
   - Update interface snippets.

4. `docs/specs/12-local-app-surface.md`
   - Replace "lookup" in public surface list with "recall".

5. `docs/specs/15-foundation-contracts-and-invariants.md`
   - Replace public lookup/client lookup requirements with recall
     requirements.
   - Add anchored summary recall access invariant:

     ```text
     Scoped recall increments only the returned summary item, not intermediate
     anchor items used for traversal.
     ```

   - Update LLM tools from `engram_lookup` to `engram_recall`.
   - Update CLI JSON output contract.

6. `docs/implementation/04-minimum-memory-slice.md`
   - Update the surface mapping table.
   - Update read-only LLM tool text.

7. `docs/implementation/06-arc-context-assembly.md`
   - Replace "arc lookup" with "arc recall".

Run:

```bash
rg -n "engram moment|engram episode|engram arc|client\\.lookup|memory\\.lookup|engram_lookup|direct lookup" README.md AGENTS.md docs/specs docs/implementation engram tests
```

No current guidance should still recommend old public names.

### Task 7: Remove Stray Public Compatibility Paths

Search broadly:

```bash
rg -n "def lookup|lookup\\(|\\.lookup\\(|engram_lookup|def moment|def episode|def arc|engram moment|engram episode|engram arc" engram tests README.md AGENTS.md docs
```

Expected remaining code hits:

- `StateStore.get_item()` and storage-shaped tests.
- Private helpers with names that are not public compatibility paths.
- Negative tests asserting old names do not exist or old commands fail.
- Historical references inside old dated plans, if left untouched.

Unexpected hits to remove:

- `Engram.lookup`
- `EngramClient.lookup`
- `commands.lookup`
- `engram_lookup`
- public `moment`, `episode`, `arc` domain helper methods
- CLI parser branches for old commands
- current docs recommending old commands

Do not leave aliases with deprecation comments. The project policy is one path.

### Task 8: Full Verification

Run targeted tests first, then full gates:

```bash
uv run ruff check --fix engram tests
uv run ruff format engram tests
uv run pytest
uv run mypy engram
```

All must report green. If `ruff check --fix` or `ruff format` changes files,
rerun at least:

```bash
uv run pytest
uv run mypy engram
uv run ruff check engram tests
uv run ruff format --check engram tests
```

Do not claim done with only targeted tests.

### Task 9: Second Review

Use the available agent review path after local gates are green. Ask for a
specific review, not a generic vibe check:

```text
Review the anchored recall API change. Focus on:
1. Any remaining backwards-compatibility paths for lookup/moment/episode/arc.
2. Whether recall episode/arc uses authoritative support graph semantics.
3. Whether scoped recall increments only the returned item.
4. Whether command/client/CLI layering stays clean.
5. Whether docs/specs still recommend stale public API names.
```

Fix concrete findings. If the reviewer recommends adding compatibility aliases,
reject that recommendation unless the user explicitly changes the policy.

## 8. Test Design Guidance

Use real SQLite and real LanceDB-backed integration where the code path normally
uses them. Do not mock the state store to prove recall. Mocking the store would
only prove that mocks return what they were told to return.

Good tests:

- create real moments and summaries
- assert returned item IDs and tiers
- inspect real `memory_edges` through existing test helpers when needed
- assert access scores before and after recall
- assert old public names are absent
- assert CLI exit codes and JSON shapes

Bad tests:

- mock `StateStore.get_parent()` and assert it was called once
- assert implementation call order instead of returned behavior
- test only exact item recall and call that sufficient for anchored recall
- keep old names working "for safety"
- test CLI by calling command functions directly instead of `main(argv)`

Use deterministic embeddings for domain/client tests:

```python
Engram.init(path, embedder=DeterministicEmbedder())
```

Use existing fixtures where they naturally create episodes and arcs:

- `memory`
- `arc_memory`
- `children()`
- `recent_items()`
- `create_summary_item_for_test()`

When testing in-between anchors, prefer direct state-store fixtures over
depending on coalescing thresholds. That makes the test about containment, not
about summarizer window selection.

## 9. Invariants And Gates

Behavioral invariants:

- `recall MID` returns exact item `MID`.
- `recall episode MID` returns an episode, never a moment.
- `recall arc MID` returns an arc, never a moment or episode.
- Scoped recall uses `memory_edges` support, not LanceDB.
- Scoped recall works for exact anchors and in-between anchors.
- Scoped recall increments only the returned item.
- Context assembly still does not increment access.
- LLM tools still do not increment access.
- Old public commands do not parse.
- Old public client/command/domain helper names do not exist.
- Store methods do not mutate access.
- No schema migration is introduced.

Layering gates:

- CLI parses and presents only.
- Command layer normalizes and serializes only.
- Client delegates to command layer.
- Domain owns recall semantics.
- Store owns SQL parent/range queries.
- LanceDB is not involved in recall containment.

Documentation gates:

- Current docs and specs use recall vocabulary.
- Historical dated plans may remain historical, but they must not be cited as
  current guidance for old public names.
- `AGENTS.md` must not tell future agents to use removed commands.

Quality gates:

- No compatibility aliases.
- No new dependencies.
- No broad refactor unrelated to recall.
- No new schema column.
- No over-generic future-tier recall UI.
- Full `ruff`, `pytest`, and `mypy` gates green.

## 10. Out Of Scope

- Deletion or forgetting.
- Import/export.
- Higher-tier generic CLI such as `engram recall tier-3 MID`.
- UI beyond CLI/client/tool surfaces.
- Schema migration.
- Rebuilding the coalescing algorithm.
- Changing context assembly budgets.
- LanceDB search behavior.
- Hosted or multi-user APIs.
- Backwards-compatible aliases.

## 11. Stop Conditions

Stop and return to the user if any of these become true:

- Implementing anchored recall requires a schema migration.
- Existing `memory_edges` cannot answer containment correctly.
- Removing public `lookup` causes a third-party compatibility requirement the
  project has not discussed.
- The change starts expanding into generic arbitrary-tier recall.
- Tests show summary support ranges are not stable enough for the requested
  semantics.

Do not drift into a different product direction to make the implementation
easier. The target is recall over existing support-anchored summaries.

## 12. Fresh-Eyes Review

### Review Pass 1: Ambiguity In "Contains"

Problem: "Contains MID" could mean exact child membership only, or it could mean
timeline support range.

Resolution: This plan defines both:

- exact child membership is handled first with `get_parent()` when the anchor is
  an exact child row
- arbitrary anchor containment is support-range based:
  `MIN(child.id) <= anchor <= MAX(child.id)`

That matches the desired example where an anchor between summary boundaries
resolves to the later containing episode.

### Review Pass 2: Summary IDs Are Not Enough

Problem: It is tempting to implement `recall episode 2000` by comparing summary
IDs. That would be brittle because summary ID allocation can skip collisions.

Resolution: The plan requires state-store support-range queries over
`memory_edges` and child item IDs. Summary IDs help preserve timeline ordering,
but the support graph is authoritative.

### Review Pass 3: Arc Recall From Moment Anchors

Problem: Arc children are episodes, not moments. A direct arc range query over
episode child IDs may not find a moment anchor.

Resolution: The plan requires a two-step domain traversal for moment anchors:
moment anchor -> containing episode -> containing arc. Direct arc range
containment is only a fallback for episode-timeline anchors.

### Review Pass 4: Access Score Mutation

Problem: Implementing scoped recall by calling public recall recursively could
increment intermediate anchors or episodes.

Resolution: The plan requires store/private traversal for intermediate nodes
and increments only the final returned item.

### Review Pass 5: Backwards Compatibility Drift

Problem: Leaving `client.lookup`, `commands.lookup`, or CLI tier commands in
place would create two paths and hide bugs.

Resolution: The plan explicitly removes those public paths and adds negative
tests. Store `get_item()` remains because it is storage vocabulary, not public
recall vocabulary.

### Review Pass 6: CLI Parser Failure Mode

Problem: Flexible positional parsing can accidentally let `ValueError` escape
as a generic runtime error.

Resolution: The plan requires CLI-only recall argument parsing with
`parser.error(...)` for invalid shapes and non-integer IDs.

### Final Implementability Check

This plan stays inside the discussed direction:

- It replaces tier-named public reads with recall.
- It uses existing support-anchored summary identity.
- It uses existing backlinks.
- It keeps layering clean.
- It does not add a compatibility layer.
- It does not require schema changes or unrelated retrieval work.

No known blocker remains.
