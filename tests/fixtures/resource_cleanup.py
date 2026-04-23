from __future__ import annotations

import gc
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

from engram._constants import DEFAULT_SQLITE_FILENAME

T = TypeVar("T")


class ResourceTracker:
    """Per-test close tracker for file-backed resources."""

    def __init__(self) -> None:
        self._resources: list[object] = []

    def register(self, resource: T) -> T:
        """Track one resource and return it unchanged."""

        self._resources.append(resource)
        return resource

    def close_all(self) -> None:
        """Close tracked resources in reverse creation order."""

        resources = list(reversed(self._resources))
        self._resources.clear()
        errors: list[BaseException] = []
        for resource in resources:
            closer = _close_method(resource)
            if closer is None:
                continue
            try:
                closer()
            except BaseException as exc:  # pragma: no cover - exercised by tests
                errors.append(exc)
        if errors:
            raise ExceptionGroup("resource cleanup failed", errors)


def ensure_windows_cleanup() -> None:
    """Force finalizers that release file handles, with an extra Windows pass."""

    gc.collect()
    if sys.platform == "win32":
        time.sleep(0.1)
        gc.collect()


def sqlite_candidate_paths(db_path: Path) -> list[Path]:
    """Return existing SQLite database and sidecar files for cleanup checks."""

    candidates = [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        Path(f"{db_path}-journal"),
    ]
    return [path for path in candidates if path.exists()]


def vault_sqlite_candidate_paths(vault_path: Path) -> list[Path]:
    """Return known sqlite-backed files created inside one Engram vault."""

    state_db = vault_path / DEFAULT_SQLITE_FILENAME
    broker_db = vault_path / "broker.db"
    return [
        *sqlite_candidate_paths(state_db),
        *sqlite_candidate_paths(broker_db),
    ]


def database_files_releasable(paths: Sequence[Path]) -> bool:
    """Return whether sqlite files appear releasable on this platform."""

    existing = [path for path in paths if path.exists()]
    if not existing:
        return True

    gc.collect()
    if sys.platform != "win32":
        return True

    renamed: list[tuple[Path, Path]] = []
    token = f".engram-release-probe-{time.time_ns()}"
    try:
        for path in existing:
            probe = path.with_name(f"{path.name}{token}")
            try:
                path.replace(probe)
            except FileNotFoundError:
                continue
            except PermissionError:
                return False
            renamed.append((path, probe))
        return True
    finally:
        restore_errors: list[str] = []
        for original, probe in reversed(renamed):
            try:
                if probe.exists():
                    probe.replace(original)
            except FileNotFoundError:
                continue
            except OSError as exc:
                restore_errors.append(f"{probe} -> {original}: {exc}")
        if restore_errors:
            raise RuntimeError(
                "Failed to restore database files after release probe: "
                + "; ".join(restore_errors)
            )


def wait_for_database_release(
    paths: Sequence[Path],
    *,
    timeout: float | None = None,
) -> None:
    """Wait until SQLite database files are releasable."""

    budget = 30.0 if sys.platform == "win32" else 1.0
    if timeout is not None:
        budget = timeout
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if database_files_releasable(paths):
            return
        time.sleep(0.05)
    if database_files_releasable(paths):
        return
    candidates = [str(path) for path in paths if path.exists()]
    raise RuntimeError("database files remain in use: " + ", ".join(candidates))


def wait_for_vault_database_release(
    vault_path: Path,
    *,
    timeout: float | None = None,
) -> None:
    """Wait until known sqlite files inside a vault are releasable."""

    wait_for_database_release(vault_sqlite_candidate_paths(vault_path), timeout=timeout)


def _close_method(resource: object) -> Any | None:
    for name in ("close", "stop", "shutdown", "cleanup"):
        closer = getattr(resource, name, None)
        if callable(closer):
            return closer
    return None
