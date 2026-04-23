# Release Helper Windows Display Path Plan

Status: in progress

## Goal

Fix the Windows-only `0.5.1` CI regression in release-helper dry-run output,
keep the release helper's behavior unchanged apart from stable display-path
formatting, then retag and rerun `v0.5.1` until both `Test` and `Release Gate`
finish green.

## Source Documents

Source spec: None — release-tooling bug fix and release retry.

Source docs and code:
- `bin/release.py`
- `tests/system/test_release_script.py`
- `docs/plans/2026-04-23-release-tooling-port-plan.md`
- GitHub Actions runs `24854220715` (`Test`) and `24854225851` (`Release Gate`)

## Context and Key Files

Files to read first:
- `bin/release.py`: `_display_path()` already defines stable POSIX-style log
  output but the main release and dry-run version-update messages bypass it.
- `tests/system/test_release_script.py`: the failing regression proof expects
  stable `pyproject.toml` and `engram/_constants.py` display paths.

Files to modify:
- `bin/release.py`
- `docs/lessons.md`
- this plan

Current structure:
- The failing GitHub runs are on release commit `a5411e9` and tag `v0.5.1`.
- `Test` fails only on Windows because the helper prints native Windows
  separators in a dry-run message that the tests treat as stable display text.
- `Release Gate` fails transitively because it waits for the `Test` workflow on
  the release commit.

Comprehension checks:
- Which existing helper already owns stable display-path formatting?
- Which release messages still interpolate raw `Path.relative_to(...)` values
  instead of routing through that helper?

## Invariants and Constraints

- Keep release version, tag-planning, and publish behavior unchanged.
- Reuse `_display_path()` instead of introducing a second display-path helper.
- Keep the regression proof on the real `bin/release.py` module path.
- Do not broaden this into unrelated release-tooling cleanup.
- Retrying `v0.5.1` must move the existing tag to the new fix commit by using
  the existing `--retag` flow.

## Assumptions

- No downstream consumer depends on backslash-separated path fragments in
  release-helper stdout.
- The current `v0.5.1` GitHub Release is absent or replaceable because the
  release gate never completed successfully.
- GitHub auth and repo permissions still allow tag deletion, push, workflow
  inspection, and reruns.

## Tasks

1. Fix stable display-path usage in the release helper.
   - Files to touch: `bin/release.py`
   - Read first: `_display_path()` and the `main()` dry-run / real-run version
     update messages.
   - Reuse `_display_path(PYPROJECT_PATH)` and `_display_path(CONSTANTS_PATH)`
     in both code paths.
   - Stop and re-evaluate if other Windows-only failures appear outside this
     message path.

2. Record the repeated failure mode.
   - Files to touch: `docs/lessons.md`
   - Add a durable lesson that human-facing path strings in CLI/release output
     must use a stable display formatter or tests need path-aware comparisons.

3. Verify locally, then retry the release.
   - Run the narrow release-script regression proof first.
   - Run the required local gates.
   - Commit the fix, retag `v0.5.1`, rerun workflows, and monitor GitHub until
     both `Test` and `Release Gate` succeed.

## Testing Plan

- Narrow regression proof:
  `./.venv/bin/python -m pytest tests/system/test_release_script.py -k short_version_flag_updates_version_targets -q`
- Neighboring release-helper proof:
  `./.venv/bin/python -m pytest tests/system/test_release_script.py -q`
- Required gates:
  `./.venv/bin/ruff check engram tests bin`
  `./.venv/bin/ruff format --check engram tests bin`
  `./.venv/bin/mypy engram --config-file pyproject.toml`

What stays real:
- real `bin/release.py` module loading and stdout behavior

What may remain mocked:
- GitHub/PyPI state shims already used by `tests/system/test_release_script.py`

## Verification and Gates

Per-task verification:
- the targeted Windows regression test passes locally
- the full release-script test file stays green

Final gates:
- requested local gates pass
- `main` is pushed with the fix commit
- `v0.5.1` points at the fix commit
- GitHub `Test` and `Release Gate` complete successfully for `0.5.1`

Rollback:
- Revert the display-path message change if it causes broader output-contract
  drift.
- If the retried release fails for a different reason, inspect that new root
  cause before changing more code.

## Independent Review Loop

Review path: self-review against the failing GitHub logs, this plan, and the
release-helper tests. A separate subagent review is not used because this
session does not authorize subagents.

## Out Of Scope

- New release features
- PyPI publishing changes
- Additional workflow redesign beyond what the retried `0.5.1` release needs
