# Architecture

Agent Data Fabric separates *what exists in the environment* (the **physical
layer**) from *what agents consume* (the **semantic layer**), and keeps the MCP
transport decoupled from tool logic. This makes each stage independently
testable and keeps the extension seams explicit for future connectors.

## Pipeline

```
DSN ──▶ Discovery ──▶ Metadata / Relationships ──▶ Semantic builder ──▶ fabric.model.yaml
                                                                              │
                                                                              ▼
                                                            Tool generation (MCP server, stdio)
```

1. **Discovery** (`discovery/postgres.py`): connects with SQLAlchemy, walks the
   inspector, and produces a physical `Resource` (schemas → tables → columns
   with PK/FK/comments). Credentials are stripped immediately via
   `config.redact_dsn`.
2. **Metadata** (`metadata/extractor.py`): normalizes raw introspection into the
   physical models (type stringification, FK expansion, best-effort comments).
3. **Relationships** (`metadata/relationships.py`): builds a de-duplicated edge
   list from foreign keys (`confidence = 1.0`) and naming heuristics
   (`*_id`/`*_fk` → `<table>.id`, `confidence ≈ 0.6`). FK edges suppress
   duplicate heuristic edges.
4. **Semantic builder** (`semantic/builder.py`): maps tables → entities and
   columns → fields, attaches relationships, and computes a
   structure-only `source_fingerprint` (sha256) for change detection.
5. **Model IO** (`semantic/model_io.py`): serializes to YAML or JSON by
   extension; round-trippable via pydantic validation.
6. **Tool generation** (`toolgen/`): `tools.py` holds transport-agnostic logic;
   `mcp_server.py` wires it into a `FastMCP` server; `serve/mcp_stdio.py` runs it.

## Layered data model

| Physical (`core/models.py`) | Semantic (`core/models.py`) |
| --- | --- |
| `Resource → Schema → Table → Column` | `SemanticModel → Entity → SemanticField` |
| Provider-specific, faithful | Normalized, agent-friendly |
| `Relationship` (shared across both layers) | |

## Safety model

Read-only by design, with defense-in-depth:

- **No credentials on disk** — `connection_ref` is a redacted DSN.
- **`run_select` guard** (`toolgen/guard.py`): parses SQL with `sqlglot`, rejects
  anything that is not a single `SELECT`/CTE/`UNION`, blocks row locks and any
  embedded write nodes, and enforces a `LIMIT ≤ max_sample_limit`.
- **Row caps + statement timeouts** on all data access (`sample_rows`, `run_select`).
- **Feature flag** — `run_select` is only registered with `--allow-query`.
- **Operational recommendation** — connect with a dedicated read-only DB role.

## Extension seams

- `core/registry.py` defines `DiscoveryPlugin` / `RelationshipInferencer`
  protocols and a `PluginRegistry`. New connectors register a discovery plugin
  keyed by resource type; the rest of the pipeline is connector-agnostic.
- Tool logic in `toolgen/tools.py` takes explicit dependencies (model + engine),
  so additional transports (HTTP/SSE) can reuse it without changes.
