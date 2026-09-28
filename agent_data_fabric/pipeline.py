"""End-to-end discovery pipeline: DSN(s) -> SemanticModel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import Relationship, Resource, ResourceType, SemanticModel
from agent_data_fabric.core.registry import PluginRegistry, build_default_registry
from agent_data_fabric.metadata.relationships import infer_relationships
from agent_data_fabric.semantic.builder import build_semantic_model, build_semantic_model_multi

_MONGO_SCHEMES = ("mongodb://", "mongodb+srv://")


def sniff_resource_type(dsn: str) -> str:
    """Guess the resource type from the DSN scheme, e.g. when ``--type`` is omitted."""

    if dsn.startswith(_MONGO_SCHEMES):
        return ResourceType.mongodb.value
    return ResourceType.postgres.value


def discover_to_model(
    dsn: str,
    *,
    resource_type: str = ResourceType.postgres.value,
    settings: Settings | None = None,
    registry: PluginRegistry | None = None,
) -> SemanticModel:
    """Run discovery -> relationship inference -> semantic model for one resource."""

    settings = settings or Settings()
    registry = registry or build_default_registry()

    resource, relationships = _discover_one(dsn, resource_type, settings, registry)
    return build_semantic_model(resource, relationships)


def discover_resources_to_model(
    resource_specs: Sequence[Mapping[str, Any]],
    *,
    base_settings: Settings | None = None,
    registry: PluginRegistry | None = None,
) -> SemanticModel:
    """Discover several resources (a config file's ``resources:`` list) into one model.

    Each spec needs a ``dsn``; ``type`` is sniffed from the DSN when omitted.
    Any other keys are treated as per-resource :class:`Settings` overrides
    (e.g. ``mongo_sample_size``, ``include_schemas``) layered on top of
    ``base_settings`` for that resource only.
    """

    base_settings = base_settings or Settings()
    registry = registry or build_default_registry()

    pairs: list[tuple[Resource, list[Relationship]]] = []
    for spec in resource_specs:
        overrides = {k: v for k, v in spec.items() if k not in ("dsn", "type", "name")}
        dsn = spec["dsn"]
        resource_type = spec.get("type") or sniff_resource_type(dsn)
        resource_settings = (
            base_settings.model_copy(update=overrides) if overrides else base_settings
        )

        pairs.append(_discover_one(dsn, resource_type, resource_settings, registry))

    return build_semantic_model_multi(pairs)


def _discover_one(
    dsn: str,
    resource_type: str,
    settings: Settings,
    registry: PluginRegistry,
) -> tuple[Resource, list[Relationship]]:
    plugin = registry.get_discovery(resource_type)
    # Rebind settings for plugins that accept them (Postgres and MongoDB do).
    if hasattr(plugin, "settings"):
        plugin.settings = settings

    resource = plugin.discover(dsn)
    relationships = infer_relationships(resource)
    return resource, relationships
