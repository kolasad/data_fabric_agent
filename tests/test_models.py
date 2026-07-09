"""Tests for core domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_data_fabric.core.models import (
    Column,
    Relationship,
    RelationshipKind,
    RelationshipSource,
    Table,
)


def test_table_qualified_name_and_primary_key() -> None:
    table = Table(
        schema_name="shop",
        name="orders",
        columns=[
            Column(name="id", data_type="int", primary_key=True),
            Column(name="status", data_type="text"),
        ],
    )
    assert table.qualified_name == "shop.orders"
    assert table.primary_key == ["id"]
    assert table.get_column("status") is not None
    assert table.get_column("missing") is None


def test_relationship_confidence_is_rounded_and_bounded() -> None:
    rel = Relationship(
        from_schema="shop",
        from_table="orders",
        from_column="customer_id",
        to_schema="shop",
        to_table="customers",
        to_column="id",
        kind=RelationshipKind.many_to_one,
        source=RelationshipSource.fk,
        confidence=0.66666,
    )
    assert rel.confidence == 0.667
    assert rel.from_qualified == "shop.orders"
    assert rel.to_qualified == "shop.customers"
    assert rel.signature == ("shop", "orders", "customer_id", "shop", "customers", "id")


def test_relationship_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Relationship(
            from_schema="s",
            from_table="a",
            from_column="x",
            to_schema="s",
            to_table="b",
            to_column="y",
            kind=RelationshipKind.many_to_one,
            source=RelationshipSource.fk,
            confidence=1.5,
        )
