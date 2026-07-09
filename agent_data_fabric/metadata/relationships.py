"""Relationship inference.

Two signals are combined:

* **Foreign keys** — authoritative (confidence ``1.0``).
* **Naming heuristics** — columns like ``customer_id`` are matched to a table
  whose primary key is ``id`` (e.g. ``customer`` / ``customers``). Lower
  confidence, and never emitted when an FK already covers the same edge.

Cardinality is inferred from uniqueness of the source column: a source column
that is itself a primary key implies ``one_to_one``, otherwise ``many_to_one``.
"""

from __future__ import annotations

import re

from agent_data_fabric.core.models import (
    Relationship,
    RelationshipKind,
    RelationshipSource,
    Resource,
    Table,
)

_ID_SUFFIX = re.compile(r"^(?P<base>.+?)_(?:id|fk)$", re.IGNORECASE)
HEURISTIC_CONFIDENCE = 0.6


def infer_relationships(resource: Resource) -> list[Relationship]:
    """Return de-duplicated relationships inferred from ``resource``."""

    tables = resource.tables
    relationships: list[Relationship] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()

    for rel in _from_foreign_keys(tables):
        if rel.signature not in seen:
            seen.add(rel.signature)
            relationships.append(rel)

    for rel in _from_naming_heuristics(tables):
        if rel.signature not in seen:
            seen.add(rel.signature)
            relationships.append(rel)

    return relationships


def _kind_for_source_column(source_table: Table, column_name: str) -> RelationshipKind:
    column = source_table.get_column(column_name)
    if column is not None and column.primary_key and len(source_table.primary_key) == 1:
        return RelationshipKind.one_to_one
    return RelationshipKind.many_to_one


def _from_foreign_keys(tables: list[Table]) -> list[Relationship]:
    relationships: list[Relationship] = []
    for table in tables:
        for column in table.columns:
            fk = column.foreign_key
            if fk is None:
                continue
            relationships.append(
                Relationship(
                    from_schema=table.schema_name,
                    from_table=table.name,
                    from_column=column.name,
                    to_schema=fk.schema_name,
                    to_table=fk.table,
                    to_column=fk.column,
                    kind=_kind_for_source_column(table, column.name),
                    source=RelationshipSource.fk,
                    confidence=1.0,
                )
            )
    return relationships


def _singular_plural(base: str) -> set[str]:
    """Candidate table names for a heuristic base (very small stemmer)."""

    candidates = {base}
    if base.endswith("y"):
        candidates.add(f"{base[:-1]}ies")
    elif base.endswith(("s", "x", "z", "ch", "sh")):
        candidates.add(f"{base}es")
    else:
        candidates.add(f"{base}s")
    # Also allow already-plural bases to match a singular table name.
    if base.endswith("s"):
        candidates.add(base[:-1])
    return {c.lower() for c in candidates}


def _from_naming_heuristics(tables: list[Table]) -> list[Relationship]:
    # Index tables by lowercased name for candidate matching.
    by_name: dict[str, list[Table]] = {}
    for table in tables:
        by_name.setdefault(table.name.lower(), []).append(table)

    relationships: list[Relationship] = []
    for table in tables:
        for column in table.columns:
            if column.foreign_key is not None:
                continue  # FK already authoritative
            match = _ID_SUFFIX.match(column.name)
            if not match:
                continue
            base = match.group("base")
            target = _resolve_target(by_name, _singular_plural(base), table)
            if target is None:
                continue
            target_pk = target.primary_key
            if len(target_pk) != 1:
                continue
            relationships.append(
                Relationship(
                    from_schema=table.schema_name,
                    from_table=table.name,
                    from_column=column.name,
                    to_schema=target.schema_name,
                    to_table=target.name,
                    to_column=target_pk[0],
                    kind=_kind_for_source_column(table, column.name),
                    source=RelationshipSource.heuristic,
                    confidence=HEURISTIC_CONFIDENCE,
                )
            )
    return relationships


def _resolve_target(
    by_name: dict[str, list[Table]],
    candidates: set[str],
    source_table: Table,
) -> Table | None:
    """Pick a single unambiguous target table for the candidate names."""

    matches: list[Table] = []
    for candidate in candidates:
        matches.extend(by_name.get(candidate, []))

    # Prefer a target in the same schema; fall back to a unique cross-schema hit.
    same_schema = [t for t in matches if t.schema_name == source_table.schema_name]
    pool = same_schema or matches
    if len(pool) == 1:
        return pool[0]
    return None
