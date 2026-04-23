# GitHub Pages Simple Index Plan

Status: implemented
Source spec: None — release tooling and GitHub Pages deployment change.
Process guidance: `docs/specs/01-development-documentation-operating-model.md`
[DOM-4], [DOM-5], [DOM-8], [DOM-10] plus
`docs/agent-context/runbooks/hardening-plans.md`.

## Goal

Extend the release gate so every tagged release regenerates and deploys a
GitHub Pages-hosted Python Simple Repository API index for Engram. The index
should include all historic GitHub Release wheel/sdist assets plus the current
release's freshly built `dist/*`, giving users a stable install URL before
PyPI publishing is enabled.

## Source Documents

- `.github/workflows/release-gate.yml`
- `.github/workflows/test.yml`
- `bin/release.py`
- `tests/system/test_release_script.py`
- `docs/implementation/02-repository-map.md`
- Python Packaging Simple Repository API
- GitHub Pages Actions publishing model

## Context and Key Files

Files to add:

- `bin/build_github_pages_index.py`
- `tests/system/test_github_pages_index.py`

Files to update:

- `.github/workflows/release-gate.yml`
- `.github/workflows/test.yml`
- `bin/release.py`
- `tests/system/test_release_script.py`
- `docs/implementation/02-repository-map.md`
- this plan

Current release gate:

- builds `dist/*` with `uv build`
- uploads and signs the wheel/sdist on the GitHub Release
- does not publish to PyPI
- does not deploy GitHub Pages

## Invariants and Constraints

- Do not enable PyPI publication.
- GitHub Releases remain the durable distribution artifact store.
- Pages deploys only static index HTML, not copied release assets.
- The index generator must include the current release from local `dist/*` even
  if the GitHub Releases API is briefly stale after asset upload.
- Historic entries should come from GitHub Releases with tags matching `v*`.
- The release gate must fail if Pages deployment fails; otherwise the first
  release could appear successful without the stable install URL.
- The generator must use only the standard library and no new dependency.
- Do not add a public Engram CLI command for index generation.

Rollback:

- Revert the Pages job and script changes. Existing GitHub Release artifacts
  remain valid and installable by direct asset URL.
- If Pages settings are not enabled yet, the release will fail at deploy time;
  enable Pages with source `GitHub Actions`, then rerun the failed job or rerun
  the release gate.

## Tasks

1. Add the Simple API index generator.
   - Query GitHub Releases through the REST API.
   - Collect `*.whl` and `*.tar.gz` release assets for `v*` tags.
   - Overlay current local `dist/*` assets using deterministic GitHub Release
     download URLs for the current tag.
   - Generate `site/index.html`, `site/simple/index.html`, and
     `site/simple/engram/index.html`.
   - Add hash fragments when a SHA-256 digest is known.

2. Wire the release gate to deploy Pages.
   - Add `pages: write` permission.
   - Run the generator after the GitHub Release artifact upload.
   - Upload the generated site with `actions/upload-pages-artifact`.
   - Deploy with `actions/deploy-pages`.

3. Extend tests and release command lists.
   - Add generator unit tests for HTML shape, URL escaping, local-dist overlay,
     and release-asset filtering.
   - Update workflow tests so the release gate proves Pages deployment and no
     PyPI publish.
   - Include the new script in release helper prechecks and CI lint/format
     gates.

4. Update docs.
   - Add the generator and Pages index tests to the repository map.
   - Record verification evidence in this plan.

## Testing Plan

- Do not mock the HTML generation core; test it with real temporary files.
- Mock only network/API boundaries by passing synthetic release payloads into
  pure parsing helpers.
- Verify workflow behavior by text/parse checks, not live GitHub deployment.
- Run full tests and quality gates because CI command surfaces change.

## Verification and Gates

Planned commands:

```bash
./.venv/bin/python -m pytest tests/system/test_github_pages_index.py -q
./.venv/bin/python -m pytest tests/system/test_release_script.py -q
./.venv/bin/python -m pytest
./.venv/bin/ruff check engram tests bin
./.venv/bin/ruff format --check engram tests bin
./.venv/bin/mypy engram
```

Observed verification:

- `./.venv/bin/python -m pytest tests/system/test_github_pages_index.py -q`: 7
  passed.
- `./.venv/bin/python -m pytest tests/system/test_release_script.py -q`: 29
  passed.
- `./.venv/bin/python -m pytest`: 164 passed.
- `./.venv/bin/ruff check engram tests bin`: all checks passed.
- `./.venv/bin/ruff format --check engram tests bin`: 70 files already
  formatted.
- `./.venv/bin/mypy engram`: success, no issues in 42 source files.
- Workflow YAML parse smoke test with PyYAML: `release-gate.yml`,
  `release.yml`, and `test.yml` loaded successfully.

## Independent Review Loop

Review path: self-review against this plan and tests. No subagent review is
used because this session was not explicitly authorized for sub-agent work.

## Out of Scope

- Enabling PyPI publishing.
- Copying release artifacts into the Pages site.
- Custom domains, branch protection, or environment protection setup.
- Supporting multiple first-party packages in the index.
