"""Plugin registry and protocols.

This slice ships a single Postgres discovery plugin, but the registry keeps the
extension seam explicit so future connectors (MongoDB, OpenAPI, ...) can be
registered without touching the pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_data_fabric.core.models import Relationship, Resource


@runtime_checkable
class DiscoveryPlugin(Protocol):
    """Discovers a resource and returns its physical model."""

    resource_type: str

    def discover(self, dsn: str) -> Resource:
        """Connect using ``dsn`` and return a populated :class:`Resource`."""
        ...


@runtime_checkable
class RelationshipInferencer(Protocol):
    """Infers relationships from a discovered resource."""

    def infer(self, resource: Resource) -> list[Relationship]: ...


class PluginRegistry:
    """A minimal in-memory registry keyed by resource type."""

    def __init__(self) -> None:
        self._discovery: dict[str, DiscoveryPlugin] = {}

    def register_discovery(self, plugin: DiscoveryPlugin) -> None:
        self._discovery[plugin.resource_type] = plugin

    def get_discovery(self, resource_type: str) -> DiscoveryPlugin:
        try:
            return self._discovery[resource_type]
        except KeyError as exc:  # pragma: no cover - defensive
            available = ", ".join(sorted(self._discovery)) or "<none>"
            raise KeyError(
                f"No discovery plugin registered for '{resource_type}'. " f"Available: {available}."
            ) from exc

    def discovery_types(self) -> list[str]:
        return sorted(self._discovery)


def build_default_registry() -> PluginRegistry:
    """Construct a registry with the built-in plugins wired up."""

    # Imported lazily to avoid a hard import cycle and to keep optional deps local.
    from agent_data_fabric.discovery.mongodb import MongoDiscovery
    from agent_data_fabric.discovery.postgres import PostgresDiscovery

    registry = PluginRegistry()
    registry.register_discovery(PostgresDiscovery())
    registry.register_discovery(MongoDiscovery())
    return registry
