"""``agent-fabric`` command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable

from agent_data_fabric.config import Settings
from agent_data_fabric.core.models import ResourceType
from agent_data_fabric.pipeline import discover_to_model
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


def _sniff_resource_type(dsn: str) -> str:
    """Guess the resource type from the DSN scheme when ``--type`` isn't given."""

    if dsn.startswith(_MONGO_SCHEMES):
        return ResourceType.mongodb.value
    return ResourceType.postgres.value


def _build_settings(config: Path | None) -> Settings:
    try:
        return Settings(_config_file=config)
    except FileNotFoundError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


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
        "AGENT_FABRIC_CONFIG, then ./fabric.config.yaml if present.",
    ),
) -> None:
    """Discover a database and write a semantic model to disk."""

    settings = _build_settings(config)
    resolved_dsn = _resolve_dsn(dsn, settings)
    resolved_type = resource_type or _sniff_resource_type(resolved_dsn)

    with console.status("Discovering environment..."):
        try:
            model = discover_to_model(resolved_dsn, resource_type=resolved_type, settings=settings)
        except Exception as exc:  # noqa: BLE001 - surface connection/introspection errors
            err_console.print(f"[red]Discovery failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    path = save_model(model, out)
    console.print(
        Panel.fit(
            f"[bold green]Semantic model written[/bold green]\n"
            f"Path: [cyan]{path}[/cyan]\n"
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

    settings = _build_settings(config)
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
