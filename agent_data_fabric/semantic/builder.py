"""Build a :class:`SemanticModel` from a physical resource + relationships."""

from __future__ import annotations

import hashlib
import json

from agent_data_fabric.core.models import (
    Entity,
    Relationship,
    Resource,
    SemanticField,
    SemanticModel,
    Table,
)


def build_semantic_model(
    resource: Resource,
    relationships: list[Relationship],
) -> SemanticModel:
    """Map tables -> entities and columns -> fields, attaching relationships."""

    entities = [_entity_from_table(t) for t in resource.tables]
    return SemanticModel(
        resource_name=resource.name,
        resource_type=resource.type,
        source_fingerprint=compute_fingerprint(resource),
        entities=entities,
        relationships=relationships,
    )


def _entity_from_table(table: Table) -> Entity:
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
    return Entity(
        name=entity_name_for(table.schema_name, table.name),
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
