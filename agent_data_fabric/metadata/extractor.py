"""Normalize raw SQLAlchemy introspection into physical models."""

from __future__ import annotations

from sqlalchemy.engine import Inspector

from agent_data_fabric.core.models import Column, ForeignKeyRef, Table


def normalize_type(raw_type: object) -> str:
    """Render a SQLAlchemy column type as a compact, portable string."""

    text = str(raw_type).strip()
    return text or "unknown"


def build_table(inspector: Inspector, schema_name: str, table_name: str) -> Table:
    """Assemble a :class:`Table` from the inspector for one table."""

    pk_constraint = inspector.get_pk_constraint(table_name, schema=schema_name)
    pk_columns: set[str] = set(pk_constraint.get("constrained_columns") or [])

    fk_map = _foreign_key_map(inspector, schema_name, table_name)

    columns: list[Column] = []
    for col in inspector.get_columns(table_name, schema=schema_name):
        name = col["name"]
        default = col.get("default")
        columns.append(
            Column(
                name=name,
                data_type=normalize_type(col.get("type")),
                nullable=bool(col.get("nullable", True)),
                primary_key=name in pk_columns,
                foreign_key=fk_map.get(name),
                default=str(default) if default is not None else None,
                comment=col.get("comment"),
            )
        )

    table_comment: str | None = None
    try:
        table_comment = inspector.get_table_comment(table_name, schema=schema_name).get("text")
    except Exception:  # noqa: BLE001 - table comments are best-effort / dialect-specific
        table_comment = None

    return Table(
        schema_name=schema_name,
        name=table_name,
        comment=table_comment,
        columns=columns,
    )


def _foreign_key_map(
    inspector: Inspector, schema_name: str, table_name: str
) -> dict[str, ForeignKeyRef]:
    """Map each constrained column to its referenced target column.

    Composite foreign keys are expanded positionally so single-column lookups
    still resolve.
    """

    fk_map: dict[str, ForeignKeyRef] = {}
    for fk in inspector.get_foreign_keys(table_name, schema=schema_name):
        constrained = fk.get("constrained_columns") or []
        referred_columns = fk.get("referred_columns") or []
        referred_table = fk.get("referred_table")
        referred_schema = fk.get("referred_schema") or schema_name
        if not referred_table:
            continue
        for local_col, remote_col in zip(constrained, referred_columns, strict=False):
            fk_map[local_col] = ForeignKeyRef(
                schema_name=referred_schema,
                table=referred_table,
                column=remote_col,
            )
    return fk_map
