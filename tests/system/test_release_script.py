"""Tests for the local release helper script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_release_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "bin" / "release.py"
    spec = importlib.util.spec_from_file_location("engram_release_script", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load release script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _release_state(
    release: ModuleType,
    *,
    version: str,
    tag_name: str,
    github_release_exists: bool = False,
    pypi_release_exists: bool = False,
    local_tag_commit: str | None = None,
    remote_tag_commit: str | None = None,
):
    return release.ReleaseState(
        target=release.ROOT_RELEASE_TARGET,
        version=version,
        tag_name=tag_name,
        github_release_exists=github_release_exists,
        pypi_release_exists=pypi_release_exists,
        local_tag_commit=local_tag_commit,
        remote_tag_commit=remote_tag_commit,
    )


def test_write_version_files_updates_pyproject_and_constants(tmp_path: Path) -> None:
    """The helper should update both canonical root-package version sources."""

    release = _load_release_module()
    pyproject_path = tmp_path / "pyproject.toml"
    constants_path = tmp_path / "_constants.py"

    pyproject_path.write_text(
        '[project]\nname = "engram"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    constants_path.write_text(
        'from typing import Final\n__version__: Final[str] = "0.1.0"\n',
        encoding="utf-8",
    )

    release.write_version_files(
        "0.1.1",
        pyproject_path=pyproject_path,
        constants_path=constants_path,
    )

    assert 'version = "0.1.1"' in pyproject_path.read_text(encoding="utf-8")
    assert '__version__: Final[str] = "0.1.1"' in constants_path.read_text(
        encoding="utf-8"
    )


def test_read_current_version_rejects_mismatch(tmp_path: Path) -> None:
    """The helper should fail fast if canonical root version files drifted."""

    release = _load_release_module()
    pyproject_path = tmp_path / "pyproject.toml"
    constants_path = tmp_path / "_constants.py"

    pyproject_path.write_text(
        '[project]\nname = "engram"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    constants_path.write_text(
        'from typing import Final\n__version__: Final[str] = "0.1.1"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Version mismatch"):
        release.read_current_version(
            pyproject_path=pyproject_path,
            constants_path=constants_path,
        )


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.1.1", "0.1.1"),
        ("  1.2.3  ", "1.2.3"),
    ],
)
def test_validate_version_accepts_explicit_semver(
    version: str,
    expected: str,
) -> None:
    """The helper should accept the strict version format it documents."""

    release = _load_release_module()
    assert release.validate_version(version) == expected


@pytest.mark.parametrize("version", ["v0.1.1", "0.1", "0.1.1rc1", "alpha"])
def test_validate_version_rejects_invalid_values(version: str) -> None:
    """The helper should reject non-X.Y.Z versions."""

    release = _load_release_module()
    with pytest.raises(ValueError, match="X.Y.Z"):
        release.validate_version(version)


def test_root_release_target_uses_engram_paths() -> None:
    """The root target should point at Engram's package and version files."""

    release = _load_release_module()

    assert release.ROOT_RELEASE_TARGET.package_name == "engram"
    assert release.ROOT_RELEASE_TARGET.tag_name("0.1.0") == "v0.1.0"
    assert release.ROOT_RELEASE_TARGET.constants_path == release.CONSTANTS_PATH
    assert release.ROOT_RELEASE_TARGET.github_release_enabled is True


def test_inspect_release_state_uses_engram_package_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release state checks should query Engram's package and root tag."""

    release = _load_release_module()
    monkeypatch.setattr(release, "github_release_exists", lambda tag_name: False)
    monkeypatch.setattr(
        release,
        "pypi_version_exists",
        lambda package_name, version: package_name == "engram" and version == "0.1.0",
    )
    monkeypatch.setattr(release, "local_tag_commit", lambda tag_name: "a" * 40)
    monkeypatch.setattr(release, "remote_tag_commit", lambda tag_name: None)

    state = release.inspect_release_state("0.1.0")

    assert state.tag_name == "v0.1.0"
    assert state.pypi_release_exists is True
    assert state.target is release.ROOT_RELEASE_TARGET


def test_main_dry_run_publish_flag_keeps_pypi_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The helper should not attempt direct PyPI publication."""

    release = _load_release_module()
    monkeypatch.setattr(release, "read_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "is_dirty_worktree", lambda: False)
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
        ),
    )
    monkeypatch.setattr(release, "current_head_commit", lambda: "a" * 40)

    exit_code = release.main(["--version", "0.1.1", "--publish", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert release.RELEASE_GATE_WORKFLOW in captured.out
    assert release.PYPI_RELEASE_WORKFLOW in captured.out
    assert "direct PyPI publication remains disabled" in captured.out
    assert "uv publish" not in captured.out


def test_resolve_target_version_reuses_current_when_unpublished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper should reuse the current version until it is externally published."""

    release = _load_release_module()
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
        ),
    )

    target_version, state = release.resolve_target_version(
        None,
        current_version="0.1.0",
    )

    assert target_version == "0.1.0"
    assert state.tag_name == "v0.1.0"


def test_resolve_target_version_requires_new_version_after_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current version cannot be reused after publication."""

    release = _load_release_module()
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
            github_release_exists=True,
        ),
    )

    with pytest.raises(RuntimeError, match="Pass --version with a new version"):
        release.resolve_target_version(None, current_version="0.1.0")


def test_plan_tag_action_rejects_existing_tag_on_different_commit() -> None:
    """The helper should not silently move an existing unpublished tag."""

    release = _load_release_module()
    state = _release_state(
        release,
        version="0.1.0",
        tag_name="v0.1.0",
        remote_tag_commit="a" * 40,
    )

    with pytest.raises(RuntimeError, match="move the remote tag"):
        release.plan_tag_action(
            state,
            head_commit="b" * 40,
            version_changed=False,
            allow_retag=False,
        )


def test_plan_tag_action_replaces_stale_local_tag() -> None:
    """A stale local-only tag should be deleted and recreated automatically."""

    release = _load_release_module()
    state = _release_state(
        release,
        version="0.1.0",
        tag_name="v0.1.0",
        local_tag_commit="a" * 40,
    )

    assert (
        release.plan_tag_action(
            state,
            head_commit="b" * 40,
            version_changed=False,
            allow_retag=False,
        )
        == "replace_local"
    )


def test_plan_tag_action_replaces_remote_tag_only_with_retag() -> None:
    """A stale remote tag should require explicit ``--retag``."""

    release = _load_release_module()
    state = _release_state(
        release,
        version="0.1.0",
        tag_name="v0.1.0",
        local_tag_commit="a" * 40,
        remote_tag_commit="a" * 40,
    )

    assert (
        release.plan_tag_action(
            state,
            head_commit="b" * 40,
            version_changed=False,
            allow_retag=True,
        )
        == "replace_remote"
    )


def test_github_api_auth_headers_use_environment_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub release lookups should use the current API token when present."""

    release = _load_release_module()
    release._github_api_token.cache_clear()
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    headers = release._github_api_auth_headers()

    assert headers == {"Authorization": "Bearer env-token"}


def test_github_api_auth_headers_fall_back_to_gh_auth_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper should fall back to ``gh auth token`` for authenticated lookups."""

    release = _load_release_module()
    release._github_api_token.cache_clear()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(release.shutil, "which", lambda name: "/opt/homebrew/bin/gh")
    monkeypatch.setattr(
        release,
        "_capture_command",
        lambda command, cwd=release.PROJECT_ROOT: subprocess.CompletedProcess(
            command,
            0,
            stdout="gh-token\n",
            stderr="",
        ),
    )

    headers = release._github_api_auth_headers()

    assert headers == {"Authorization": "Bearer gh-token"}


def test_main_dry_run_reuses_current_unpublished_version(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run should allow the current unpublished version without a bump."""

    release = _load_release_module()
    monkeypatch.setattr(release, "read_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "is_dirty_worktree", lambda: False)
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
        ),
    )
    monkeypatch.setattr(release, "current_head_commit", lambda: "a" * 40)

    exit_code = release.main(["--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "target:  0.1.0" in captured.out
    assert "would reuse existing version files" in captured.out
    assert "would update pyproject.toml" not in captured.out


def test_main_dry_run_deletes_stale_local_tag_before_recreating(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run should show automatic cleanup of a stale local-only root tag."""

    release = _load_release_module()
    monkeypatch.setattr(release, "read_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "is_dirty_worktree", lambda: False)
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
            local_tag_commit="a" * 40,
        ),
    )
    monkeypatch.setattr(release, "current_head_commit", lambda: "b" * 40)

    exit_code = release.main(["--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "$ git tag -d v0.1.0" in captured.out
    assert "$ git tag v0.1.0" in captured.out


def test_main_dry_run_stages_uv_lock_for_release_commit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run should include ``uv.lock`` in the release commit staging set."""

    release = _load_release_module()
    monkeypatch.setattr(release, "read_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "is_dirty_worktree", lambda: False)
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
        ),
    )
    monkeypatch.setattr(release, "current_head_commit", lambda: "a" * 40)

    exit_code = release.main(["--version", "0.1.1", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "$ git add pyproject.toml engram/_constants.py uv.lock" in captured.out


def test_main_dry_run_retags_remote_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run should show remote tag deletion only when ``--retag`` is set."""

    release = _load_release_module()
    monkeypatch.setattr(release, "read_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "is_dirty_worktree", lambda: False)
    monkeypatch.setattr(
        release,
        "inspect_release_state",
        lambda version, *, target=release.ROOT_RELEASE_TARGET: _release_state(
            release,
            version=version,
            tag_name=target.tag_name(version),
            local_tag_commit="a" * 40,
            remote_tag_commit="a" * 40,
        ),
    )
    monkeypatch.setattr(release, "current_head_commit", lambda: "b" * 40)

    exit_code = release.main(["--dry-run", "--retag"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "$ git push --delete origin v0.1.0" in captured.out
    assert "$ git tag -d v0.1.0" in captured.out
    assert "$ git tag v0.1.0" in captured.out


def test_build_precheck_commands_cover_release_gate_and_quality_gates() -> None:
    """The helper precheck should cover release-gate and quality commands."""

    release = _load_release_module()
    commands = release.build_precheck_commands()
    test_command = commands[0]
    ruff_check_command = commands[1]
    ruff_format_command = commands[2]
    mypy_command = commands[3]

    assert test_command == (
        "uv",
        "run",
        "--extra",
        "dev",
        "pytest",
        "-v",
        "--tb=short",
        "-m",
        "",
        "--override-ini=addopts=-ra -q --strict-markers",
    )
    assert ruff_check_command == (
        "uv",
        "run",
        "--extra",
        "dev",
        "ruff",
        "check",
        "engram",
        "tests",
        "bin",
    )
    assert ruff_format_command == (
        "uv",
        "run",
        "--extra",
        "dev",
        "ruff",
        "format",
        "--check",
        "engram",
        "tests",
        "bin",
    )
    assert mypy_command == (
        "uv",
        "run",
        "--extra",
        "dev",
        "mypy",
        "engram",
        "--config-file",
        "pyproject.toml",
    )
    assert release.PRECHECK_ENV_OVERRIDES == {"PYTEST_ADDOPTS": "-x --maxfail=1"}


def test_build_postupdate_steps_build_root_package() -> None:
    """Post-update verification should lock, test version config, and build."""

    release = _load_release_module()

    steps = release.build_postupdate_steps()

    assert steps[0] == release.CommandStep(("uv", "lock"))
    assert steps[1] == release.CommandStep(
        ("uv", "run", "pytest", "tests/test_constants.py", "-q")
    )
    assert steps[2] == release.CommandStep(("uv", "build"))


def test_merge_command_env_appends_pytest_addopts() -> None:
    """Precheck env overrides should preserve existing pytest addopts."""

    release = _load_release_module()
    merged = release._merge_command_env(
        release.PRECHECK_ENV_OVERRIDES,
        base_env={
            "PATH": "/tmp/bin",
            "PYTEST_ADDOPTS": "--lf",
        },
    )

    assert merged is not None
    assert merged["PATH"] == "/tmp/bin"
    assert merged["PYTEST_ADDOPTS"] == "--lf -x --maxfail=1"


def test_run_command_dry_run_shows_env_prefix_and_cwd(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run command logging should show env overrides and non-root cwd."""

    release = _load_release_module()
    monkeypatch.setattr(release.subprocess, "run", lambda *args, **kwargs: None)

    release.run_command(
        ("pytest", "-q"),
        cwd=release.PROJECT_ROOT / "docs",
        dry_run=True,
        env_overrides=release.PRECHECK_ENV_OVERRIDES,
    )

    captured = capsys.readouterr()
    assert "PYTEST_ADDOPTS='-x --maxfail=1'" in captured.out
    assert "pytest -q" in captured.out
    assert "(cwd=docs)" in captured.out


def test_release_gate_builds_github_release_without_pypi_publish() -> None:
    """The active tag gate should build artifacts but not publish to PyPI."""

    root = Path(__file__).resolve().parents[2]
    release_gate = (root / ".github" / "workflows" / "release-gate.yml").read_text(
        encoding="utf-8"
    )

    assert 'tags:\n      - "v*"' in release_gate
    assert "verify-main-test-workflow" in release_gate
    assert 'workflow_id: "test.yml"' in release_gate
    assert "uv build" in release_gate
    assert "sigstore/gh-action-sigstore-python" in release_gate
    assert "softprops/action-gh-release" in release_gate
    assert "Deploy GitHub Pages package index" in release_gate
    assert "python bin/build_github_pages_index.py" in release_gate
    assert "actions/upload-pages-artifact" in release_gate
    assert "actions/deploy-pages" in release_gate
    assert "uv publish" not in release_gate
    assert "uses: ./.github/workflows/release.yml" not in release_gate


def test_pypi_release_workflow_exists_but_is_disabled() -> None:
    """The future PyPI workflow should be present but not active."""

    root = Path(__file__).resolve().parents[2]
    release_workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_call:" in release_workflow
    assert "workflow_dispatch:" not in release_workflow
    assert "push:" not in release_workflow
    assert "release:" not in release_workflow
    assert "Publish to PyPI (disabled)" in release_workflow
    assert "if: ${{ false }}" in release_workflow
    assert "uv publish --trusted-publishing always dist/*" in release_workflow


def test_test_workflow_runs_engram_quality_gates() -> None:
    """The normal CI workflow should use Engram package paths."""

    root = Path(__file__).resolve().parents[2]
    test_workflow = (root / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8"
    )

    assert 'python-version: ["3.12", "3.13", "3.14"]' in test_workflow
    assert 'uv pip install --system -e ".[dev]"' in test_workflow
    assert "pytest -v --tb=short" in test_workflow
    assert "engram version" in test_workflow
    assert "ruff check engram tests bin" in test_workflow
    assert "mypy engram --config-file pyproject.toml" in test_workflow
