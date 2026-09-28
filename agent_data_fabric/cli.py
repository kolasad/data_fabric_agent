"""``agent-fabric`` command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable

from agent_data_fabric.config import Settings, load_resource_specs, resolve_config_path
from agent_data_fabric.pipeline import (
    discover_resources_to_model,
    discover_to_model,
    sniff_resource_type,
)
from agent_data_fabric.semantic.model_io import load_model, save_model

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Discover a data environment and expose it to AI agents via MCP.",
)
console = Console()
err_console = Console(stderr=True)

DEFAULT_MODEL_PATH = "fabric.model.yaml"
_MONGO_SCHEMES = ("mongodb://", "mongodb+srv://")


def _resolve_dsn(dsn: str | None, settings: Settings) -> str:
    resolved = dsn or settings.dsn
    if not resolved:
        err_console.print(
            "[red]No DSN provided.[/red] Pass --dsn or set AGENT_FABRIC_DSN " "(see .env.example)."
        )
        raise typer.Exit(code=2)
    return resolved


def _resolve_config(config: Path | None) -> Path | None:
    try:
        return resolve_config_path(config)
    except FileNotFoundError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


def _build_settings(config_path: Path | None) -> Settings:
    return Settings(_config_file=config_path)


@app.command()
def discover(
    dsn: str | None = typer.Option(
        None,
        "--dsn",
        help="DSN, e.g. postgresql+psycopg://user:pass@host:5432/db or "
        "mongodb://user:pass@host:27017/db. Falls back to AGENT_FABRIC_DSN.",
    ),
    resource_type: str | None = typer.Option(
        None,
        "--type",
        help="Resource type ('postgres' or 'mongodb'). Auto-detected from the DSN "
        "scheme when omitted.",
    ),
    out: Path = typer.Option(
        Path(DEFAULT_MODEL_PATH),
        "--out",
        "-o",
        help="Where to write the semantic model (.yaml or .json).",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Path to a fabric.config.yaml settings file. Falls back to "
        "AGENT_FABRIC_CONFIG, then ./fabric.config.yaml if present. A config "
        "file with a top-level `resources:` list discovers all of them into "
        "one model, ignoring --dsn/--type.",
    ),
) -> None:
    """Discover a database (or several, via --config) and write a semantic model to disk."""

    config_path = _resolve_config(config)
    settings = _build_settings(config_path)
    resource_specs = load_resource_specs(config_path) if config_path else None

    resolved_dsn: str | None = None
    resolved_type: str | None = None
    if not resource_specs:
        resolved_dsn = _resolve_dsn(dsn, settings)
        resolved_type = resource_type or sniff_resource_type(resolved_dsn)

    with console.status("Discovering environment..."):
        try:
            if resource_specs:
                model = discover_resources_to_model(resource_specs, base_settings=settings)
            else:
                assert resolved_dsn is not None and resolved_type is not None
                model = discover_to_model(
                    resolved_dsn, resource_type=resolved_type, settings=settings
                )
        except Exception as exc:  # noqa: BLE001 - surface connection/introspection errors
            err_console.print(f"[red]Discovery failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    path = save_model(model, out)
    resources_line = (
        f"Resources: [bold]{len(model.resources)}[/bold]\n" if len(model.resources) > 1 else ""
    )
    console.print(
        Panel.fit(
            f"[bold green]Semantic model written[/bold green]\n"
            f"Path: [cyan]{path}[/cyan]\n"
            f"{resources_line}"
            f"Entities: [bold]{len(model.entities)}[/bold]  "
            f"Relationships: [bold]{len(model.relationships)}[/bold]\n"
            f"Fingerprint: [dim]{model.source_fingerprint[:12]}[/dim]",
            title="agent-fabric discover",
        )
    )


@app.command()
def inspect(
    model_path: Path = typer.Option(
        Path(DEFAULT_MODEL_PATH),
        "--model",
        "-m",
        help="Path to a semantic model produced by `discover`.",
    ),
) -> None:
    """Print a summary of entities and relationships from a semantic model."""

    if not model_path.exists():
        err_console.print(f"[red]Model not found:[/red] {model_path}")
        raise typer.Exit(code=2)

    model = load_model(model_path)

    if len(model.resources) > 1:
        resources_table = RichTable(title=f"Resources ({len(model.resources)})")
        resources_table.add_column("Name", style="cyan")
        resources_table.add_column("Type")
        resources_table.add_column("Entities", justify="right")
        resources_table.add_column("Fingerprint")
        for resource in model.resources:
            resources_table.add_row(
                resource.resource_name,
                resource.resource_type.value,
                str(len(resource.entities)),
                resource.source_fingerprint[:12],
            )
        console.print(resources_table)

    entities_table = RichTable(title=f"Entities ({len(model.entities)})")
    entities_table.add_column("Entity", style="cyan", no_wrap=True)
    entities_table.add_column("Source table")
    entities_table.add_column("Fields", justify="right")
    entities_table.add_column("Primary key")
    for entity in model.entities:
        entities_table.add_row(
            entity.name,
            entity.source_table,
            str(len(entity.fields)),
            ", ".join(entity.primary_key) or "-",
        )
    console.print(entities_table)

    rel_table = RichTable(title=f"Relationships ({len(model.relationships)})")
    rel_table.add_column("From", style="cyan")
    rel_table.add_column("To")
    rel_table.add_column("Kind")
    rel_table.add_column("Source")
    rel_table.add_column("Confidence", justify="right")
    for rel in model.relationships:
        rel_table.add_row(
            f"{rel.from_qualified}.{rel.from_column}",
            f"{rel.to_qualified}.{rel.to_column}",
            rel.kind.value,
            rel.source.value,
            f"{rel.confidence:.2f}",
        )
    console.print(rel_table)


@app.command()
def serve(
    model_path: Path = typer.Option(
        Path(DEFAULT_MODEL_PATH),
        "--model",
        "-m",
        help="Path to a semantic model produced by `discover`.",
    ),
    dsn: str | None = typer.Option(
        None,
        "--dsn",
        help="DSN for live data tools (sample_rows/run_select). "
        "Falls back to AGENT_FABRIC_DSN. Omit for metadata-only mode.",
    ),
    allow_query: bool = typer.Option(
        False,
        "--allow-query",
        help="Enable the guarded run_select tool (read-only SELECT only).",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Path to a fabric.config.yaml settings file. Falls back to "
        "AGENT_FABRIC_CONFIG, then ./fabric.config.yaml if present.",
    ),
) -> None:
    """Run the generated MCP server over stdio."""

    if not model_path.exists():
        err_console.print(f"[red]Model not found:[/red] {model_path}")
        raise typer.Exit(code=2)

    settings = _build_settings(_resolve_config(config))
    resolved_dsn = dsn or settings.dsn

    if resolved_dsn and resolved_dsn.startswith(_MONGO_SCHEMES):
        err_console.print(
            "[yellow]Live query tools (sample_rows/run_select) aren't implemented for "
            "MongoDB yet — serving in metadata-only mode (list_entities/describe_entity).[/yellow]"
        )
        resolved_dsn = None

    # Imported lazily so `discover`/`inspect` don't require the MCP runtime.
    from agent_data_fabric.serve.mcp_stdio import serve_stdio

    serve_stdio(
        model_path,
        dsn=resolved_dsn,
        allow_query=allow_query,
        settings=settings,
    )


if __name__ == "__main__":  # pragma: no cover
    app()
