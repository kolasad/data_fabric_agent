"""Tests for the CLI surface (no live database required)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_data_fabric.cli import app
from agent_data_fabric.core.models import SemanticModel
from agent_data_fabric.semantic.model_io import save_model

runner = CliRunner()


def test_inspect_renders_summary(shop_model: SemanticModel, tmp_path: Path) -> None:
    model_path = tmp_path / "fabric.model.yaml"
    save_model(shop_model, model_path)

    result = runner.invoke(app, ["inspect", "--model", str(model_path)])
    assert result.exit_code == 0
    assert "Entities" in result.stdout
    assert "shop.customers" in result.stdout


def test_inspect_missing_model_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", "--model", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2


def test_discover_without_dsn_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("AGENT_FABRIC_DSN", raising=False)
    result = runner.invoke(app, ["discover"])
    assert result.exit_code == 2


def test_serve_missing_model_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--model", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
