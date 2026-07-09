# Agent Data Fabric

> Turn an existing data environment into an AI-accessible platform with one command.

Agent Data Fabric discovers a data environment, understands its structure and
relationships, builds a **semantic model**, and auto-generates a safe,
**MCP-compatible** interface that Claude, Cursor, VS Code, or any MCP client can
consume — without hand-writing connectors or tool definitions.

This repository contains the **initial vertical slice**: a complete
`PostgreSQL → semantic model → MCP server` pipeline that proves the core concept
end to end. Additional connectors, a deployment engine, and a security layer are
on the [roadmap](docs/roadmap.md).

```
agent-fabric discover      # Postgres → fabric.model.yaml
        ↓
agent-fabric inspect       # human-readable summary
        ↓
agent-fabric serve         # MCP server (stdio) with read-only tools
        ↓
Claude / Cursor / VS Code
```

## Features (this slice)

- **PostgreSQL discovery** via SQLAlchemy: schemas, tables, columns, PKs, FKs, comments.
- **Relationship inference**: authoritative FK edges + naming heuristics (`customer_id → customers.id`) with confidence scores.
- **Semantic model**: normalized entities/fields/relationships serialized to `fabric.model.yaml` (or `.json`), with a `source_fingerprint` for change detection.
- **Auto-generated MCP tools** (read-only, safe by default):
  - `list_entities()` — entities + descriptions.
  - `describe_entity(name)` — columns, types, relationships.
  - `sample_rows(entity, limit)` — capped, parametrized sample.
  - `run_select(sql)` — **guarded** (SELECT-only, single statement, enforced `LIMIT`); off unless `--allow-query`.
- **Safety first**: credentials never written to disk; read-only role recommended; statement timeouts and row caps.

## Quickstart

Requires Python 3.12+, [Poetry](https://python-poetry.org/), and Docker (for the demo DB).

```bash
# 1. Install dependencies
poetry install

# 2. Start the demo PostgreSQL database (seeded with a small shop schema)
docker compose -f examples/docker-compose.yml up -d

# 3. Discover → semantic model
poetry run agent-fabric discover \
  --dsn "postgresql+psycopg://app:app@localhost:5432/shopdb" \
  --out fabric.model.yaml

# 4. Inspect the result
poetry run agent-fabric inspect --model fabric.model.yaml

# 5. Serve over MCP (stdio). Add --allow-query to enable guarded run_select.
poetry run agent-fabric serve \
  --model fabric.model.yaml \
  --dsn "postgresql+psycopg://app:app@localhost:5432/shopdb" \
  --allow-query
```

> Prefer a **read-only** database role for the DSN used above. See `.env.example`.
> You can also set `AGENT_FABRIC_DSN` instead of passing `--dsn`.

## Connecting an MCP client

`agent-fabric serve` speaks MCP over **stdio**. Point any MCP client at it.

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agent-data-fabric": {
      "command": "poetry",
      "args": [
        "run", "agent-fabric", "serve",
        "--model", "/absolute/path/to/fabric.model.yaml",
        "--dsn", "postgresql+psycopg://readonly:***@localhost:5432/shopdb",
        "--allow-query"
      ]
    }
  }
}
```

For **Cursor / VS Code**, register the same command in their MCP settings.

## CLI

| Command | Purpose |
| --- | --- |
| `agent-fabric discover --dsn <url> [--out fabric.model.yaml]` | Discover → semantic model on disk. |
| `agent-fabric inspect [--model fabric.model.yaml]` | Rich summary of entities/relationships. |
| `agent-fabric serve --model fabric.model.yaml [--dsn <url>] [--allow-query]` | Run the MCP stdio server. |

Config resolves from CLI flags → `AGENT_FABRIC_*` env vars → `.env` (see `.env.example`).

## Architecture

See [docs/architecture.md](docs/architecture.md). Module map:

```
agent_data_fabric/
  cli.py                 # typer app: discover, inspect, serve
  config.py              # settings + DSN redaction
  pipeline.py            # discover → relationships → semantic model
  core/models.py         # physical + semantic pydantic models
  core/registry.py       # plugin registry / protocols
  discovery/postgres.py  # SQLAlchemy inspector → Resource
  metadata/extractor.py  # normalize introspection
  metadata/relationships.py  # FK + heuristic inference
  semantic/builder.py    # tables→entities, fingerprint
  semantic/model_io.py   # YAML/JSON (de)serialization
  toolgen/guard.py       # SELECT-only SQL guard (sqlglot)
  toolgen/tools.py       # tool logic (transport-agnostic)
  toolgen/mcp_server.py  # FastMCP wiring
  serve/mcp_stdio.py     # stdio runner
```

## Development

```bash
poetry install
poetry run pytest              # unit tests (fast)
poetry run pytest -m integration   # requires Docker (testcontainers)
poetry run ruff check .
poetry run black --check .
poetry run mypy agent_data_fabric
pre-commit install
```

## License

MIT — see [LICENSE](LICENSE).
