"""Tests for configuration and DSN redaction."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_data_fabric.config import Settings, load_resource_specs, redact_dsn, resolve_config_path


def test_redact_dsn_removes_password() -> None:
    dsn = "postgresql+psycopg://user:supersecret@db.example.com:5432/app"
    redacted = redact_dsn(dsn)
    assert "supersecret" not in redacted
    assert "user" in redacted
    assert "db.example.com:5432" in redacted
    assert redacted.endswith("/app")


def test_redact_dsn_handles_no_credentials() -> None:
    dsn = "postgresql://db.example.com/app"
    assert "db.example.com" in redact_dsn(dsn)


def test_redact_dsn_drops_non_url() -> None:
    assert redact_dsn("host=localhost password=secret") == "<redacted>"


def test_settings_split_csv_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGENT_FABRIC_INCLUDE_SCHEMAS", "public, sales ,ops")
    settings = Settings()
    assert settings.include_schemas == ["public", "sales", "ops"]


def test_resolve_config_path_missing_default_is_none(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_FABRIC_CONFIG", raising=False)
    assert resolve_config_path(None) is None


def test_resolve_config_path_missing_explicit_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(FileNotFoundError):
        resolve_config_path(tmp_path / "does-not-exist.yaml")


def test_resolve_config_path_missing_env_raises(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_FABRIC_CONFIG", "does-not-exist.yaml")
    with pytest.raises(FileNotFoundError):
        resolve_config_path(None)


def test_settings_reads_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text(
        "dsn: postgresql+psycopg://readonly:secret@db.example.com:5432/app\n"
        "mongo_sample_size: 250\n"
        "include_schemas: [public, sales]\n",
        encoding="utf-8",
    )
    settings = Settings(_config_file=config_path)

    assert settings.dsn == "postgresql+psycopg://readonly:secret@db.example.com:5432/app"
    assert settings.mongo_sample_size == 250
    assert settings.include_schemas == ["public", "sales"]


def test_env_overrides_config_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text("mongo_sample_size: 250\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_FABRIC_MONGO_SAMPLE_SIZE", "500")

    settings = Settings(_config_file=config_path)

    assert settings.mongo_sample_size == 500


def test_cli_kwarg_overrides_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text("mongo_sample_size: 250\n", encoding="utf-8")

    settings = Settings(_config_file=config_path, mongo_sample_size=999)

    assert settings.mongo_sample_size == 999


def test_missing_default_config_file_is_not_an_error(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_FABRIC_CONFIG", raising=False)

    settings = Settings()

    assert settings.mongo_sample_size == 100  # falls through to the field default


def test_load_resource_specs_absent_returns_none(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text("mongo_sample_size: 50\n", encoding="utf-8")

    assert load_resource_specs(config_path) is None


def test_load_resource_specs_reads_list(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text(
        "resources:\n"
        "  - dsn: postgresql+psycopg://readonly:secret@crm.example.com:5432/app\n"
        "    name: crm\n"
        "  - dsn: mongodb://readonly:secret@support.example.com:27017/app\n"
        "    type: mongodb\n"
        "    mongo_sample_size: 50\n",
        encoding="utf-8",
    )

    specs = load_resource_specs(config_path)

    assert specs is not None
    assert len(specs) == 2
    assert specs[0]["name"] == "crm"
    assert specs[1]["type"] == "mongodb"
    assert specs[1]["mongo_sample_size"] == 50


def test_load_resource_specs_rejects_non_list(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text("resources: not-a-list\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a list"):
        load_resource_specs(config_path)


def test_load_resource_specs_requires_dsn(tmp_path: Path) -> None:
    config_path = tmp_path / "fabric.config.yaml"
    config_path.write_text("resources:\n  - name: crm\n", encoding="utf-8")

    with pytest.raises(ValueError, match="'dsn'"):
        load_resource_specs(config_path)
