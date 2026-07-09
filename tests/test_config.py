"""Tests for configuration and DSN redaction."""

from __future__ import annotations

from agent_data_fabric.config import Settings, redact_dsn


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
