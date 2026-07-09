"""End-to-end discovery pipeline: DSN -> SemanticModel."""

from __future__ import annotations

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import ResourceType, SemanticModel
from agent_data_fabric.core.registry import PluginRegistry, build_default_registry
from agent_data_fabric.metadata.relationships import infer_relationships
from agent_data_fabric.semantic.builder import build_semantic_model


def discover_to_model(
    dsn: str,
    *,
    resource_type: str = ResourceType.postgres.value,
    settings: Settings | None = None,
    registry: PluginRegistry | None = None,
) -> SemanticModel:
    """Run discovery -> relationship inference -> semantic model."""

    settings = settings or Settings()
    registry = registry or build_default_registry()

    plugin = registry.get_discovery(resource_type)
    # Rebind settings for plugins that accept them (Postgres does).
    if hasattr(plugin, "settings"):
        plugin.settings = settings

    resource = plugin.discover(dsn)
    relationships = infer_relationships(resource)
    return build_semantic_model(resource, relationships)
