# Agent Data Fabric — working notes for Claude Code

Discovers a data environment, builds a semantic model, and auto-generates a safe MCP
interface for AI agents. Full product context: `docs/Agent_Data_Fabric_Project_Brief.md`.
Current milestone status (source of truth, keep it updated as work lands): `docs/roadmap.md`.

## Commands

```bash
poetry install                        # install deps
poetry run pytest                     # unit tests (fast, no Docker)
poetry run pytest -m integration      # integration tests (needs Docker/testcontainers)
poetry run ruff check .
poetry run black --check .
poetry run mypy agent_data_fabric
pre-commit install                    # one-time, then runs on commit
```

Demo DB + CLI walkthrough: see `README.md` Quickstart.

## Architecture

Full writeup: `docs/architecture.md`. Pipeline:

```
DSN → Discovery → Metadata/Relationships → Semantic builder → fabric.model.yaml → Tool generation (MCP)
```

Two layered models in `core/models.py`:
- **Physical** (`Resource → Schema → Table → Column`) — provider-specific, faithful to the source.
- **Semantic** (`SemanticModel → Entity → SemanticField` + `Relationship`) — normalized, agent-facing.

## Adding a connector

1. Implement the `DiscoveryPlugin` protocol (`core/registry.py`): a `resource_type: str` and
   `discover(dsn: str) -> Resource`.
2. Split `discover(dsn)` (owns the client/engine lifecycle) from a
   `discover_with_<client>(client, dsn)` method so the mapping logic is unit-testable without a
   live connection — see `discovery/postgres.py`'s `discover`/`discover_with_engine` split.
3. Register the plugin in `core/registry.py:build_default_registry` (lazy import, same pattern
   as `PostgresDiscovery`, to keep optional deps out of the hot import path).
4. `metadata/relationships.py` needs **no changes** — it infers relationships generically over
   `Table`/`Column` (FK edges + `*_id`/`*_fk` naming heuristics), not against Postgres
   specifically.
5. Strip credentials before they reach the model (`config.redact_dsn`) — nothing with a
   password ever gets serialized to `fabric.model.yaml`.

## Conventions

- Pydantic v2 models throughout (`core/models.py`); keep new fields typed and validated there
  rather than passing around raw dicts.
- Read-only by default: no tool may write. `toolgen/guard.py` enforces this for `run_select`
  (SELECT-only, single statement, capped `LIMIT`, behind `--allow-query`); any new live-data
  tool needs an equivalent guard.
- No credentials on disk, ever — `connection_ref` is a redacted DSN.
- Tool logic (`toolgen/tools.py`) takes explicit dependencies (model, engine) instead of
  reaching for global state, so it stays testable without a running MCP server and reusable
  across transports.
- Integration tests are marked `@pytest.mark.integration` and must skip gracefully (not fail)
  when Docker/testcontainers is unavailable — see `tests/integration/test_postgres_discovery.py`.

## Current phase

v0.1 is in progress: second connector (MongoDB), config file support, and model diffing via
`source_fingerprint`. Working plan: `docs/roadmap.md` tracks what's shipped; check it before
assuming a feature exists.
