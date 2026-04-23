# 2026-04-23 API Vocabulary: Process And Set Importance

Status: Implemented

## Goal

Replace two public API vocabulary leaks with canonical domain terms:

- `work` / `drain` becomes `process`
- `pin` becomes `set_importance` in Python and `set-importance` in the CLI

This is a hard rename. Do not add aliases, shims, compatibility wrappers, or
secondary public paths. Move all current repo users to the new names in the same
change.

## Target Surface

CLI:

```bash
engram vault process [--max-passes INT] [--json]
engram set-importance ID INT [--json]
```

Client:

```python
client.process(max_passes=1000)
client.set_importance(item_id, importance)
```

Command layer:

```python
commands.process(memory, max_passes=1000)
commands.set_importance(memory, item_id, importance=importance)
```

Domain:

```python
memory.process(max_passes=100)
memory.process_once(max_items=1)
memory.set_importance(item_id, importance=importance)
```

`set_importance` stores the value in the existing `MemoryItem.relevance` field.
Do not add a storage column. `importance` is an integer greater than or equal to
`1`, matching `record(..., importance=...)`.

## Files To Touch

- `engram/core/memory.py`
- `engram/commands/memory.py`
- `engram/commands/__init__.py`
- `engram/client.py`
- `engram/cli.py`
- `engram/_models.py`
- `engram/__init__.py`
- `engram/store/base.py`
- `engram/store/sqlite.py`
- `engram/store/core.py`
- tests under `tests/core/`, `tests/commands/`, `tests/client/`, `tests/cli/`
- active docs and specs that define public surfaces

## Invariants

- No `pin` public method, command, CLI command, or command-layer export remains.
- No `work_once`, `work_until_idle`, or `drain` public method/export remains.
- CLI does not accept `engram pin` or `engram work`.
- Existing persisted vaults require no migration.
- JSON result shapes do not change except command names.
- `set_importance` validates before writing and rejects non-integer, boolean,
  zero, or negative values.

## Verification

Run:

```bash
uv run ruff check --fix
uv run ruff format
uv run mypy engram
uv run pytest
uv run ruff check
uv run ruff format --check
```

Also scan active code and docs for removed public names. Tests may contain
negative assertions that the old public names are rejected, so scan production
and documentation separately from test assertions:

```bash
rg -n "\bpin\b|work_once|work_until_idle|\bdrain\b|engram work" engram README.md AGENTS.md docs/specs docs/implementation
```

## Implementation Result

Implemented on 2026-04-23.

Changed surfaces:

- `Engram.work_once()` became `Engram.process_once()`.
- `Engram.work_until_idle()` became `Engram.process()`.
- `Engram.pin(...)` became `Engram.set_importance(..., importance=...)`.
- `WorkResult` became `ProcessResult`.
- `commands.work_once()` became `commands.process_once()`.
- `commands.pin(...)` became `commands.set_importance(...)`.
- `EngramClient` exposes `process()` and `set_importance()`.
- CLI now exposes `engram vault process` and `engram set-importance`.
- CLI maintenance commands now live under the `vault` submenu:
  `engram vault status`, `engram vault process`, and
  `engram vault rebuild-index`.

Removed surfaces:

- No `pin` method, command-layer export, or CLI command remains.
- No `work_once`, `work_until_idle`, or `drain` public method/export remains.
- `engram pin`, `engram work`, top-level `engram status`, top-level
  `engram process`, and top-level `engram rebuild-index` are rejected by
  argparse.

Follow-up implemented on 2026-04-23:

- Top-level `engram init` remains top-level.
- Vault maintenance commands moved under `engram vault`.
- Python client and domain method names stayed unchanged because they already
  operate on an opened vault object.

Verification completed:

```bash
uv run pytest tests/core/test_memory.py tests/commands/test_memory_commands.py tests/client/test_client.py tests/cli/test_cli.py
uv run pytest tests/cli/test_cli.py
uv run pytest tests/core/test_context.py tests/test_background.py
uv run ruff check --fix
uv run ruff format
uv run mypy engram
uv run pytest
uv run ruff check
uv run ruff format --check
```

Final gate results:

- Public-layer suite passed: `47 passed`.
- CLI suite passed: `10 passed`.
- Context/background targeted suite passed: `14 passed`.
- Full test suite passed: `170 passed`.
- `uv run mypy engram` passed.
- `uv run ruff check` passed.
- `uv run ruff format --check` passed.
