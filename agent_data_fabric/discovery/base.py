"""Shared discovery helpers."""

from __future__ import annotations

from collections.abc import Iterable


def select_schemas(
    available: Iterable[str],
    include: Iterable[str],
    exclude: Iterable[str],
) -> list[str]:
    """Resolve which schemas to introspect.

    ``include`` wins when non-empty; otherwise everything not in ``exclude`` is
    used. The result preserves discovery order and is de-duplicated.
    """

    include_set = {s for s in include}
    exclude_set = {s for s in exclude}

    result: list[str] = []
    for name in available:
        if include_set:
            if name in include_set and name not in result:
                result.append(name)
        elif name not in exclude_set and name not in result:
            result.append(name)
    return result
