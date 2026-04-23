from __future__ import annotations

import importlib
from pathlib import Path

from engram._constants import (
    ENV_WEFT_BACKEND,
    ENV_WEFT_BACKEND_TARGET,
    ENV_WEFT_DEBUG,
    ENV_WEFT_DEFAULT_DB_LOCATION,
    ENV_WEFT_DEFAULT_DB_NAME,
    ENV_WEFT_DIRECTORY_NAME,
    load_embedded_weft_config,
    load_embedded_weft_overrides,
)


def test_load_embedded_weft_overrides_translates_engram_namespace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir()
    monkeypatch.setenv(ENV_WEFT_DEBUG, "1")
    monkeypatch.setenv(ENV_WEFT_BACKEND, "postgres")
    monkeypatch.setenv(
        ENV_WEFT_BACKEND_TARGET,
        "postgresql://broker@db.example.com/simplebroker",
    )
    monkeypatch.setenv(ENV_WEFT_DIRECTORY_NAME, ".custom-engram")
    monkeypatch.setenv(ENV_WEFT_DEFAULT_DB_LOCATION, str(tmp_path / "elsewhere"))
    monkeypatch.setenv(ENV_WEFT_DEFAULT_DB_NAME, ".custom-engram/custom.db")

    overrides = load_embedded_weft_overrides(vault_path)

    assert overrides["WEFT_DIRECTORY_NAME"] == ".engram"
    assert overrides["WEFT_DEBUG"] == "1"
    assert overrides["WEFT_BACKEND"] == "postgres"
    assert (
        overrides["WEFT_BACKEND_TARGET"]
        == "postgresql://broker@db.example.com/simplebroker"
    )
    assert overrides["WEFT_DEFAULT_DB_LOCATION"] == ""
    assert overrides["WEFT_DEFAULT_DB_NAME"] == ".engram/broker.db"


def test_load_embedded_weft_config_forces_vault_owned_sqlite_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / ".engram"
    vault_path.mkdir()
    monkeypatch.setenv(ENV_WEFT_DIRECTORY_NAME, ".custom-engram")
    monkeypatch.setenv(ENV_WEFT_DEFAULT_DB_LOCATION, str(tmp_path / "elsewhere"))
    monkeypatch.setenv(ENV_WEFT_DEFAULT_DB_NAME, ".custom-engram/custom.db")

    weft_constants = importlib.import_module("weft._constants")

    def _fake_load_config(overrides=None):  # type: ignore[no-untyped-def]
        config = {
            "WEFT_DEBUG": False,
            "WEFT_LOGGING_ENABLED": False,
            "BROKER_DEFAULT_DB_LOCATION": "",
            "BROKER_DEFAULT_DB_NAME": ".weft/broker.db",
        }
        if overrides is not None:
            config.update(overrides)
            if "WEFT_DEFAULT_DB_LOCATION" in overrides:
                config["BROKER_DEFAULT_DB_LOCATION"] = overrides[
                    "WEFT_DEFAULT_DB_LOCATION"
                ]
            if "WEFT_DEFAULT_DB_NAME" in overrides:
                config["BROKER_DEFAULT_DB_NAME"] = overrides["WEFT_DEFAULT_DB_NAME"]
        return config

    monkeypatch.setattr(weft_constants, "load_config", _fake_load_config)

    config = load_embedded_weft_config(vault_path)

    assert config["WEFT_DIRECTORY_NAME"] == ".engram"
    assert config["WEFT_DEFAULT_DB_LOCATION"] == ""
    assert config["WEFT_DEFAULT_DB_NAME"] == ".engram/broker.db"
    assert config["BROKER_DEFAULT_DB_LOCATION"] == ""
    assert config["BROKER_DEFAULT_DB_NAME"] == ".engram/broker.db"
