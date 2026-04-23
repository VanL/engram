# Windows Status Path And Release Plan

Status: in progress

## Goal

Fix the Windows-only CLI regression caused by a POSIX-only path suffix
assertion, keep the `VaultStatus` JSON contract aligned with native `Path`
and `model_dump(mode="json")` behavior, then run the full release flow and watch
GitHub until the release succeeds.

## Source Documents

Source specs:
- `docs/specs/12-local-app-surface.md` [LAS-8], [LAS-26], [LAS-28], [LAS-31]
- `docs/specs/15-foundation-contracts-and-invariants.md` [FCI-32], [FCI-36]

Source docs and code:
- `tests/cli/test_cli.py`
- `engram/core/memory.py`
- `bin/release.py`
- `docs/plans/2026-04-23-release-tooling-port-plan.md`

## Context and Key Files

Files to read first:
- `engram/core/memory.py`: `Engram.status()` owns the `VaultStatus` payload and
  currently serializes paths with `str(Path(...))`.
- `tests/cli/test_cli.py`: CLI contract tests, including the failing
  `broker_path` suffix assertion.
- `bin/release.py`: repo-local release entry point the user explicitly asked to
  run with `--retag`.

Files to modify:
- `tests/cli/test_cli.py`
- this plan

Current structure:
- `engram vault status --json` is specified to expose
  `VaultStatus.model_dump(mode="json")`.
- `Engram.status()` emits `vault_path`, `sqlite_path`, `index_path`, and
  `broker_path` from native `Path` string conversions. Changing one field to a
  forced POSIX format would create an inconsistent JSON contract.
- The current failure is in test code, not in the status implementation.

Comprehension check:
- Does the spec require a POSIX path string, or does it require the JSON shape
  from `VaultStatus.model_dump(mode="json")`?
- If one path field were normalized in production, would the rest of the
  contract still be internally consistent across platforms?

## Invariants and Constraints

- Keep `engram vault status --json` aligned with `VaultStatus.model_dump(mode="json")`.
- Do not introduce a second path-formatting rule just for `broker_path`.
- Keep the regression proof on the real CLI path.
- Do not broaden the change into unrelated CLI or status cleanup.
- Release work must use the repository’s existing tooling: repo venv binaries,
  `bin/release.py --retag`, and GitHub inspection via `gh`.

## Assumptions

- No spec or downstream consumer requires POSIX separators in status JSON.
- `bin/release.py --retag` encapsulates the intended release workflow for this
  repository.
- GitHub credentials and tag push permissions are already available in this
  environment. If not, the release step will block on external auth, not local
  code state.

## Tasks

1. Fix the brittle regression proof.
   - Files to touch: `tests/cli/test_cli.py`
   - Read first: `engram/core/memory.py`, `docs/specs/12-local-app-surface.md`,
     `docs/specs/15-foundation-contracts-and-invariants.md`
   - Reuse `pathlib.Path` for normalization in the assertion instead of adding
     a production formatting helper.
   - Verify with the targeted CLI test first.
   - Stop and re-evaluate if another test or caller depends on forced POSIX
     output.

2. Run local quality gates.
   - Commands: targeted pytest, then `ruff check`, `ruff format --check`,
     `mypy engram`, and the relevant broader pytest scope if needed.
   - Keep commands that mutate repo state or depend on previous output
     sequential.

3. Execute the release workflow and monitor it.
   - Run `bin/release.py --retag`.
   - Follow resulting GitHub activity with `gh` until push and release finish
     successfully, or until a concrete external blocker appears.
   - If GitHub checks or release jobs fail, inspect the failures, fix the cause,
     rerun local gates as needed, and repeat.

## Testing Plan

- Primary regression proof:
  `./.venv/bin/python -m pytest tests/cli/test_cli.py -k status_and_rebuild_index -q`
- Neighboring CLI contract proof if the regression fix touches shared helpers:
  `./.venv/bin/python -m pytest tests/cli/test_cli.py -q`
- Quality gates:
  `./.venv/bin/ruff check engram tests bin`
  `./.venv/bin/ruff format --check engram tests bin`
  `./.venv/bin/mypy engram`

What stays real:
- real CLI entry point
- real SQLite/LanceDB local behavior in tests

What may remain mocked:
- nothing for the targeted regression

## Verification and Gates

Per-task verification:
- regression test passes on local platform
- no new lint or type issues

Final gates before completion:
- requested local commands pass
- `bin/release.py --retag` completes successfully
- GitHub release state is observed with `gh`

Rollback path:
- If the test-only fix is wrong, revert the assertion change before release.
- If release automation fails after local success, inspect the failing GitHub
  step, patch the repo, and rerun the same gates plus release.

## Independent Review Loop

Review path: self-review against the specs, the failing test, and the final
diff. A separate subagent review is not used because the current session policy
only allows spawning when the user explicitly asks for subagents.

## Out Of Scope

- Changing `VaultStatus` field names or JSON shape
- Reformatting all path-like outputs to POSIX
- Unrelated release-tooling refactors
