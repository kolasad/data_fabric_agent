"""PostgreSQL discovery via the SQLAlchemy inspector.

Enumerates schemas, tables, columns, primary keys, foreign keys and comments,
and normalizes them into the physical :class:`Resource` model.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine import Inspector

from agent_data_fabric.config import Settings, redact_dsn
from agent_data_fabric.core.models import Resource, ResourceType, Schema
from agent_data_fabric.discovery.base import select_schemas
from agent_data_fabric.metadata.extractor import build_table


class PostgresDiscovery:
    """Discovery plugin for PostgreSQL databases."""

    resource_type = ResourceType.postgres.value

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def discover(self, dsn: str) -> Resource:
        engine = create_engine(dsn)
        try:
            return self.discover_with_engine(engine, dsn)
        finally:
            engine.dispose()

    def discover_with_engine(self, engine: Engine, dsn: str) -> Resource:
        inspector = inspect(engine)
        database = engine.url.database or "postgres"

        schema_names = select_schemas(
            available=inspector.get_schema_names(),
            include=self.settings.include_schemas,
            exclude=self.settings.exclude_schemas,
        )

        schemas: list[Schema] = []
        for schema_name in schema_names:
            tables = self._discover_schema(inspector, schema_name)
            if tables.tables:
                schemas.append(tables)

        return Resource(
            type=ResourceType.postgres,
            name=database,
            connection_ref=redact_dsn(dsn),
            schemas=schemas,
        )

    def _discover_schema(self, inspector: Inspector, schema_name: str) -> Schema:
        table_names = inspector.get_table_names(schema=schema_name)
        view_names = inspector.get_view_names(schema=schema_name)

        schema = Schema(name=schema_name)
        for name in [*table_names, *view_names]:
            schema.tables.append(build_table(inspector, schema_name, name))
        return schema
