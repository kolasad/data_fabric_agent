"""MongoDB discovery via schema-on-read sampling.

MongoDB collections have no declared schema, so discovery infers one: each
collection's field names and types are derived from a bounded sample of its
documents. There are no real foreign keys either — ``metadata/relationships.py``'s
naming heuristic (``*_id``/``*_fk`` -> ``<table>.id``) is left to infer references,
unmodified, exactly as it does for Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from bson import ObjectId
from pymongo import MongoClient

from agent_data_fabric.config import Settings, redact_dsn
from agent_data_fabric.core.models import Column, Resource, ResourceType, Schema, Table
from agent_data_fabric.discovery.base import select_schemas


@dataclass
class _FieldInfo:
    """Accumulates the observed shape of one field across sampled documents."""

    types: set[str] = field(default_factory=set)
    seen_count: int = 0
    saw_none: bool = False

    def observe(self, value: Any) -> None:
        self.seen_count += 1
        if value is None:
            self.saw_none = True
            return
        self.types.add(_type_name(value))

    def data_type(self) -> str:
        return "|".join(sorted(self.types)) if self.types else "null"

    def is_nullable(self, total_documents: int) -> bool:
        return self.saw_none or self.seen_count < total_documents


def _default_database_name(dsn: str) -> str | None:
    """Extract the database name from a Mongo connection string's path."""

    return urlsplit(dsn).path.lstrip("/") or None


def _type_name(value: Any) -> str:
    # bool is a subclass of int in Python, so it must be checked first.
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, ObjectId):
        return "objectId"
    if isinstance(value, datetime):
        return "date"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "object"


class MongoDiscovery:
    """Discovery plugin for MongoDB databases."""

    resource_type = ResourceType.mongodb.value

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def discover(self, dsn: str) -> Resource:
        client: MongoClient = MongoClient(dsn)
        try:
            return self.discover_with_client(client, dsn)
        finally:
            client.close()

    def discover_with_client(self, client: MongoClient, dsn: str) -> Resource:
        no_default_db = ValueError(
            "MongoDB DSN must include a default database, e.g. mongodb://host:27017/mydb"
        )
        # Prefer the database name from `dsn` directly: it's the source of truth (and the
        # only option when `client` wasn't itself constructed from a URI, e.g. in tests).
        db_name = _default_database_name(dsn)
        if db_name:
            db = client[db_name]
        else:
            try:
                db = client.get_default_database()
            except Exception as exc:  # noqa: BLE001 - pymongo/mongomock raise on a missing name
                raise no_default_db from exc
            if db is None:
                raise no_default_db

        collection_names = select_schemas(
            available=db.list_collection_names(),
            include=self.settings.include_collections,
            exclude=self.settings.exclude_collections,
        )

        schema = Schema(name=db.name)
        for name in collection_names:
            schema.tables.append(self._discover_collection(db, name))

        return Resource(
            type=ResourceType.mongodb,
            name=db.name,
            connection_ref=redact_dsn(dsn),
            schemas=[schema] if schema.tables else [],
        )

    def _discover_collection(self, db: Any, name: str) -> Table:
        collection = db[name]
        sample_size = self.settings.mongo_sample_size
        documents = list(collection.find().limit(sample_size))

        fields: dict[str, _FieldInfo] = {}
        for document in documents:
            for key, value in document.items():
                fields.setdefault(key, _FieldInfo()).observe(value)

        total_documents = len(documents)
        columns = [
            Column(
                name=field_name,
                data_type=info.data_type(),
                nullable=info.is_nullable(total_documents),
                primary_key=field_name == "_id",
            )
            for field_name, info in fields.items()
        ]

        return Table(
            schema_name=db.name,
            name=name,
            row_estimate=collection.count_documents({}),
            columns=columns,
        )
