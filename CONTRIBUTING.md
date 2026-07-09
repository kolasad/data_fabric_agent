# Contributing

Thanks for your interest in Agent Data Fabric.

## Setup

```bash
poetry install
pre-commit install
```

## Workflow

- Create a working branch; do not push to `master`/`main` directly.
- Keep changes focused and match the surrounding style.
- Add or update tests for non-trivial changes.

## Quality gates

Run before opening a PR (these also run in CI):

```bash
poetry run ruff check .
poetry run black --check .
poetry run mypy agent_data_fabric
poetry run pytest
```

Integration tests require Docker:

```bash
poetry run pytest -m integration
```

## Adding a connector

1. Implement a discovery plugin satisfying `core.registry.DiscoveryPlugin`.
2. Register it in `core.registry.build_default_registry`.
3. Add unit tests for normalization and an integration test if a container image exists.
