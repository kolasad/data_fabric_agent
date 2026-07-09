"""End-to-end discovery against a real PostgreSQL instance.

Requires Docker. Automatically skipped when Docker/testcontainers is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import RelationshipSource
from agent_data_fabric.pipeline import discover_to_model
from agent_data_fabric.semantic.model_io import load_model, save_model
from agent_data_fabric.toolgen import tools

pytestmark = pytest.mark.integration

SEED_SQL = Path(__file__).resolve().parents[2] / "examples" / "seed.sql"


@pytest.fixture(scope="module")
def postgres_dsn() -> Iterator[str]:
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover
        pytest.skip("testcontainers not installed")

    try:
        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker may be unavailable
        pytest.skip(f"Docker/testcontainers unavailable: {exc}")

    dsn = container.get_connection_url()
    engine = create_engine(dsn)
    try:
        _seed(engine)
        yield dsn
    finally:
        engine.dispose()
        container.stop()


def _seed(engine: Engine) -> None:
    statements = [s.strip() for s in SEED_SQL.read_text().split(";") if s.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def test_discover_builds_expected_model(postgres_dsn: str, tmp_path: Path) -> None:
    settings = Settings(include_schemas=["shop"])
    model = discover_to_model(postgres_dsn, settings=settings)

    entity_names = {e.name for e in model.entities}
    assert {
        "shop.customers",
        "shop.orders",
        "shop.products",
        "shop.order_items",
        "shop.reviews",
    } <= entity_names

    # FK edge exists (orders.customer_id -> customers.id).
    assert any(
        r.from_table == "orders"
        and r.from_column == "customer_id"
        and r.to_table == "customers"
        and r.source == RelationshipSource.fk
        for r in model.relationships
    )

    # Heuristic edge exists (reviews.customer_id -> customers.id, no FK).
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


def test_tools_against_live_db(postgres_dsn: str) -> None:
    settings = Settings(include_schemas=["shop"])
    model = discover_to_model(postgres_dsn, settings=settings)
    engine = create_engine(postgres_dsn)
    try:
        sample = tools.sample_rows(engine, model, "shop.customers", limit=5, settings=settings)
        assert sample["row_count"] >= 1
        assert "email" in sample["columns"]

        selected = tools.run_select(
            engine, "SELECT id, email FROM shop.customers", settings=settings
        )
        assert selected["row_count"] >= 1
    finally:
        engine.dispose()
