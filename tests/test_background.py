from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engram import background
from engram._internal_tasks import (
    PROCESS_ITEM_TASK_NAME,
    internal_taskspec_names,
)
from engram.core.memory import Engram
from engram.runtime import weft as weft_runtime
from engram.store.sqlite import SQLiteStateStore


def test_internal_task_inventory_exposes_stable_names() -> None:
    assert internal_taskspec_names() == (PROCESS_ITEM_TASK_NAME,)


def test_submit_process_item_task_uses_vault_as_weft_metadata_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir()
    captured: dict[str, object] = {}

    def _fake_build_context(*, spec_context, config):  # type: ignore[no-untyped-def]
        captured["build_context_spec_context"] = spec_context
        captured["build_context_config"] = dict(config)
        weft_dir = Path(spec_context) / str(config["WEFT_DIRECTORY_NAME"])
        context = SimpleNamespace(
            root=Path(spec_context).resolve(),
            weft_dir=weft_dir.resolve(),
            database_path=(weft_dir / "broker.db").resolve(),
            broker_target="engram-weft-target",
            broker_config={
                key: value
                for key, value in dict(config).items()
                if key.startswith("BROKER_")
            },
            config=dict(config),
        )
        return context

    class _FakeWeftClient:
        def __init__(self, context):  # type: ignore[no-untyped-def]
            self.context = context

        @classmethod
        def from_weft_context(cls, context):  # type: ignore[no-untyped-def]
            captured["context"] = context
            return cls(context)

        def submit(self, taskspec, *, payload=None, **overrides):  # type: ignore[no-untyped-def]
            captured["taskspec"] = taskspec
            captured["payload"] = payload
            captured["overrides"] = dict(overrides)
            return SimpleNamespace(tid="1837000000000000000")

    def _fake_load_embedded_weft_config(path):  # type: ignore[no-untyped-def]
        captured["config_vault_path"] = Path(path)
        return {
            "WEFT_DIRECTORY_NAME": ".engram",
            "BROKER_DEFAULT_DB_NAME": ".engram/broker.db",
            "BROKER_BACKEND": "sqlite",
        }

    monkeypatch.setattr(
        weft_runtime,
        "load_embedded_weft_config",
        _fake_load_embedded_weft_config,
    )
    monkeypatch.setattr(weft_runtime, "build_context", _fake_build_context)
    monkeypatch.setattr(weft_runtime, "WeftClient", _FakeWeftClient)

    task_tid = weft_runtime.submit_process_item_task(vault_path, item_id=123)

    context = captured["context"]
    taskspec = captured["taskspec"]
    assert task_tid.isdigit()
    assert task_tid == "1837000000000000000"
    assert captured["config_vault_path"] == vault_path
    assert captured["build_context_spec_context"] == tmp_path
    assert captured["build_context_config"]["WEFT_DIRECTORY_NAME"] == ".engram"
    assert (
        captured["build_context_config"]["BROKER_DEFAULT_DB_NAME"]
        == ".engram/broker.db"
    )
    assert context.root == tmp_path.resolve()
    assert context.weft_dir == vault_path.resolve()
    assert context.database_path == (vault_path / "broker.db").resolve()
    assert context.config["WEFT_DIRECTORY_NAME"] == ".engram"
    assert taskspec.name == PROCESS_ITEM_TASK_NAME
    assert taskspec.spec.function_target == "engram.background:process_memory_task"
    assert taskspec.spec.weft_context == str(tmp_path.resolve())
    assert taskspec.metadata["internal_task_name"] == PROCESS_ITEM_TASK_NAME
    assert captured["payload"] == {
        "payload": {"vault_path": str(vault_path), "item_id": 123}
    }
    assert captured["overrides"] == {}


def test_initialize_embedded_weft_project_calls_weft_init_with_vault_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    captured: dict[str, object] = {}

    def _fake_load_embedded_weft_overrides(path):  # type: ignore[no-untyped-def]
        captured["overrides_vault_path"] = Path(path)
        return {
            "WEFT_DIRECTORY_NAME": ".engram",
            "WEFT_DEFAULT_DB_LOCATION": "",
            "WEFT_DEFAULT_DB_NAME": ".engram/broker.db",
        }

    def _fake_weft_cmd_init(directory, *, quiet, autostart, overrides):  # type: ignore[no-untyped-def]
        captured["directory"] = Path(directory)
        captured["quiet"] = quiet
        captured["autostart"] = autostart
        captured["overrides"] = dict(overrides)
        return 0

    monkeypatch.setattr(
        weft_runtime,
        "load_embedded_weft_overrides",
        _fake_load_embedded_weft_overrides,
    )
    monkeypatch.setattr(weft_runtime, "weft_cmd_init", _fake_weft_cmd_init)

    weft_runtime.initialize_embedded_weft_project(vault_path)

    assert captured["overrides_vault_path"] == vault_path.resolve()
    assert captured["directory"] == tmp_path.resolve()
    assert captured["quiet"] is True
    assert captured["autostart"] is True
    assert captured["overrides"] == {
        "WEFT_DIRECTORY_NAME": ".engram",
        "WEFT_DEFAULT_DB_LOCATION": "",
        "WEFT_DEFAULT_DB_NAME": ".engram/broker.db",
    }


def test_engram_init_can_disable_embedded_weft_autostart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    captured: dict[str, object] = {}

    def _fake_initialize(vault, *, autostart):  # type: ignore[no-untyped-def]
        captured["vault"] = Path(vault)
        captured["autostart"] = autostart

    monkeypatch.setattr(
        "engram.core.memory.weft_runtime.initialize_embedded_weft_project",
        _fake_initialize,
    )

    memory = Engram.init(vault_path, autostart=False)
    try:
        assert captured["vault"] == vault_path.resolve()
        assert captured["autostart"] is False
    finally:
        memory.close()


def test_engram_record_can_skip_background_submission(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    submitted: list[int] = []

    monkeypatch.setattr(
        "engram.core.memory.weft_runtime.initialize_embedded_weft_project",
        lambda vault, *, autostart: None,
    )
    monkeypatch.setattr(
        "engram.core.memory.weft_runtime.submit_process_item_task",
        lambda vault, *, item_id: submitted.append(item_id) or "123",
    )

    memory = Engram.init(vault_path, submit_background=False)
    try:
        item_id = memory.record("No background submission for deterministic replay.")
    finally:
        memory.close()

    assert item_id > 0
    assert submitted == []


def test_process_memory_task_uses_repair_item_and_records_success(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    memory = Engram.init(vault_path)
    item_id = memory.record("Decision: Weft and repair must share one operation.")
    memory.close()

    result = background.process_memory_task(
        {
            "vault_path": str(vault_path),
            "item_id": item_id,
        }
    )

    reopened = Engram.open(vault_path)
    try:
        stored = reopened.recall(item_id, count_access=False)
        status = reopened.status()
    finally:
        reopened.close()

    assert result["processed_ids"] == [item_id]
    assert set(result) == {
        "processed_ids",
        "created_episode_ids",
        "created_arc_ids",
        "failed_item_ids",
        "processed_count",
        "is_idle",
    }
    assert result["processed_count"] == 1
    assert result["is_idle"] is False
    assert stored.indexed_at is not None
    assert status.items_needing_processing == 0
    assert status.failed_processing_items == 0


def test_process_memory_task_failure_is_recorded_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault_path = tmp_path / ".engram"
    memory = Engram.init(vault_path)
    item_id = memory.record("Decision: worker failures should be inspectable.")
    memory.close()

    def _fake_process(self, subject_id):  # type: ignore[no-untyped-def]
        del self, subject_id
        raise RuntimeError("worker boom")

    monkeypatch.setattr(Engram, "process_item_operation", _fake_process)

    with pytest.raises(RuntimeError, match="worker boom"):
        background.process_memory_task(
            {
                "vault_path": str(vault_path),
                "item_id": item_id,
            }
        )

    reopened = Engram.open(vault_path)
    try:
        status = reopened.status()
        stored = reopened.recall(item_id, count_access=False)
    finally:
        reopened.close()

    assert status.items_needing_processing == 1
    assert status.failed_processing_items == 1
    assert status.failed_items[0].id == item_id
    assert "worker boom" in status.failed_items[0].error
    assert status.failed_items[0].processing_attempts == 1
    assert stored.indexed_at is None


def test_process_memory_task_open_failure_records_with_domain_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_path = tmp_path / ".engram"
    memory = Engram.init(vault_path, submit_background=False)
    item_id = memory.record("Decision: open failures still mark work failed.")
    memory.close()

    def _fail_open(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise RuntimeError("open boom")

    monkeypatch.setattr(Engram, "open", _fail_open)

    with pytest.raises(RuntimeError, match="open boom"):
        background.process_memory_task(
            {
                "vault_path": str(vault_path),
                "item_id": item_id,
            }
        )

    store = SQLiteStateStore(vault_path, create=False)
    try:
        assert store.count_failed_processing_items() == 1
        failed_items = store.list_failed_items(limit=5)
    finally:
        store.close()

    assert failed_items[0].id == item_id
    assert "open boom" in failed_items[0].error
