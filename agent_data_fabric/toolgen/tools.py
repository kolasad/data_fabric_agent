"""Read-only tool implementations, decoupled from the MCP transport.

Each function takes explicit dependencies (the semantic model, and where data
access is needed, a SQLAlchemy :class:`Engine`) so the logic can be unit-tested
without a running MCP server.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import uuid
from typing import Any

from sqlalchemy import Engine, text

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import SemanticModel
from agent_data_fabric.toolgen.guard import QueryNotAllowed, validate_select


class ToolError(RuntimeError):
    """Raised for user-facing tool failures (unknown entity, no connection, ...)."""


def list_entities(model: SemanticModel) -> list[dict[str, Any]]:
    """Return every entity with a short description and its field count."""

    return [
        {
            "name": entity.name,
            "source_table": entity.source_table,
            "description": entity.description,
            "primary_key": entity.primary_key,
            "field_count": len(entity.fields),
            "row_estimate": entity.row_estimate,
        }
        for entity in model.entities
    ]


def describe_entity(model: SemanticModel, name: str) -> dict[str, Any]:
    """Return columns, types and relationships for a single entity."""

    entity = model.get_entity(name)
    if entity is None:
        raise ToolError(f"Unknown entity '{name}'. Use list_entities() to see available entities.")

    relationships = [
        {
            "from": f"{rel.from_qualified}.{rel.from_column}",
            "to": f"{rel.to_qualified}.{rel.to_column}",
            "kind": rel.kind.value,
            "source": rel.source.value,
            "confidence": rel.confidence,
        }
        for rel in model.relationships_for(name)
    ]

    return {
        "name": entity.name,
        "source_table": entity.source_table,
        "description": entity.description,
        "primary_key": entity.primary_key,
        "row_estimate": entity.row_estimate,
        "fields": [
            {
                "name": field.name,
                "data_type": field.data_type,
                "nullable": field.nullable,
                "primary_key": field.primary_key,
                "description": field.description,
            }
            for field in entity.fields
        ],
        "relationships": relationships,
    }


def sample_rows(
    engine: Engine | None,
    model: SemanticModel,
    entity: str,
    limit: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return up to ``limit`` rows (capped) from an entity's source table."""

    settings = settings or Settings()
    entity_model = model.get_entity(entity)
    if entity_model is None:
        raise ToolError(
            f"Unknown entity '{entity}'. Use list_entities() to see available entities."
        )
    engine = _require_engine(engine)

    effective_limit = settings.default_sample_limit if limit is None else int(limit)
    effective_limit = max(1, min(effective_limit, settings.max_sample_limit))

    schema_name, _, table_name = entity_model.source_table.partition(".")
    qualified = f"{_quote_ident(schema_name)}.{_quote_ident(table_name)}"
    sql = f"SELECT * FROM {qualified} LIMIT {effective_limit}"

    rows, columns = _execute(engine, sql, settings.query_timeout_seconds)
    return {
        "entity": entity,
        "source_table": entity_model.source_table,
        "limit": effective_limit,
        "columns": columns,
        "row_count": len(rows),
        "rows": rows,
    }


def run_select(
    engine: Engine | None,
    sql: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute a guarded, read-only SELECT and return rows."""

    settings = settings or Settings()
    engine = _require_engine(engine)
    try:
        guarded_sql = validate_select(sql, settings.max_sample_limit)
    except QueryNotAllowed as exc:
        raise ToolError(f"Query rejected: {exc}") from exc

    rows, columns = _execute(engine, guarded_sql, settings.query_timeout_seconds)
    return {
        "executed_sql": guarded_sql,
        "columns": columns,
        "row_count": len(rows),
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_engine(engine: Engine | None) -> Engine:
    if engine is None:
        raise ToolError(
            "No database connection is configured. Start the server with a DSN "
            "(--dsn or AGENT_FABRIC_DSN) to enable data access."
        )
    return engine


def _quote_ident(identifier: str) -> str:
    """Safely quote a SQL identifier (double-quote escaping)."""

    return '"' + identifier.replace('"', '""') + '"'


def _execute(
    engine: Engine, sql: str, timeout_seconds: int
) -> tuple[list[dict[str, Any]], list[str]]:
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(f"SET statement_timeout = {int(timeout_seconds) * 1000}"))
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [{key: _jsonify(value) for key, value in row.items()} for row in result.mappings()]
    return rows, columns


def _jsonify(value: Any) -> Any:
    """Coerce a database value into something JSON-serializable."""

    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, _dt.datetime | _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    if isinstance(value, list | tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    return str(value)
