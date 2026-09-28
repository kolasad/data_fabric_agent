# Roadmap

Milestones map to the Agent Data Fabric project brief.

## MVP (this slice) ✅
- PostgreSQL discovery → semantic model → MCP serve.
- FK + naming-heuristic relationship inference with confidence scores.
- Read-only tools: `list_entities`, `describe_entity`, `sample_rows`, guarded `run_select`.
- YAML/JSON model IO with structural fingerprint.
- Unit tests + testcontainers integration test + CI.

## v0.1
- Second connector (OpenAPI **or** MongoDB) behind the existing plugin registry. ✅
  MongoDB discovery via document sampling; naming-heuristic relationship inference
  reused unmodified. Live query tools (`sample_rows`/`run_select`) remain Postgres-only.
- Config file (in addition to env/flags) and multi-resource models.
- Model diffing using `source_fingerprint` (detect + report schema drift).

## v0.2
- Relationship inference improvements (data-profiling signals, join-cardinality checks).
- Security/auth layer and per-tool authorization.
- Deployment engine (containerized gateway) and observability hooks.
- Formalized plugin system with entry-point discovery.

## v0.5 → v1.0 (future)
- Multi-system discovery (Redis, Kafka, S3, Kubernetes, Terraform).
- Unified semantic graph across heterogeneous resources.
- HTTP/SSE MCP transport; hosted AI gateway.
- Documentation generation and lineage integration (OpenLineage/OpenMetadata).
