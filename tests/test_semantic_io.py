"""Tests for semantic model building, fingerprinting and IO round-trips."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_data_fabric.core.models import Resource, SemanticModel
from agent_data_fabric.metadata.relationships import infer_relationships
from agent_data_fabric.semantic.builder import (
    build_semantic_model,
    compute_fingerprint,
    entity_name_for,
)
from agent_data_fabric.semantic.model_io import load_model, save_model


def test_entity_name_drops_public_prefix() -> None:
    assert entity_name_for("public", "orders") == "orders"
    assert entity_name_for("shop", "orders") == "shop.orders"


def test_build_semantic_model_maps_tables_and_relationships(shop_model: SemanticModel) -> None:
    names = {e.name for e in shop_model.entities}
    assert {"shop.customers", "shop.orders", "shop.reviews"} <= names

    customers = shop_model.get_entity("shop.customers")
    assert customers is not None
    assert customers.primary_key == ["id"]
    assert customers.description == "People who place orders."

    # relationships_for returns both incoming and outgoing edges.
    rels = shop_model.relationships_for("shop.customers")
    assert any(r.from_table == "orders" for r in rels)


def test_fingerprint_is_stable_and_structure_sensitive(shop_resource: Resource) -> None:
    fp1 = compute_fingerprint(shop_resource)
    fp2 = compute_fingerprint(shop_resource.model_copy(deep=True))
    assert fp1 == fp2

    mutated = shop_resource.model_copy(deep=True)
    mutated.schemas[0].tables[0].columns[0].data_type = "BIGINT"
    assert compute_fingerprint(mutated) != fp1


@pytest.mark.parametrize("filename", ["fabric.model.yaml", "fabric.model.json"])
def test_model_round_trip(shop_model: SemanticModel, tmp_path: Path, filename: str) -> None:
    path = save_model(shop_model, tmp_path / filename)
    assert path.exists()

    loaded = load_model(path)
    assert loaded.source_fingerprint == shop_model.source_fingerprint
    assert {e.name for e in loaded.entities} == {e.name for e in shop_model.entities}
    assert len(loaded.relationships) == len(shop_model.relationships)


def test_round_trip_preserves_relationship_details(shop_resource: Resource, tmp_path: Path) -> None:
    model = build_semantic_model(shop_resource, infer_relationships(shop_resource))
    loaded = load_model(save_model(model, tmp_path / "m.yaml"))
    original = {r.signature for r in model.relationships}
    assert {r.signature for r in loaded.relationships} == original
