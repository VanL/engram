# Release Tooling Port Plan

Status: implemented
Source spec: None — release tooling and GitHub Actions change.
Process guidance: `docs/specs/01-development-documentation-operating-model.md`
[DOM-4], [DOM-5], [DOM-8], [DOM-10].

## Goal

Port Weft's repo-local release helper and GitHub release runners into Engram
with Engram package names, paths, tests, and quality gates. Keep the future
PyPI publish workflow present but disabled because Engram cannot publish
directly to PyPI yet.

## Source Documents

- `../weft/bin/release.py`
- `../weft/.github/workflows/release-gate.yml`
- `../weft/.github/workflows/release.yml`
- `../weft/.github/workflows/test.yml`
- `../weft/tests/system/test_release_script.py`
- `pyproject.toml`
- `engram/_constants.py`
- `docs/implementation/02-repository-map.md`

## Context and Key Files

Files to add:

- `bin/release.py`
- `.github/workflows/test.yml`
- `.github/workflows/release-gate.yml`
- `.github/workflows/release.yml`
- `tests/system/test_release_script.py`

Files to update:

- `docs/implementation/02-repository-map.md`
- this plan

Current Engram release facts:

- `pyproject.toml` and `engram/_constants.py` are the canonical version
  sources and both currently say `0.1.0`.
- Engram has no first-party extension packages, no `bin/pytest-pg`, and no
  existing GitHub Actions workflows.
- The installed CLI version check is `engram version`, not `engram --version`.
- The development dependency group is `dev`; it already includes pytest, ruff,
  mypy, pytest-cov, and PG client dependencies.

## Invariants and Constraints

- Do not enable direct PyPI publication.
- The disabled PyPI workflow must not have independent push, tag, release, or
  manual triggers, and the PyPI job must remain disabled even if the reusable
  workflow is accidentally called.
- Do not create extension release targets for packages Engram does not have.
- Keep version updates atomic across `pyproject.toml`, `engram/_constants.py`,
  and `uv.lock`.
- Do not add a new installed `engram` CLI command or a new release dependency.
- Do not push tags or change remotes as part of this implementation.
- Keep release checks grounded in existing Engram commands: pytest, ruff,
  ruff format check, mypy, `uv lock`, and `uv build`.

## Tasks

1. Add the Engram release helper.
   - Port the Weft helper's version sync, dirty-tree guard, PyPI/GitHub state
     checks, retag planning, dry-run output, release commit, branch push, and
     tag push behavior.
   - Replace Weft paths and command lists with Engram paths and command lists.
   - Remove extension package support.

2. Add targeted release-helper tests.
   - Load `bin/release.py` by file path.
   - Verify version file updates, mismatch rejection, strict version parsing,
     tag planning, dry-run output, disabled direct PyPI workflow expectations,
     and command-list shape.
   - Avoid live git, GitHub, or PyPI integration tests; monkeypatch those
     boundaries.

3. Add GitHub Actions workflows.
   - Add `test.yml` for the normal matrix and lint/type gates.
   - Add `release-gate.yml` for version-tag release testing, tag-current
     verification, dist build, signing, and GitHub Release artifact upload.
   - Add `release.yml` as the future PyPI publish workflow, but keep it
     disabled and uncalled.

4. Update repository documentation.
   - Add the new release helper, workflows, and test file to the repository map.
   - Keep this plan current with final verification evidence.

## Testing Plan

- Run the targeted release-helper tests first.
- Run ruff on the new script and tests.
- Run mypy for `engram` because package code was not changed, and run the full
  suite only if the targeted tests or workflow checks suggest broader risk.
- Verify workflow files by text assertions in `tests/system/test_release_script.py`.

## Verification and Gates

Final gates:

```bash
./.venv/bin/python -m pytest tests/system/test_release_script.py -q
./.venv/bin/python -m pytest tests/test_constants.py -q
./.venv/bin/ruff check bin/release.py tests/system/test_release_script.py
./.venv/bin/ruff format --check bin/release.py tests/system/test_release_script.py
./.venv/bin/mypy engram
```

Success means the helper behavior is covered, version consistency still holds,
the new Python files pass lint and formatting checks, and package type checks
still pass.

Observed verification:

- `./.venv/bin/python -m pytest tests/system/test_release_script.py -q`: 29
  passed.
- `./.venv/bin/python -m pytest tests/test_constants.py -q`: 2 passed.
- `./.venv/bin/python -m pytest`: 149 passed.
- `./.venv/bin/ruff check engram tests bin/release.py`: all checks passed.
- `./.venv/bin/ruff format --check engram tests bin/release.py`: 68 files
  already formatted.
- `./.venv/bin/mypy engram`: success, no issues in 42 source files.
- Workflow YAML parse smoke test with PyYAML: `release-gate.yml`,
  `release.yml`, and `test.yml` loaded successfully.

## Independent Review Loop

Review path: self-review against this plan plus targeted tests. A separate
subagent review is not used in this session because the current tool policy
only permits spawning when the user explicitly asks for sub-agents.

## Out of Scope

- Publishing to PyPI.
- Adding TestPyPI support.
- Adding branch protection, environment protection, or repository secrets.
- Adding release notes to README beyond the repository map update.
