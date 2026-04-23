from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engram.core.embeddings import DeterministicEmbedder
from engram.core.memory import Engram
from tests.fixtures import resource_cleanup
from tests.fixtures.resource_cleanup import (
    ResourceTracker,
    database_files_releasable,
    ensure_windows_cleanup,
    sqlite_candidate_paths,
    wait_for_database_release,
    wait_for_vault_database_release,
)


class _Closeable:
    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    def close(self) -> None:
        self._calls.append(self._name)


class _BrokenCloseable:
    def close(self) -> None:
        raise RuntimeError("close failed")


def test_resource_tracker_closes_in_reverse_order() -> None:
    calls: list[str] = []
    tracker = ResourceTracker()
    tracker.register(_Closeable("first", calls))
    tracker.register(_Closeable("second", calls))

    tracker.close_all()

    assert calls == ["second", "first"]


def test_resource_tracker_surfaces_close_failures() -> None:
    tracker = ResourceTracker()
    tracker.register(_BrokenCloseable())

    with pytest.raises(ExceptionGroup, match="resource cleanup failed") as exc_info:
        tracker.close_all()

    assert len(exc_info.value.exceptions) == 1
    assert "close failed" in str(exc_info.value.exceptions[0])


def test_ensure_windows_cleanup_runs_second_gc_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(resource_cleanup.sys, "platform", "win32")
    monkeypatch.setattr(resource_cleanup.gc, "collect", lambda: calls.append("gc"))
    monkeypatch.setattr(
        resource_cleanup.time,
        "sleep",
        lambda seconds: calls.append(f"sleep:{seconds}"),
    )

    ensure_windows_cleanup()

    assert calls == ["gc", "sleep:0.1", "gc"]


def test_sqlite_candidate_paths_includes_existing_sidecars(tmp_path: Path) -> None:
    db_path = tmp_path / "engram.db"
    for path in (
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        Path(f"{db_path}-journal"),
    ):
        path.write_text("x", encoding="utf-8")

    assert sqlite_candidate_paths(db_path) == [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        Path(f"{db_path}-journal"),
    ]


def test_database_files_releasable_restores_windows_probe_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "engram.db"
    wal_path = Path(f"{db_path}-wal")
    db_path.write_text("db", encoding="utf-8")
    wal_path.write_text("wal", encoding="utf-8")
    monkeypatch.setattr(resource_cleanup.sys, "platform", "win32")

    assert database_files_releasable([db_path, wal_path]) is True

    assert db_path.read_text(encoding="utf-8") == "db"
    assert wal_path.read_text(encoding="utf-8") == "wal"
    assert list(tmp_path.glob("*.engram-release-probe-*")) == []


def test_wait_for_database_release_waits_through_transient_locked_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "engram.db"
    db_path.write_text("db", encoding="utf-8")
    states = iter([False, False, True])
    checks: list[str] = []
    clock = {"now": 0.0}

    def fake_releasable(paths):  # type: ignore[no-untyped-def]
        checks.append(str(paths[0]))
        return next(states)

    monkeypatch.setattr(resource_cleanup, "database_files_releasable", fake_releasable)
    monkeypatch.setattr(resource_cleanup.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        resource_cleanup.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    wait_for_database_release([db_path], timeout=1.0)

    assert checks == [str(db_path), str(db_path), str(db_path)]


def test_wait_for_database_release_raises_with_locked_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "engram.db"
    db_path.write_text("db", encoding="utf-8")
    clock = {"now": 0.0}

    monkeypatch.setattr(
        resource_cleanup, "database_files_releasable", lambda paths: False
    )
    monkeypatch.setattr(resource_cleanup.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        resource_cleanup.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with pytest.raises(RuntimeError, match="database files remain in use"):
        wait_for_database_release([db_path], timeout=0.1)


def test_tracker_closes_real_engram_before_tempdir_removal(tmp_path: Path) -> None:
    root = tmp_path / "run"
    vault_path = root / ".engram"
    tracker = ResourceTracker()
    memory = tracker.register(
        Engram.init(
            vault_path,
            autostart=False,
            embedder=DeterministicEmbedder(),
        )
    )

    memory.record("Decision: cleanup must release sqlite handles.")
    tracker.close_all()
    ensure_windows_cleanup()
    wait_for_vault_database_release(vault_path)

    shutil.rmtree(root)
    assert not root.exists()
