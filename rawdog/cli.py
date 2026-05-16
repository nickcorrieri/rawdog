# Author: Nicholas Corrieri

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rawdog.config import build_config, default_config_path, load_config, save_config
from rawdog.db import initialize, session
from rawdog.models import OrganizationMode, ProjectCreate
from rawdog.projects import create_project, list_projects
from rawdog.safety import SafetyError, ensure_distinct_roots, reject_dangerous_arguments

app = typer.Typer(
    name="rawdog",
    help="RAW photo managing tool that can fetch, copy, and audit your RAW libraries.",
    no_args_is_help=True,
)
console = Console()


def _load_or_exit() -> tuple[Path, object]:
    config_path = default_config_path()
    if not config_path.exists():
        raise typer.BadParameter("RAWDOG is not initialized. Run `rawdog init` first.")
    config = load_config(config_path)
    return config_path, config


@app.callback()
def main() -> None:
    try:
        reject_dangerous_arguments()
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def init(
    working_root: Path = typer.Option(..., prompt=True, help="Local working library root."),
    archive_root: Path = typer.Option(..., prompt=True, help="Permanent append-only archive root."),
    mode: OrganizationMode = typer.Option(
        ...,
        prompt="How do you organize your shoots? Choose date or project",
        help="Organization mode.",
    ),
    date_template: str = typer.Option("YYYY/YYYY-MM", help="Date-oriented folder template."),
    project_template: str = typer.Option("YYYY/PROJECT", help="Project-oriented folder template."),
) -> None:
    """Initialize RAWDOG config and local SQLite database."""
    ensure_distinct_roots(working_root, archive_root)
    config = build_config(
        organization_mode=mode,
        working_root=working_root,
        archive_root=archive_root,
        date_folder_template=date_template,
        project_folder_template=project_template,
    )
    config_path = save_config(config)
    initialize(config.database_path)
    console.print(f"RAWDOG config written: {config_path}")
    console.print(f"RAWDOG database initialized: {config.database_path}")


@app.command()
def fetch(
    source: Path = typer.Argument(..., help="SD card or import source path."),
    detect_sessions: bool = typer.Option(False, "--detect-sessions", help="Suggest time-gap splits."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before copying."),
) -> None:
    """Fetch RAW files from an SD card or import source into the working library."""
    _, config = _load_or_exit()
    console.print("Fetch is append-only and never assigns projects silently.")
    console.print(f"Source: {source}")
    console.print(f"Working root: {config.working_root}")
    console.print(f"Mode: {config.organization_mode.value}")
    console.print(f"Session detection: {'on' if detect_sessions else 'off'}")
    console.print(f"Dry run: {'yes' if dry_run else 'no'}")
    console.print("Project selection and copy planning will run here in the next increment.")


@app.command()
def breed(
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before archiving."),
) -> None:
    """Archive the working library to permanent storage without sync semantics."""
    _, config = _load_or_exit()
    console.print("Breed is append-only. It never deletes destination files.")
    console.print(f"Working root: {config.working_root}")
    console.print(f"Archive root: {config.archive_root}")
    console.print(f"Dry run: {'yes' if dry_run else 'no'}")


@app.command()
def sniff() -> None:
    """Inspect RAWDOG library state and prepare report data."""
    _, config = _load_or_exit()
    console.print(f"Sniff will inspect working root: {config.working_root}")
    console.print(f"Sniff will inspect archive root: {config.archive_root}")


@app.command()
def status() -> None:
    """Show configured paths, projects, and archive state summary."""
    _, config = _load_or_exit()
    table = Table(title="RAWDOG Status")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Organization mode", config.organization_mode.value)
    table.add_row("Working root", str(config.working_root))
    table.add_row("Archive root", str(config.archive_root))
    table.add_row("Database", str(config.database_path))
    with session(config.database_path) as connection:
        projects = list_projects(connection)
    table.add_row("Projects", str(len(projects)))
    console.print(table)


@app.command()
def report() -> None:
    """Generate RAWDOG reports from the local database."""
    _, config = _load_or_exit()
    console.print(f"Reports will be generated from: {config.database_path}")


@app.command()
def verify(
    source: Path | None = typer.Option(
        None,
        "--source",
        help="Optional source tree for an explicit source-to-destination check.",
    ),
    destination: Path | None = typer.Option(
        None,
        "--destination",
        help="Optional destination tree for an explicit source-to-destination check.",
    ),
) -> None:
    """Verify archive files, or explicitly check whether SOURCE is represented in DESTINATION."""
    _, config = _load_or_exit()
    if source or destination:
        if not source or not destination:
            raise typer.BadParameter("--source and --destination must be provided together.")
        console.print("Running explicit source-to-destination verification preview.")
        console.print("This is an optional check, not sync behavior.")
        console.print(f"Source: {source}")
        console.print(f"Destination: {destination}")
        return
    console.print(f"Verify will inspect RAWDOG archive root: {config.archive_root}")


projects_app = typer.Typer(help="Manage RAWDOG projects.")
app.add_typer(projects_app, name="projects")


@projects_app.command("create")
def project_create(
    name: str = typer.Argument(...),
    client: str | None = typer.Option(None, "--client"),
    tags: list[str] = typer.Option(None, "--tag"),
    location: str | None = typer.Option(None, "--location"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Create a project explicitly."""
    _, config = _load_or_exit()
    payload = ProjectCreate(
        name=name,
        client_name=client,
        tags=tags or [],
        location=location,
        notes=notes,
    )
    with session(config.database_path) as connection:
        project = create_project(connection, payload)
    console.print(f"Created project #{project.project_id}: {project.name}")


@projects_app.command("list")
def project_list(include_archived: bool = typer.Option(False, "--include-archived")) -> None:
    """List projects."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        projects = list_projects(connection, include_archived=include_archived)
    table = Table(title="RAWDOG Projects")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Client")
    table.add_column("Last Import")
    for project in projects:
        table.add_row(
            str(project.project_id),
            project.name,
            project.client_name or "",
            project.last_import_at.isoformat() if project.last_import_at else "",
        )
    console.print(table)


if __name__ == "__main__":
    app()
