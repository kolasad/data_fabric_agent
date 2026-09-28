# Changelog

## Unreleased (v0.1)

### Breaking: semantic model format bumped to `0.2`

`SemanticModel` is now multi-resource. What used to be top-level fields
(`resource_name`, `resource_type`, `source_fingerprint`, `entities`,
`relationships`) now live on a `ResourceModel`, and `SemanticModel` holds a
`resources: list[ResourceModel]` plus `version`/`generated_at`.

A `fabric.model.yaml`/`.json` written by an earlier version will fail to load
(`resources` is a required field the old format doesn't have) — there is no
automatic migration. Re-run `agent-fabric discover` to regenerate it.

For single-resource models (the common case — one `--dsn`, no `resources:` in
the config file) nothing else changes: entity names stay unprefixed, and
`model.entities`, `model.relationships`, `model.source_fingerprint`,
`model.get_entity()` and `model.relationships_for()` all still work exactly as
before — they're now convenience views over `model.resources[0]` rather than
stored fields. Only models spanning more than one resource prefix entity names
with the resource name, to avoid collisions.

### Added

- Config file support (`fabric.config.yaml`), resolved via `--config` /
  `AGENT_FABRIC_CONFIG` / `./fabric.config.yaml`, ranked below env vars/`.env`
  and above field defaults.
- Multi-resource discovery: a config file's top-level `resources:` list
  discovers several connectors into one `fabric.model.yaml` in a single
  `agent-fabric discover --config ...` run (`pipeline.discover_resources_to_model`).
- MongoDB discovery connector (`discovery/mongodb.py`): schema-on-read field
  inference via document sampling; reuses the existing naming-heuristic
  relationship inference unmodified. Live query tools (`sample_rows`/
  `run_select`) remain Postgres-only.

## MVP

Initial vertical slice: PostgreSQL discovery → semantic model → MCP stdio
server, with FK + naming-heuristic relationship inference, read-only tools,
YAML/JSON model IO with a structural fingerprint, tests, and CI.
