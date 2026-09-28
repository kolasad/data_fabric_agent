"""Domain models for the Agent Data Fabric vertical slice.

The models fall into two layers:

* **Physical layer** (`Resource` -> `Schema` -> `Table` -> `Column`): a faithful,
  provider-specific description of what discovery found in the environment.
* **Semantic layer** (`SemanticModel` -> `Entity` -> `Field` + `Relationship`):
  a normalized, agent-friendly view derived from the physical layer.

Relationships are shared between the two layers because they are the primary
output of relationship inference.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, NonNegativeInt, field_validator

SEMANTIC_MODEL_VERSION = "0.2"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class ResourceType(str, Enum):
    """Type of a discovered resource."""

    postgres = "postgres"
    mongodb = "mongodb"


class RelationshipKind(str, Enum):
    """Cardinality of an inferred relationship, from the source column's view."""

    many_to_one = "many_to_one"
    one_to_one = "one_to_one"
    one_to_many = "one_to_many"
    many_to_many = "many_to_many"


class RelationshipSource(str, Enum):
    """How a relationship was discovered."""

    fk = "fk"
    heuristic = "heuristic"


# --------------------------------------------------------------------------- #
# Physical layer
# --------------------------------------------------------------------------- #
class ForeignKeyRef(BaseModel):
    """A reference from a column to a target table column."""

    schema_name: str
    table: str
    column: str

    @property
    def qualified_table(self) -> str:
        return f"{self.schema_name}.{self.table}"


class Column(BaseModel):
    """A single column of a physical table."""

    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    foreign_key: ForeignKeyRef | None = None
    default: str | None = None
    comment: str | None = None


class Table(BaseModel):
    """A physical table (or view treated as a table)."""

    schema_name: str
    name: str
    comment: str | None = None
    row_estimate: NonNegativeInt | None = None
    columns: list[Column] = Field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.name}"

    @property
    def primary_key(self) -> list[str]:
        return [c.name for c in self.columns if c.primary_key]

    def get_column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


class Schema(BaseModel):
    """A database schema/namespace."""

    name: str
    tables: list[Table] = Field(default_factory=list)


class Resource(BaseModel):
    """A discovered data resource (a single database, in this slice).

    `connection_ref` is a **redacted**, credential-free identifier so the model
    can be safely serialized to disk and shared.
    """

    type: ResourceType
    name: str
    connection_ref: str
    schemas: list[Schema] = Field(default_factory=list)

    @property
    def tables(self) -> list[Table]:
        return [t for schema in self.schemas for t in schema.tables]

    def get_table(self, schema_name: str, table: str) -> Table | None:
        return next(
            (t for t in self.tables if t.schema_name == schema_name and t.name == table),
            None,
        )


# --------------------------------------------------------------------------- #
# Relationships (shared)
# --------------------------------------------------------------------------- #
class Relationship(BaseModel):
    """A directional relationship between two tables/entities."""

    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    kind: RelationshipKind
    source: RelationshipSource
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def _round_confidence(cls, value: float) -> float:
        return round(value, 3)

    @property
    def from_qualified(self) -> str:
        return f"{self.from_schema}.{self.from_table}"

    @property
    def to_qualified(self) -> str:
        return f"{self.to_schema}.{self.to_table}"

    @property
    def signature(self) -> tuple[str, str, str, str, str, str]:
        """Stable identity used for de-duplication."""

        return (
            self.from_schema,
            self.from_table,
            self.from_column,
            self.to_schema,
            self.to_table,
            self.to_column,
        )


# --------------------------------------------------------------------------- #
# Semantic layer
# --------------------------------------------------------------------------- #
class SemanticField(BaseModel):
    """An agent-facing field derived from a physical column."""

    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    description: str | None = None


class Entity(BaseModel):
    """An agent-facing entity derived from a physical table."""

    name: str
    source_table: str
    description: str | None = None
    primary_key: list[str] = Field(default_factory=list)
    row_estimate: NonNegativeInt | None = None
    fields: list[SemanticField] = Field(default_factory=list)

    def get_field(self, name: str) -> SemanticField | None:
        return next((f for f in self.fields if f.name == name), None)


class ResourceModel(BaseModel):
    """One discovered resource's entities and relationships within a model.

    Relationships are scoped to their own resource — cross-resource inference
    isn't attempted (a naive naming match across unrelated systems would be
    noise, not signal); that's future work, not a silent gap.
    """

    resource_name: str
    resource_type: ResourceType
    source_fingerprint: str
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    def get_entity(self, name: str) -> Entity | None:
        return next((e for e in self.entities if e.name == name), None)

    def relationships_for(self, entity_name: str) -> list[Relationship]:
        entity = self.get_entity(entity_name)
        if entity is None:
            return []
        table = entity.source_table
        return [
            r for r in self.relationships if r.from_qualified == table or r.to_qualified == table
        ]


class SemanticModel(BaseModel):
    """The serialized output of the discovery pipeline.

    Holds one :class:`ResourceModel` per discovered resource. ``entities``,
    ``relationships``, ``source_fingerprint``, ``get_entity`` and
    ``relationships_for`` are convenience views flattened across every
    resource, so single-resource callers (the common case) don't need to know
    this is a list underneath.
    """

    version: str = SEMANTIC_MODEL_VERSION
    generated_at: datetime = Field(default_factory=_utcnow)
    resources: list[ResourceModel] = Field(default_factory=list)

    @property
    def entities(self) -> list[Entity]:
        return [entity for resource in self.resources for entity in resource.entities]

    @property
    def relationships(self) -> list[Relationship]:
        return [rel for resource in self.resources for rel in resource.relationships]

    @property
    def source_fingerprint(self) -> str:
        """A single resource's fingerprint, or a stable combined hash for several."""

        if len(self.resources) == 1:
            return self.resources[0].source_fingerprint
        payload = "|".join(
            f"{r.resource_name}:{r.source_fingerprint}"
            for r in sorted(self.resources, key=lambda r: r.resource_name)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_resource(self, resource_name: str) -> ResourceModel | None:
        return next((r for r in self.resources if r.resource_name == resource_name), None)

    def get_entity(self, name: str) -> Entity | None:
        for resource in self.resources:
            entity = resource.get_entity(name)
            if entity is not None:
                return entity
        return None

    def relationships_for(self, entity_name: str) -> list[Relationship]:
        for resource in self.resources:
            if resource.get_entity(entity_name) is not None:
                return resource.relationships_for(entity_name)
        return []
