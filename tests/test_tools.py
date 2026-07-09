"""Tests for the read-only tool implementations."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import SemanticModel
from agent_data_fabric.toolgen import tools
from agent_data_fabric.toolgen.tools import ToolError

ENTITY = "main.items"


def test_list_entities(sqlite_model: SemanticModel) -> None:
    result = tools.list_entities(sqlite_model)
    assert len(result) == 1
    assert result[0]["name"] == ENTITY
    assert result[0]["field_count"] == 3


def test_describe_entity(sqlite_model: SemanticModel) -> None:
    result = tools.describe_entity(sqlite_model, ENTITY)
    assert result["primary_key"] == ["id"]
    field_names = {f["name"] for f in result["fields"]}
    assert field_names == {"id", "name", "price"}


def test_describe_unknown_entity_raises(sqlite_model: SemanticModel) -> None:
    with pytest.raises(ToolError):
        tools.describe_entity(sqlite_model, "nope")


def test_sample_rows_returns_data(sqlite_engine: Engine, sqlite_model: SemanticModel) -> None:
    result = tools.sample_rows(sqlite_engine, sqlite_model, ENTITY, limit=1)
    assert result["limit"] == 1
    assert result["row_count"] == 1
    assert set(result["columns"]) == {"id", "name", "price"}


def test_sample_rows_limit_is_capped(sqlite_engine: Engine, sqlite_model: SemanticModel) -> None:
    settings = Settings(max_sample_limit=1)
    result = tools.sample_rows(sqlite_engine, sqlite_model, ENTITY, limit=999, settings=settings)
    assert result["limit"] == 1
    assert result["row_count"] == 1


def test_sample_rows_without_engine_raises(sqlite_model: SemanticModel) -> None:
    with pytest.raises(ToolError):
        tools.sample_rows(None, sqlite_model, ENTITY)


def test_run_select_executes_guarded_query(
    sqlite_engine: Engine, sqlite_model: SemanticModel
) -> None:
    result = tools.run_select(sqlite_engine, "SELECT id, name FROM items ORDER BY id")
    assert "LIMIT" in result["executed_sql"].upper()
    assert result["row_count"] == 2
    assert result["rows"][0]["id"] == 1


def test_run_select_rejects_non_select(sqlite_engine: Engine) -> None:
    with pytest.raises(ToolError):
        tools.run_select(sqlite_engine, "DELETE FROM items")
