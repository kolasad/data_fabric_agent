"""Tests for multi-resource semantic models (builder + pipeline)."""

from __future__ import annotations

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import Column, Resource, ResourceType, Schema, Table
from agent_data_fabric.core.registry import PluginRegistry
from agent_data_fabric.metadata.relationships import infer_relationships
from agent_data_fabric.pipeline import discover_resources_to_model
from agent_data_fabric.semantic.builder import build_semantic_model, build_semantic_model_multi


def _customers_resource(resource_type: ResourceType, name: str) -> Resource:
    """Two resources that both happen to have a `customers` table/collection."""

    table = Table(
        schema_name="public" if resource_type == ResourceType.postgres else name,
        name="customers",
        columns=[
            Column(name="id", data_type="int", primary_key=True),
            Column(name="email", data_type="string"),
        ],
    )
    return Resource(
        type=resource_type,
        name=name,
        connection_ref="<redacted>",
        schemas=[Schema(name=table.schema_name, tables=[table])],
    )


def test_single_resource_entities_are_unprefixed() -> None:
    resource = _customers_resource(ResourceType.postgres, "crm")
    model = build_semantic_model(resource, [])

    assert len(model.resources) == 1
    assert {e.name for e in model.entities} == {"customers"}
    assert model.get_entity("customers") is not None
    assert model.source_fingerprint == model.resources[0].source_fingerprint


def test_multi_resource_entities_are_prefixed_to_avoid_collisions() -> None:
    crm = _customers_resource(ResourceType.postgres, "crm")
    support = _customers_resource(ResourceType.mongodb, "support")

    model = build_semantic_model_multi([(crm, []), (support, [])])

    assert len(model.resources) == 2
    entity_names = {e.name for e in model.entities}
    assert entity_names == {"crm.customers", "support.customers"}

    assert model.get_entity("crm.customers") is not None
    assert model.get_entity("support.customers") is not None
    assert model.get_entity("customers") is None  # unprefixed lookup no longer matches

    assert model.get_resource("crm") is not None
    assert model.get_resource("support") is not None
    assert model.get_resource("nope") is None


def test_multi_resource_relationships_stay_scoped_per_resource() -> None:
    crm = _customers_resource(ResourceType.postgres, "crm")
    support = _customers_resource(ResourceType.mongodb, "support")

    model = build_semantic_model_multi(
        [(crm, infer_relationships(crm)), (support, infer_relationships(support))]
    )

    # Neither resource has FK/heuristic edges here (no *_id columns); this just
    # asserts relationships_for still resolves through the right resource.
    assert model.relationships_for("crm.customers") == []
    assert model.relationships_for("support.customers") == []


def test_combined_fingerprint_differs_from_either_resource_alone() -> None:
    crm = _customers_resource(ResourceType.postgres, "crm")
    support = _customers_resource(ResourceType.mongodb, "support")

    single = build_semantic_model(crm, [])
    combined = build_semantic_model_multi([(crm, []), (support, [])])

    assert combined.source_fingerprint != single.source_fingerprint
    assert combined.source_fingerprint == combined.model_copy(deep=True).source_fingerprint


class _FakeDiscovery:
    """An in-memory DiscoveryPlugin for testing the multi-resource pipeline."""

    def __init__(self, resource_type: str, resource: Resource) -> None:
        self.resource_type = resource_type
        self._resource = resource

    def discover(self, dsn: str) -> Resource:  # noqa: ARG002 - dsn unused by the fake
        return self._resource


def test_discover_resources_to_model_merges_specs() -> None:
    crm = _customers_resource(ResourceType.postgres, "crm")
    support = _customers_resource(ResourceType.mongodb, "support")

    registry = PluginRegistry()
    registry.register_discovery(_FakeDiscovery("postgres", crm))
    registry.register_discovery(_FakeDiscovery("mongodb", support))

    model = discover_resources_to_model(
        [
            {"dsn": "postgresql://crm", "type": "postgres"},
            {"dsn": "mongodb://support", "type": "mongodb"},
        ],
        base_settings=Settings(),
        registry=registry,
    )

    assert len(model.resources) == 2
    assert {e.name for e in model.entities} == {"crm.customers", "support.customers"}


def test_discover_resources_to_model_sniffs_missing_type() -> None:
    support = _customers_resource(ResourceType.mongodb, "support")
    registry = PluginRegistry()
    registry.register_discovery(_FakeDiscovery("mongodb", support))

    model = discover_resources_to_model(
        [{"dsn": "mongodb://support/db"}],  # no explicit "type"
        registry=registry,
    )

    assert len(model.resources) == 1
    assert model.resources[0].resource_type == ResourceType.mongodb
