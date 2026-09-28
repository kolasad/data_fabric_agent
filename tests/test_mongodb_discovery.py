"""Unit tests for MongoDB discovery, backed by ``mongomock`` (no Docker needed)."""

from __future__ import annotations

import mongomock
import pytest

from agent_data_fabric.config import Settings
from agent_data_fabric.discovery.mongodb import MongoDiscovery


@pytest.fixture
def client() -> mongomock.MongoClient:
    return mongomock.MongoClient()


def _seed(client: mongomock.MongoClient) -> None:
    db = client["shopdb"]
    db.customers.insert_many(
        [
            {"_id": 1, "name": "Alice", "email": "alice@example.com"},
            {"_id": 2, "name": "Bob", "email": None},
        ]
    )
    db.orders.insert_many(
        [
            {"_id": 10, "customer_id": 1, "total": 42.5, "placed_at": None},
            {"_id": 11, "customer_id": 2, "total": 10},
        ]
    )


def test_discover_infers_columns_and_types(client: mongomock.MongoClient) -> None:
    _seed(client)
    discovery = MongoDiscovery(settings=Settings())
    resource = discovery.discover_with_client(client, "mongodb://localhost/shopdb")

    assert resource.name == "shopdb"
    assert resource.type.value == "mongodb"

    customers = resource.get_table("shopdb", "customers")
    assert customers is not None

    id_col = customers.get_column("_id")
    assert id_col is not None
    assert id_col.primary_key is True

    name_col = customers.get_column("name")
    assert name_col is not None
    assert name_col.data_type == "string"
    assert name_col.primary_key is False


def test_field_nullability_and_missing_keys(client: mongomock.MongoClient) -> None:
    _seed(client)
    discovery = MongoDiscovery(settings=Settings())
    resource = discovery.discover_with_client(client, "mongodb://localhost/shopdb")

    customers = resource.get_table("shopdb", "customers")
    assert customers is not None
    email_col = customers.get_column("email")
    assert email_col is not None
    assert email_col.data_type == "string"
    assert email_col.nullable is True  # Bob's email is explicitly None

    name_col = customers.get_column("name")
    assert name_col is not None
    assert name_col.nullable is False  # present and non-null on every sampled doc

    orders = resource.get_table("shopdb", "orders")
    assert orders is not None
    placed_col = orders.get_column("placed_at")
    assert placed_col is not None
    assert placed_col.nullable is True  # present but None on one doc

    total_col = orders.get_column("total")
    assert total_col is not None
    assert set(total_col.data_type.split("|")) <= {"int", "double"}


def test_no_foreign_keys_are_synthesized(client: mongomock.MongoClient) -> None:
    _seed(client)
    discovery = MongoDiscovery(settings=Settings())
    resource = discovery.discover_with_client(client, "mongodb://localhost/shopdb")

    orders = resource.get_table("shopdb", "orders")
    assert orders is not None
    customer_id_col = orders.get_column("customer_id")
    assert customer_id_col is not None
    assert customer_id_col.foreign_key is None


def test_collection_include_filter(client: mongomock.MongoClient) -> None:
    _seed(client)
    settings = Settings(include_collections=["customers"])
    discovery = MongoDiscovery(settings=settings)
    resource = discovery.discover_with_client(client, "mongodb://localhost/shopdb")

    assert {t.name for t in resource.tables} == {"customers"}


def test_collection_exclude_filter(client: mongomock.MongoClient) -> None:
    _seed(client)
    settings = Settings(exclude_collections=["orders"])
    discovery = MongoDiscovery(settings=settings)
    resource = discovery.discover_with_client(client, "mongodb://localhost/shopdb")

    assert {t.name for t in resource.tables} == {"customers"}


def test_missing_default_database_raises() -> None:
    client = mongomock.MongoClient()
    discovery = MongoDiscovery(settings=Settings())

    with pytest.raises(ValueError, match="default database"):
        discovery.discover_with_client(client, "mongodb://localhost")
