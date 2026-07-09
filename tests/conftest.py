"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from agent_data_fabric.core.models import (
    Column,
    ForeignKeyRef,
    Resource,
    ResourceType,
    Schema,
    SemanticModel,
    Table,
)
from agent_data_fabric.metadata.relationships import infer_relationships
from agent_data_fabric.semantic.builder import build_semantic_model


@pytest.fixture
def shop_resource() -> Resource:
    """A hand-built physical resource mirroring examples/seed.sql.

    Includes an FK edge (orders.customer_id -> customers.id) and a heuristic-only
    edge (reviews.customer_id -> customers.id, no FK).
    """

    customers = Table(
        schema_name="shop",
        name="customers",
        comment="People who place orders.",
        columns=[
            Column(name="id", data_type="INTEGER", nullable=False, primary_key=True),
            Column(name="email", data_type="TEXT", nullable=False),
            Column(name="full_name", data_type="TEXT", nullable=False),
        ],
    )
    orders = Table(
        schema_name="shop",
        name="orders",
        columns=[
            Column(name="id", data_type="INTEGER", nullable=False, primary_key=True),
            Column(
                name="customer_id",
                data_type="INTEGER",
                nullable=False,
                foreign_key=ForeignKeyRef(schema_name="shop", table="customers", column="id"),
            ),
            Column(name="status", data_type="TEXT"),
        ],
    )
    reviews = Table(
        schema_name="shop",
        name="reviews",
        columns=[
            Column(name="id", data_type="INTEGER", nullable=False, primary_key=True),
            Column(name="product_id", data_type="INTEGER", nullable=False),
            Column(name="customer_id", data_type="INTEGER", nullable=False),
            Column(name="rating", data_type="SMALLINT", nullable=False),
        ],
    )
    return Resource(
        type=ResourceType.postgres,
        name="shopdb",
        connection_ref="postgresql://app@localhost:5432/shopdb",
        schemas=[Schema(name="shop", tables=[customers, orders, reviews])],
    )


@pytest.fixture
def shop_model(shop_resource: Resource) -> SemanticModel:
    relationships = infer_relationships(shop_resource)
    return build_semantic_model(shop_resource, relationships)


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """In-memory SQLite engine seeded with a single ``items`` table.

    SQLite accepts the ``main`` schema qualifier, so schema-qualified access used
    by the tools works without a Postgres instance.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE items ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "price INTEGER NOT NULL)"
            )
        )
        conn.execute(text("INSERT INTO items (id, name, price) VALUES (1, 'a', 10), (2, 'b', 20)"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_model() -> SemanticModel:
    """A semantic model matching the ``items`` table in ``sqlite_engine``."""

    items = Table(
        schema_name="main",
        name="items",
        columns=[
            Column(name="id", data_type="INTEGER", nullable=False, primary_key=True),
            Column(name="name", data_type="TEXT", nullable=False),
            Column(name="price", data_type="INTEGER", nullable=False),
        ],
    )
    resource = Resource(
        type=ResourceType.postgres,
        name="memdb",
        connection_ref="<redacted>",
        schemas=[Schema(name="main", tables=[items])],
    )
    return build_semantic_model(resource, [])
