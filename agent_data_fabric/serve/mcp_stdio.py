"""Run the generated MCP server over stdio."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from agent_data_fabric.config import Settings
from agent_data_fabric.semantic.model_io import load_model
from agent_data_fabric.toolgen.mcp_server import create_mcp_server


def serve_stdio(
    model_path: str | Path,
    *,
    dsn: str | None = None,
    allow_query: bool = False,
    settings: Settings | None = None,
) -> None:
    """Load a semantic model and run its MCP server on stdio (blocking)."""

    settings = settings or Settings()
    model = load_model(model_path)

    engine: Engine | None = None
    if dsn:
        engine = create_engine(dsn)

    server = create_mcp_server(
        model,
        engine,
        allow_query=allow_query,
        settings=settings,
    )
    try:
        server.run(transport="stdio")
    finally:
        if engine is not None:
            engine.dispose()
