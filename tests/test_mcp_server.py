"""Tests for MCP server tool registration."""

from __future__ import annotations

from agent_data_fabric.core.models import SemanticModel
from agent_data_fabric.toolgen.mcp_server import create_mcp_server


def _tool_names(server) -> set[str]:  # type: ignore[no-untyped-def]
    return {tool.name for tool in server._tool_manager.list_tools()}


def test_metadata_tools_always_registered(sqlite_model: SemanticModel) -> None:
    server = create_mcp_server(sqlite_model)
    names = _tool_names(server)
    assert {"list_entities", "describe_entity", "sample_rows"} <= names


def test_run_select_hidden_by_default(sqlite_model: SemanticModel) -> None:
    server = create_mcp_server(sqlite_model, allow_query=False)
    assert "run_select" not in _tool_names(server)


def test_run_select_registered_when_allowed(sqlite_model: SemanticModel) -> None:
    server = create_mcp_server(sqlite_model, allow_query=True)
    assert "run_select" in _tool_names(server)
