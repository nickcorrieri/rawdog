# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rawdog.config import build_config, default_config_path, load_config, save_config
from rawdog.db import initialize, session
from rawdog.drives import parse_user_path, standard_path_choices
from rawdog.inventory import earliest_raw_capture_time
from rawdog.memory import (
    build_destination_memory,
    default_date_only_destination,
    write_destination_memory,
)
from rawdog.models import ImportProfileCreate, OrganizationMode, ProjectCreate, RawdogConfig
from rawdog.planner import default_project_destination
from rawdog.profiles import (
    create_or_update_profile,
    get_last_profile,
    get_profile_by_name,
    list_profiles,
    touch_profile,
)
from rawdog.projects import ProjectError, create_project, get_project_by_name, list_projects
from rawdog.safety import (
    SafetyError,
    ensure_distinct_roots,
    ensure_existing_directory,
    ensure_import_roots,
    reject_dangerous_arguments,
)

app = typer.Typer(
    name="rawdog",
    help="RAW photo managing tool that can fetch, copy, and audit your RAW libraries.",
    no_args_is_help=True,
)
console = Console()


def _load_or_exit() -> tuple[Path, RawdogConfig]:
    config_path = default_config_path()
    if not config_path.exists():
        raise typer.BadParameter("RAWDOG is not initialized. Run `rawdog init` first.")
    config = load_config(config_path)
    return config_path, config


def _choose_path(label: str) -> Path:
    choices = standard_path_choices()
    console.print(f"{label}:")
    for index, (name, path) in enumerate(choices, start=1):
        console.print(f"{index}. {name}: {path}")
    console.print("0. Other")
    selection = typer.prompt("Choose a path", default="1")
    if selection == "0":
        return parse_user_path(typer.prompt("Path"))
    try:
        return choices[int(selection) - 1][1]
    except (IndexError, ValueError) as exc:
        raise typer.BadParameter("Invalid path selection.") from exc


@app.callback()
def main() -> None:
    try:
        reject_dangerous_arguments()
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def init(
    working_root: Path | None = typer.Option(
        None,
        help="Optional default local working library root.",
    ),
    archive_root: Path | None = typer.Option(
        None,
        help="Optional default append-only archive root.",
    ),
    mode: OrganizationMode = typer.Option(
        ...,
        prompt="How do you organize your shoots? Choose date or project",
        help="Organization mode.",
    ),
    date_template: str = typer.Option("YYYY/YYYY-MM", help="Date-oriented folder template."),
    project_template: str = typer.Option(
        "YYYY/YYYYMMDD_PROJECT",
        help="Project-oriented folder template.",
    ),
) -> None:
    """Initialize RAWDOG config and local SQLite database."""
    if working_root and archive_root:
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
    source: Path | None = typer.Argument(None, help="SD card, folder, or import source path."),
    destination: Path | None = typer.Option(None, "--destination", "-d", help="Working/import destination."),
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Reuse an import profile by name, or use 'last'.",
    ),
    project_name: str | None = typer.Option(None, "--project", help="Project name for this import."),
    profile_name: str | None = typer.Option(None, "--save-profile", help="Save source/destination as profile."),
    detect_sessions: bool = typer.Option(False, "--detect-sessions", help="Suggest time-gap splits."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before copying."),
) -> None:
    """Fetch RAW files from an SD card or import source into the working library."""
    _, config = _load_or_exit()
    loaded_profile = None
    with session(config.database_path) as connection:
        if profile:
            loaded_profile = (
                get_last_profile(connection)
                if profile.lower() == "last"
                else get_profile_by_name(connection, profile)
            )
            if not loaded_profile:
                raise typer.BadParameter(f"Unknown profile: {profile}")

    source_root = source or (loaded_profile.source_root if loaded_profile else None)
    destination_root = destination or (loaded_profile.destination_root if loaded_profile else None)

    if source_root is None:
        source_root = _choose_path("Import source")
    if destination_root is None:
        destination_root = config.working_root or _choose_path("Import destination")

    source_root = parse_user_path(str(source_root))
    destination_root = parse_user_path(str(destination_root))
    try:
        ensure_existing_directory(source_root, "source")
        ensure_import_roots(source_root, destination_root)
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    project = None
    if project_name:
        with session(config.database_path) as connection:
            project = get_project_by_name(connection, project_name)
            if project is None and not dry_run:
                try:
                    project = create_project(connection, ProjectCreate(name=project_name))
                except ProjectError as exc:
                    raise typer.BadParameter(str(exc)) from exc
            if not dry_run:
                remembered_name = profile_name or project_name
                remembered_profile = create_or_update_profile(
                    connection,
                    ImportProfileCreate(
                        name=remembered_name,
                        source_root=source_root,
                        destination_root=destination_root,
                        organization_mode=OrganizationMode.PROJECT,
                        folder_template=(
                            loaded_profile.folder_template if loaded_profile else config.project_folder_template
                        ),
                        project_id=project.project_id if project else None,
                    ),
                )
                touch_profile(connection, remembered_profile.profile_id)
            elif project is None:
                console.print(f"Project would be created on commit: {project_name}")
    elif profile_name and not dry_run:
        with session(config.database_path) as connection:
            create_or_update_profile(
                connection,
                ImportProfileCreate(
                    name=profile_name,
                    source_root=source_root,
                    destination_root=destination_root,
                    organization_mode=config.organization_mode,
                    folder_template=(
                        config.project_folder_template
                        if config.organization_mode == OrganizationMode.PROJECT
                        else config.date_folder_template
                    ),
                ),
            )
    elif loaded_profile and not dry_run:
        with session(config.database_path) as connection:
            touch_profile(connection, loaded_profile.profile_id)
    elif profile_name:
        console.print(f"Profile would be saved on commit: {profile_name}")

    console.print("Fetch is append-only and never assigns projects silently.")
    console.print(f"Source: {source_root}")
    console.print(f"Destination: {destination_root}")
    console.print(f"Mode: {(loaded_profile.organization_mode if loaded_profile else config.organization_mode).value}")
    effective_mode = loaded_profile.organization_mode if loaded_profile else config.organization_mode
    effective_template = (
        loaded_profile.folder_template
        if loaded_profile
        else (
            config.project_folder_template
            if effective_mode == OrganizationMode.PROJECT
            else config.date_folder_template
        )
    )
    earliest_capture_at = earliest_raw_capture_time(source_root)
    destination_folder = None
    if project_name:
        preview_project_name = project.name if project else project_name
        destination_folder = default_project_destination(
            destination_root,
            preview_project_name,
            earliest_capture_at
            or (project.created_at if project else datetime.now(timezone.utc)),
            (project.preferred_folder_template if project else None) or effective_template,
        )
        console.print(f"Project: {preview_project_name}")
        console.print(f"Default project folder: {destination_folder}")
    elif earliest_capture_at:
        destination_folder = default_date_only_destination(
            destination_root,
            earliest_capture_at,
            effective_template,
        )
        console.print(f"Default date-only folder: {destination_folder}")
    if destination_folder:
        memory = build_destination_memory(
            organization_mode=effective_mode,
            project_name=(project.name if project else project_name),
            source_root=source_root,
            destination_root=destination_root,
            destination_folder=destination_folder,
            folder_template=effective_template,
            earliest_capture_at=earliest_capture_at,
            profile_name=profile_name or profile,
        )
        memory_path = write_destination_memory(memory, dry_run=True)
        console.print(f"Destination memory planned: {memory_path}")
    console.print(f"Session detection: {'on' if detect_sessions else 'off'}")
    console.print(f"Dry run: {'yes' if dry_run else 'no'}")
    console.print("Project selection and copy planning will run here in the next increment.")


@app.command()
def breed(
    project_name: str | None = typer.Option(None, "--project", help="Project to archive."),
    source: Path | None = typer.Option(None, "--source", "-s", help="Working project source."),
    destinations: list[Path] | None = typer.Option(None, "--dest", "-d", help="Archive destination."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Saved archive/import profile."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before archiving."),
) -> None:
    """Archive the working library to permanent storage without sync semantics."""
    _, config = _load_or_exit()
    console.print("Breed is append-only. It never deletes destination files.")
    console.print(f"Project: {project_name or 'not specified'}")
    console.print(f"Source: {source or config.working_root or 'profile/import specific'}")
    if destinations:
        for destination in destinations:
            console.print(f"Archive destination: {destination}")
    else:
        console.print(f"Archive destination: {config.archive_root or 'profile/import specific'}")
    console.print(f"Profile: {profile or 'not specified'}")
    console.print(f"Dry run: {'yes' if dry_run else 'no'}")


@app.command()
def sniff() -> None:
    """Inspect RAWDOG library state and prepare report data."""
    _, config = _load_or_exit()
    console.print(f"Sniff will inspect working root: {config.working_root or 'profile/import specific'}")
    console.print(f"Sniff will inspect archive root: {config.archive_root or 'profile/import specific'}")


@app.command()
def status() -> None:
    """Show configured paths, projects, and archive state summary."""
    _, config = _load_or_exit()
    table = Table(title="RAWDOG Status")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Organization mode", config.organization_mode.value)
    table.add_row("Working root", str(config.working_root or "profile/import specific"))
    table.add_row("Archive root", str(config.archive_root or "profile/import specific"))
    table.add_row("Database", str(config.database_path))
    with session(config.database_path) as connection:
        projects = list_projects(connection)
        profiles = list_profiles(connection)
    table.add_row("Projects", str(len(projects)))
    table.add_row("Profiles", str(len(profiles)))
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

profiles_app = typer.Typer(help="Manage reusable RAWDOG import profiles.")
app.add_typer(profiles_app, name="profiles")


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
    try:
        with session(config.database_path) as connection:
            project = create_project(connection, payload)
    except ProjectError as exc:
        raise typer.BadParameter(str(exc)) from exc
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


@profiles_app.command("create")
def profile_create(
    name: str = typer.Argument(...),
    source: Path | None = typer.Option(None, "--source", "-s"),
    destination: Path | None = typer.Option(None, "--destination", "-d"),
    mode: OrganizationMode = typer.Option(OrganizationMode.PROJECT, "--mode"),
    template: str = typer.Option("YYYY/YYYYMMDD_PROJECT", "--template"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Create or update a reusable import profile."""
    _, config = _load_or_exit()
    source_root = source or _choose_path("Profile source")
    destination_root = destination or _choose_path("Profile destination")
    with session(config.database_path) as connection:
        profile = create_or_update_profile(
            connection,
            ImportProfileCreate(
                name=name,
                source_root=parse_user_path(str(source_root)),
                destination_root=parse_user_path(str(destination_root)),
                organization_mode=mode,
                folder_template=template,
                notes=notes,
            ),
        )
    console.print(f"Saved profile #{profile.profile_id}: {profile.name}")


@profiles_app.command("list")
def profile_list() -> None:
    """List reusable import profiles."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        profiles = list_profiles(connection)
    table = Table(title="RAWDOG Import Profiles")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Template")
    for profile in profiles:
        table.add_row(
            str(profile.profile_id),
            profile.name,
            str(profile.source_root),
            str(profile.destination_root),
            profile.folder_template,
        )
    console.print(table)


if __name__ == "__main__":
    app()
