"""Tests for relationship inference."""

from __future__ import annotations

from agent_data_fabric.core.models import (
    Column,
    ForeignKeyRef,
    RelationshipKind,
    RelationshipSource,
    Resource,
    ResourceType,
    Schema,
    Table,
)
from agent_data_fabric.metadata.relationships import infer_relationships


def test_fk_relationship_is_authoritative(shop_resource: Resource) -> None:
    rels = infer_relationships(shop_resource)
    fk_edges = [r for r in rels if r.source == RelationshipSource.fk]
    orders_fk = next(
        r for r in fk_edges if r.from_table == "orders" and r.from_column == "customer_id"
    )
    assert orders_fk.to_table == "customers"
    assert orders_fk.to_column == "id"
    assert orders_fk.confidence == 1.0
    assert orders_fk.kind == RelationshipKind.many_to_one


def test_heuristic_relationship_inferred_without_fk(shop_resource: Resource) -> None:
    rels = infer_relationships(shop_resource)
    review_edge = next(
        r for r in rels if r.from_table == "reviews" and r.from_column == "customer_id"
    )
    assert review_edge.source == RelationshipSource.heuristic
    assert review_edge.to_table == "customers"
    assert review_edge.to_column == "id"
    assert 0.0 < review_edge.confidence < 1.0


def test_no_duplicate_edges_and_fk_wins() -> None:
    # A column with an FK that would ALSO match the heuristic must not double-count.
    resource = Resource(
        type=ResourceType.postgres,
        name="db",
        connection_ref="<redacted>",
        schemas=[
            Schema(
                name="public",
                tables=[
                    Table(
                        schema_name="public",
                        name="users",
                        columns=[Column(name="id", data_type="int", primary_key=True)],
                    ),
                    Table(
                        schema_name="public",
                        name="posts",
                        columns=[
                            Column(name="id", data_type="int", primary_key=True),
                            Column(
                                name="user_id",
                                data_type="int",
                                foreign_key=ForeignKeyRef(
                                    schema_name="public", table="users", column="id"
                                ),
                            ),
                        ],
                    ),
                ],
            )
        ],
    )
    rels = infer_relationships(resource)
    user_edges = [r for r in rels if r.from_table == "posts" and r.from_column == "user_id"]
    assert len(user_edges) == 1
    assert user_edges[0].source == RelationshipSource.fk


def test_one_to_one_when_source_column_is_sole_pk() -> None:
    resource = Resource(
        type=ResourceType.postgres,
        name="db",
        connection_ref="<redacted>",
        schemas=[
            Schema(
                name="public",
                tables=[
                    Table(
                        schema_name="public",
                        name="users",
                        columns=[Column(name="id", data_type="int", primary_key=True)],
                    ),
                    Table(
                        schema_name="public",
                        name="profiles",
                        columns=[
                            Column(
                                name="user_id",
                                data_type="int",
                                primary_key=True,
                                foreign_key=ForeignKeyRef(
                                    schema_name="public", table="users", column="id"
                                ),
                            )
                        ],
                    ),
                ],
            )
        ],
    )
    rels = infer_relationships(resource)
    edge = next(r for r in rels if r.from_table == "profiles")
    assert edge.kind == RelationshipKind.one_to_one
