"""Build a :class:`SemanticModel` from one or more physical resources."""

from __future__ import annotations

import hashlib
import json

from agent_data_fabric.core.models import (
    Entity,
    Relationship,
    Resource,
    ResourceModel,
    SemanticField,
    SemanticModel,
    Table,
)


def build_semantic_model(
    resource: Resource,
    relationships: list[Relationship],
) -> SemanticModel:
    """Map one resource's tables -> entities and columns -> fields.

    A thin, unprefixed-entity-names convenience over
    :func:`build_semantic_model_multi` for the common single-resource case.
    """

    return build_semantic_model_multi([(resource, relationships)])


def build_semantic_model_multi(
    resources: list[tuple[Resource, list[Relationship]]],
) -> SemanticModel:
    """Build one model spanning one :class:`ResourceModel` per input resource.

    Entity names are prefixed with the resource name only when more than one
    resource is present, to keep lookups unambiguous; a single resource keeps
    today's unprefixed names, so existing single-resource models are unaffected.
    """

    prefix_entities = len(resources) > 1
    resource_models = [
        _build_resource_model(resource, relationships, prefix_entities=prefix_entities)
        for resource, relationships in resources
    ]
    return SemanticModel(resources=resource_models)


def _build_resource_model(
    resource: Resource,
    relationships: list[Relationship],
    *,
    prefix_entities: bool,
) -> ResourceModel:
    prefix = resource.name if prefix_entities else None
    entities = [_entity_from_table(t, prefix) for t in resource.tables]
    return ResourceModel(
        resource_name=resource.name,
        resource_type=resource.type,
        source_fingerprint=compute_fingerprint(resource),
        entities=entities,
        relationships=relationships,
    )


def _entity_from_table(table: Table, resource_prefix: str | None = None) -> Entity:
    fields = [
        SemanticField(
            name=col.name,
            data_type=col.data_type,
            nullable=col.nullable,
            primary_key=col.primary_key,
            description=col.comment,
        )
        for col in table.columns
    ]
    name = entity_name_for(table.schema_name, table.name)
    # Mongo's schema name *is* the resource name, so entity_name_for already
    # embeds it (e.g. "shopdb.customers") — don't double-prefix in that case.
    if resource_prefix and not name.startswith(f"{resource_prefix}."):
        name = f"{resource_prefix}.{name}"
    return Entity(
        name=name,
        source_table=table.qualified_name,
        description=table.comment,
        primary_key=table.primary_key,
        row_estimate=table.row_estimate,
        fields=fields,
    )


def entity_name_for(schema_name: str, table_name: str) -> str:
    """Public-facing entity name. ``public`` tables drop the schema prefix."""

    if schema_name == "public":
        return table_name
    return f"{schema_name}.{table_name}"


def compute_fingerprint(resource: Resource) -> str:
    """Stable hash of the physical structure, used for change detection.

    Excludes volatile fields (row estimates, connection ref) so re-running
    discovery against an unchanged schema yields an identical fingerprint.
    """

    skeleton = {
        "type": resource.type.value,
        "name": resource.name,
        "schemas": [
            {
                "name": schema.name,
                "tables": [
                    {
                        "name": table.name,
                        "columns": [
                            {
                                "name": col.name,
                                "data_type": col.data_type,
                                "nullable": col.nullable,
                                "primary_key": col.primary_key,
                                "foreign_key": (
                                    col.foreign_key.model_dump() if col.foreign_key else None
                                ),
                            }
                            for col in table.columns
                        ],
                    }
                    for table in sorted(schema.tables, key=lambda t: t.name)
                ],
            }
            for schema in sorted(resource.schemas, key=lambda s: s.name)
        ],
    }
    payload = json.dumps(skeleton, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
