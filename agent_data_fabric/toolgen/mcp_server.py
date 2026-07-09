"""Wire the read-only tools into an MCP server driven by the semantic model."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import Engine

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import SemanticModel
from agent_data_fabric.toolgen import tools
from agent_data_fabric.toolgen.tools import ToolError

SERVER_NAME = "agent-data-fabric"


def create_mcp_server(
    model: SemanticModel,
    engine: Engine | None = None,
    *,
    allow_query: bool = False,
    settings: Settings | None = None,
) -> FastMCP:
    """Build a :class:`FastMCP` server exposing tools for ``model``.

    ``list_entities`` and ``describe_entity`` work from the model alone.
    ``sample_rows`` requires ``engine``. ``run_select`` is only registered when
    ``allow_query`` is true (and also requires ``engine``).
    """

    settings = settings or Settings()
    server = FastMCP(SERVER_NAME)

    @server.tool()
    def list_entities() -> list[dict[str, Any]]:
        """List all discovered entities with descriptions and field counts."""
        return tools.list_entities(model)

    @server.tool()
    def describe_entity(name: str) -> dict[str, Any]:
        """Describe one entity: columns, types, primary key and relationships."""
        return _guarded(lambda: tools.describe_entity(model, name))

    @server.tool()
    def sample_rows(entity: str, limit: int | None = None) -> dict[str, Any]:
        """Return a small, capped sample of rows from an entity's source table."""
        return _guarded(lambda: tools.sample_rows(engine, model, entity, limit, settings))

    if allow_query:

        @server.tool()
        def run_select(sql: str) -> dict[str, Any]:
            """Run a guarded, read-only SELECT. Non-SELECT statements are rejected."""
            return _guarded(lambda: tools.run_select(engine, sql, settings))

    return server


def _guarded(fn: Any) -> Any:
    """Convert :class:`ToolError` into a plain message the client can render."""

    try:
        return fn()
    except ToolError as exc:
        return {"error": str(exc)}
