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

1. **Discovery** (`discovery/postgres.py`, `discovery/mongodb.py`): connects to
   the source and produces a physical `Resource` (schemas → tables → columns).
   Postgres walks the SQLAlchemy inspector for PK/FK/comments; MongoDB has no
   declared schema, so it infers one by sampling documents per collection
   (`Settings.mongo_sample_size`) and unioning observed field names/types.
   Credentials are stripped immediately via `config.redact_dsn`.
2. **Metadata** (`metadata/extractor.py`): normalizes raw introspection into the
   physical models (type stringification, FK expansion, best-effort comments).
3. **Relationships** (`metadata/relationships.py`): builds a de-duplicated edge
   list from foreign keys (`confidence = 1.0`) and naming heuristics
   (`*_id`/`*_fk` → `<table>.id`, `confidence ≈ 0.6`). FK edges suppress
   duplicate heuristic edges.
4. **Semantic builder** (`semantic/builder.py`): maps tables → entities and
   columns → fields, attaches relationships, and computes a
   structure-only `source_fingerprint` (sha256) for change detection. One
   `ResourceModel` is built per discovered resource; entity names are prefixed
   with the resource name only when a model spans more than one resource, so
   the common single-resource case keeps unprefixed names.
5. **Model IO** (`semantic/model_io.py`): serializes to YAML or JSON by
   extension; round-trippable via pydantic validation.
6. **Tool generation** (`toolgen/`): `tools.py` holds transport-agnostic logic;
   `mcp_server.py` wires it into a `FastMCP` server; `serve/mcp_stdio.py` runs it.

## Layered data model

| Physical (`core/models.py`) | Semantic (`core/models.py`) |
| --- | --- |
| `Resource → Schema → Table → Column` | `SemanticModel → ResourceModel → Entity → SemanticField` |
| Provider-specific, faithful | Normalized, agent-friendly |
| `Relationship` (shared across both layers, scoped to one resource) | |

`SemanticModel` holds a list of `ResourceModel` (one per discovered resource:
`resource_name`, `resource_type`, `source_fingerprint`, `entities`,
`relationships`) plus `version`/`generated_at`. `entities`, `relationships`,
`source_fingerprint`, `get_entity()` and `relationships_for()` are convenience
views flattened across every resource, so single-resource callers (`toolgen/
tools.py`, the CLI) don't need to know this is a list underneath. Relationship
inference stays scoped to one resource at a time — a naming match across two
unrelated systems would be noise, not signal — so cross-resource relationships
are out of scope for now, not a silent gap.

> **Format note:** this is a breaking change from the `0.1` model schema
> (`resource_name`/`resource_type`/`source_fingerprint`/`entities`/
> `relationships` used to be top-level fields). A `fabric.model.yaml` written
> by an older version won't load; re-run `agent-fabric discover`. See
> `CHANGELOG.md`.

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
  keyed by resource type; the rest of the pipeline is connector-agnostic. Two
  plugins are registered today: `discovery/postgres.py` and
  `discovery/mongodb.py` — proof that the seam holds for a non-SQL,
  schema-on-read source without touching `metadata/relationships.py` (its FK +
  naming-heuristic inference is generic over `Table`/`Column`, not
  Postgres-specific) or the semantic builder.
- Tool logic in `toolgen/tools.py` takes explicit dependencies (model + engine),
  so additional transports (HTTP/SSE) can reuse it without changes. It's
  currently SQL-specific (`sqlalchemy.Engine` + `sqlglot` guard), so
  Mongo-backed models only expose the metadata tools (`list_entities`/
  `describe_entity`) until a Mongo-native `sample_rows`/`run_select` equivalent
  is built.
