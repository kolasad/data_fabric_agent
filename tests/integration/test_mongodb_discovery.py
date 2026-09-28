"""End-to-end discovery against a real MongoDB instance.

Requires Docker. Automatically skipped when Docker/testcontainers is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import RelationshipSource
from agent_data_fabric.pipeline import discover_to_model
from agent_data_fabric.semantic.model_io import load_model, save_model

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mongo_dsn() -> Iterator[str]:
    try:
        from pymongo import MongoClient
        from testcontainers.mongodb import MongoDbContainer
    except ImportError:  # pragma: no cover
        pytest.skip("testcontainers/pymongo not installed")

    try:
        container = MongoDbContainer("mongo:7.0")
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker may be unavailable
        pytest.skip(f"Docker/testcontainers unavailable: {exc}")

    dsn = container.get_connection_url().rstrip("/") + "/shopdb"
    client = MongoClient(dsn)
    try:
        _seed(client["shopdb"])
        yield dsn
    finally:
        client.close()
        container.stop()


def _seed(db) -> None:  # type: ignore[no-untyped-def]
    db.customers.insert_many(
        [
            {"_id": 1, "name": "Alice", "email": "alice@example.com"},
            {"_id": 2, "name": "Bob", "email": "bob@example.com"},
        ]
    )
    db.reviews.insert_many(
        [
            {"_id": 100, "customer_id": 1, "rating": 5, "comment": "Great!"},
        ]
    )


def test_discover_builds_expected_model(mongo_dsn: str, tmp_path: Path) -> None:
    model = discover_to_model(mongo_dsn, resource_type="mongodb", settings=Settings())

    entity_names = {e.name for e in model.entities}
    assert {"shopdb.customers", "shopdb.reviews"} <= entity_names

    # Heuristic edge (reviews.customer_id -> customers._id), no real FK in Mongo.
    assert any(
        r.from_table == "reviews"
        and r.from_column == "customer_id"
        and r.to_table == "customers"
        and r.source == RelationshipSource.heuristic
        for r in model.relationships
    )

    # Model round-trips through disk.
    path = save_model(model, tmp_path / "fabric.model.yaml")
    reloaded = load_model(path)
    assert reloaded.source_fingerprint == model.source_fingerprint
