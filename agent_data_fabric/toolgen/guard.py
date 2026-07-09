"""SQL safety guard for the optional ``run_select`` tool.

The guard parses SQL with ``sqlglot`` and rejects anything that is not a single
read-only ``SELECT``/CTE statement. It also enforces a hard ``LIMIT`` so an agent
cannot exfiltrate an entire table in one call. This is defense-in-depth: the
docs still recommend connecting with a read-only database role.
"""

from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp

DIALECT = "postgres"


class QueryNotAllowed(ValueError):
    """Raised when a query fails the safety guard."""


def _is_read_only_select(statement: exp.Expression) -> bool:
    """True if the top-level statement is a SELECT (optionally wrapped in a CTE/UNION)."""

    if isinstance(statement, exp.Select | exp.Union):
        return True
    if isinstance(statement, exp.Subquery):
        return _is_read_only_select(statement.this)
    return False


def validate_select(sql: str, max_limit: int) -> str:
    """Validate and normalize ``sql``; return guarded SQL or raise.

    Rules:
    * Exactly one statement (no stacked queries).
    * Statement must be a ``SELECT``/CTE/``UNION`` (no DML/DDL/utility commands).
    * No row-locking clauses (``FOR UPDATE`` / ``FOR SHARE``).
    * A ``LIMIT`` <= ``max_limit`` is enforced (added or capped).
    """

    if not sql or not sql.strip():
        raise QueryNotAllowed("Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise QueryNotAllowed(f"Could not parse SQL: {exc}") from exc

    if len(statements) != 1:
        raise QueryNotAllowed("Exactly one statement is allowed.")

    statement = statements[0]

    if isinstance(statement, exp.Command):
        raise QueryNotAllowed("Utility/DDL commands are not allowed.")

    if not _is_read_only_select(statement):
        raise QueryNotAllowed("Only read-only SELECT statements are allowed.")

    if statement.args.get("locks"):
        raise QueryNotAllowed("Row-locking clauses (FOR UPDATE/SHARE) are not allowed.")

    # Belt-and-suspenders: reject any embedded write expression anywhere in the tree.
    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Merge,
    )
    if any(isinstance(node, forbidden) for node in statement.walk()):
        raise QueryNotAllowed("Data-modifying statements are not allowed.")

    return _apply_limit(cast(exp.Query, statement), max_limit).sql(dialect=DIALECT)


def _apply_limit(statement: exp.Query, max_limit: int) -> exp.Query:
    current = _current_limit(statement)
    effective = max_limit if current is None else min(current, max_limit)
    return statement.limit(effective)


def _current_limit(statement: exp.Query) -> int | None:
    limit_node = statement.args.get("limit")
    if limit_node is None:
        return None
    try:
        return int(limit_node.expression.name)
    except (AttributeError, ValueError, TypeError):
        return None
