"""Tests for the run_select SQL safety guard."""

from __future__ import annotations

import pytest

from agent_data_fabric.toolgen.guard import QueryNotAllowed, validate_select


def test_select_gets_limit_injected() -> None:
    out = validate_select("SELECT id FROM shop.orders", max_limit=100)
    assert "LIMIT 100" in out.upper()


def test_existing_limit_is_capped() -> None:
    out = validate_select("SELECT * FROM t LIMIT 5000", max_limit=100)
    assert "LIMIT 100" in out.upper()
    assert "5000" not in out


def test_existing_small_limit_is_preserved() -> None:
    out = validate_select("SELECT * FROM t LIMIT 10", max_limit=100)
    assert "LIMIT 10" in out.upper()


def test_cte_select_is_allowed() -> None:
    sql = "WITH x AS (SELECT 1 AS n) SELECT n FROM x"
    out = validate_select(sql, max_limit=50)
    assert "LIMIT 50" in out.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t (a) VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE t",
        "SELECT 1; SELECT 2",
        "SELECT * FROM t FOR UPDATE",
        "",
        "   ",
    ],
)
def test_disallowed_statements_rejected(sql: str) -> None:
    with pytest.raises(QueryNotAllowed):
        validate_select(sql, max_limit=100)


def test_write_disguised_as_cte_rejected() -> None:
    # sqlglot parses data-modifying CTEs; ensure the walk() guard catches them.
    sql = "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d"
    with pytest.raises(QueryNotAllowed):
        validate_select(sql, max_limit=100)
