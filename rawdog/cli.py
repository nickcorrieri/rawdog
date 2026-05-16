# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from rawdog.config import build_config, default_config_path, load_config, save_config
from rawdog.db import initialize, session
from rawdog.den import DenPlan, build_den_plan, score_items, summarize_by_year
from rawdog.drives import parse_user_path, standard_path_choices
from rawdog.execution import (
    add_execution_plan_rows,
    create_execution_plan,
    get_execution_plan,
    get_latest_execution_plan,
    list_execution_plan_rows,
    list_execution_plans,
    mark_execution_plan_finished,
    mark_execution_plan_started,
    update_execution_plan_row,
)
from rawdog.inventory import earliest_raw_capture_time, scan_raw_files
from rawdog.memory import (
    build_destination_memory,
    write_destination_memory,
)
from rawdog.models import (
    ConsolidationWorkflowCreate,
    DenLayoutMode,
    DenTransferAction,
    ExecutionPlan,
    ExecutionPlanCreate,
    ExecutionPlanRow,
    ExecutionPlanRowCreate,
    ExecutionPlanStatus,
    ImportProfileCreate,
    OrganizationMode,
    PlanQueueCreate,
    PlanQueueStepCreate,
    PlanStepKind,
    ProjectCreate,
    RawdogConfig,
)
from rawdog.planner import default_date_only_destination, default_project_destination
from rawdog.copier import append_only_copy, append_only_move
from rawdog.profiles import (
    create_or_update_profile,
    get_last_profile,
    get_profile_by_name,
    list_profiles,
    touch_profile,
)
from rawdog.projects import ProjectError, create_project, get_project_by_name, list_projects
from rawdog.queue import (
    add_queue_step,
    create_or_update_queue,
    get_queue_by_name,
    list_queue_steps,
    list_queues,
)
from rawdog.safety import (
    SafetyError,
    ensure_consolidation_roots,
    ensure_distinct_roots,
    ensure_existing_directory,
    ensure_import_roots,
    ensure_same_filesystem,
    reject_dangerous_arguments,
)
from rawdog.workflows import (
    create_or_update_workflow,
    get_workflow_by_name,
    list_workflows,
    mark_workflow_committed,
    mark_workflow_planned,
)

app = typer.Typer(
    name="rawdog",
    help="RAW photo managing tool that can fetch, copy, and audit your RAW libraries.",
    no_args_is_help=False,
)
console = Console(force_terminal=True, color_system="standard")


STYLE_TITLE = "bold green on black"
STYLE_ACTION = "bold yellow on black"
STYLE_SAFE = "bold green on black"
STYLE_WARN = "bold red on black"
STYLE_PATH = "bold cyan on black"


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


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    try:
        reject_dangerous_arguments()
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if ctx.invoked_subcommand is None:
        _show_home_menu()
        raise typer.Exit()


def _show_home_menu() -> None:
    banner = Text()
    banner.append("RAWDOG\n", style=STYLE_TITLE)
    banner.append(
        "RAW photo managing tool that can fetch, copy, and audit your RAW libraries.",
        style="green on black",
    )
    console.print(Panel(banner, border_style="green", style="on black"))

    table = Table(
        title="Choose A Workflow",
        title_style=STYLE_ACTION,
        border_style="green",
        style="on black",
    )
    table.add_column("Option", style=STYLE_ACTION, justify="right")
    table.add_column("Workflow", style=STYLE_SAFE)
    table.add_column("Command", style=STYLE_PATH)
    table.add_row("1", "First setup", "rawdog init")
    table.add_row("2", "Fetch from card/folder", "rawdog fetch")
    table.add_row("3", "Archive edited project", "rawdog breed")
    table.add_row("4", "Consolidate old drive/folder", "rawdog den")
    table.add_row("5", "Queue a longer safe job", "rawdog queue create")
    table.add_row("6", "Inspect or score a folder", "rawdog sniff / rawdog score")
    table.add_row("7", "Check saved memory and plans", "rawdog plans list")
    table.add_row("0", "Show full help", "rawdog --help")
    console.print(table)
    console.print(
        "[bold red on black]Preview-first:[/] fetch, breed, and den do not write archive files "
        "unless you use [bold yellow on black]--commit[/]."
    )
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            latest_plan = get_latest_execution_plan(connection)
        if latest_plan:
            console.print(
                "[bold yellow on black]Last plan:[/] "
                f"#{latest_plan.plan_id} {latest_plan.status.value} - {latest_plan.what}"
            )
    except typer.BadParameter:
        pass
    choice = Prompt.ask(
        "[bold yellow on black]CHOOSE AN OPTION[/]",
        choices=["0", "1", "2", "3", "4", "5", "6", "7"],
        default="0",
        console=console,
    )
    suggestions = {
        "1": ["rawdog init"],
        "2": [
            "rawdog fetch /Volumes/CARD --destination ~/Pictures/RAWDOG --project Wedding_Smith",
            "rawdog fetch --profile last",
        ],
        "3": [
            "rawdog breed --project Wedding_Smith --source ~/Pictures/RAWDOG/2026/20260516_Wedding_Smith --dest /Volumes/Archive",
        ],
        "4": [
            "rawdog sniff /Volumes/OldDrive",
            "rawdog score /Volumes/OldDrive",
            "rawdog den /Volumes/OldDrive --dest /Volumes/Archive --layout preserve-dates",
        ],
        "5": [
            "rawdog queue create old_drive_cleanup",
            "rawdog queue add-sniff old_drive_cleanup /Volumes/OldDrive",
            "rawdog queue add-score old_drive_cleanup /Volumes/OldDrive",
            "rawdog queue add-den old_drive_cleanup /Volumes/OldDrive --dest /Volumes/Archive",
            "rawdog queue show old_drive_cleanup",
            "rawdog queue run old_drive_cleanup --commit",
        ],
        "6": ["rawdog sniff /Volumes/OldDrive", "rawdog score /Volumes/OldDrive"],
        "7": [
            "rawdog projects list",
            "rawdog profiles list",
            "rawdog workflows list",
            "rawdog queue list",
            "rawdog plans list",
        ],
        "0": ["rawdog --help"],
    }
    console.print(Panel("\n".join(suggestions[choice]), title="Next Command", border_style="yellow"))


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
    console.print("No files copied. Re-run with --commit after reviewing the plan.")


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
def sniff(roots: list[Path] | None = typer.Argument(None, help="Folders or volumes to inspect.")) -> None:
    """Inspect folders or configured RAWDOG roots."""
    _, config = _load_or_exit()
    sniff_roots = roots or [root for root in [config.working_root, config.archive_root] if root]
    if not sniff_roots:
        raise typer.BadParameter("No roots provided and no default roots are configured.")
    table = Table(title="RAWDOG Sniff")
    table.add_column("Root")
    table.add_column("RAW files", justify="right")
    table.add_column("GB", justify="right")
    table.add_column("Earliest", justify="right")
    for root in sniff_roots:
        try:
            ensure_existing_directory(root, "root")
        except SafetyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        items = scan_raw_files(root)
        total_bytes = sum(item.size_bytes for item in items)
        earliest = earliest_raw_capture_time(root)
        table.add_row(
            str(root),
            str(len(items)),
            f"{total_bytes / 1_000_000_000:.2f}",
            earliest.isoformat() if earliest else "",
        )
    console.print(table)


@app.command()
def score(root: Path = typer.Argument(..., help="Folder or volume to score.")) -> None:
    """Score a RAW library source for consolidation readiness."""
    try:
        ensure_existing_directory(root, "root")
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    items = scan_raw_files(root)
    result = score_items(items)
    table = Table(title="RAWDOG Score")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Score", str(result.score))
    table.add_row("RAW files", str(result.file_count))
    table.add_row("GB", f"{result.total_bytes / 1_000_000_000:.2f}")
    table.add_row("Duplicate names", str(result.duplicate_names))
    table.add_row("Years", str(result.year_count))
    console.print(table)
    for note in result.notes:
        console.print(f"- {note}")


def _persist_den_execution_plan(
    config: RawdogConfig,
    plan: DenPlan,
    *,
    queue_id: int | None = None,
) -> ExecutionPlan:
    skipped = sum(1 for row in plan.rows if row.status.startswith("skip"))
    collisions = sum(1 for row in plan.rows if row.status == "collision")
    what = f"{plan.transfer_action.value} RAW files into a RAWDOG destination"
    subject = f"{plan.source_root} -> {plan.destination_root}"
    expected = (
        f"{plan.files_to_transfer} files should be at {plan.destination_folder}; "
        f"{skipped} already-present files skipped; {collisions} collisions held for review."
    )
    with session(config.database_path) as connection:
        execution_plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what=what,
                subject=subject,
                expected_result=expected,
                execution_summary="Not started.",
                post_audit_summary="Not audited.",
                source_root=plan.source_root,
                destination_root=plan.destination_root,
                queue_id=queue_id,
            ),
        )
        add_execution_plan_rows(
            connection,
            execution_plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=row.source_path,
                    destination_path=row.destination_path,
                    size_bytes=row.size_bytes,
                    transfer_action=plan.transfer_action,
                    status=row.status,
                )
                for row in plan.rows
            ],
        )
    return execution_plan


def _print_execution_plan_start(plan: ExecutionPlan) -> None:
    body = "\n".join(
        [
            f"[bold green on black]What we're doing:[/] {plan.what}",
            f"[bold cyan on black]What we're doing it to:[/] {plan.subject}",
            f"[bold yellow on black]What should be where when done:[/] {plan.expected_result}",
            f"[bold green on black]Execution:[/] {plan.execution_summary}",
            f"[bold yellow on black]Post audit:[/] {plan.post_audit_summary}",
        ]
    )
    console.print(Panel(body, title=f"RAWDOG Plan #{plan.plan_id}", border_style="green"))


def _audit_execution_row(row: ExecutionPlanRow, status: str) -> str:
    if status in {"copied", "moved", "skipped_existing_same_name_size"}:
        if not row.destination_path.exists():
            return "destination_missing"
        if row.destination_path.stat().st_size != row.size_bytes:
            return "size_mismatch"
        return "destination_verified"
    if status == "skipped_collision" or row.status == "collision":
        return "needs_collision_review"
    if status == "skipped_existing_partial":
        return "needs_partial_review"
    if row.status.startswith("skip"):
        return "not_applicable"
    return "not_audited"


def _execute_persisted_plan(config: RawdogConfig, plan_id: int) -> ExecutionPlan:
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
        mark_execution_plan_started(connection, plan_id)

    transferred = 0
    skipped = 0
    review = 0
    failed = 0
    for row in rows:
        if row.status not in {"plan_copy", "planned", "failed"}:
            audit_status = _audit_execution_row(row, row.status)
            if audit_status.startswith("needs") or audit_status.endswith("missing"):
                review += 1
            if row.status.startswith("skip"):
                skipped += 1
            with session(config.database_path) as connection:
                update_execution_plan_row(
                    connection,
                    row.row_id,
                    status=row.status,
                    audit_status=audit_status,
                )
            continue
        try:
            if plan.destination_root is None:
                raise SafetyError("execution plan is missing destination root")
            status = (
                append_only_move(row.source_path, row.destination_path, plan.destination_root)
                if row.transfer_action == DenTransferAction.MOVE
                else append_only_copy(row.source_path, row.destination_path, plan.destination_root)
            )
            audit_status = _audit_execution_row(row, status)
            if status in {"copied", "moved"}:
                transferred += 1
            elif status.startswith("skipped"):
                skipped += 1
            if audit_status.startswith("needs") or audit_status.endswith("missing"):
                review += 1
            with session(config.database_path) as connection:
                update_execution_plan_row(
                    connection,
                    row.row_id,
                    status=status,
                    audit_status=audit_status,
                )
        except Exception as exc:
            failed += 1
            with session(config.database_path) as connection:
                update_execution_plan_row(
                    connection,
                    row.row_id,
                    status="failed",
                    audit_status="not_audited",
                    error=str(exc),
                )

    final_status = ExecutionPlanStatus.DONE
    if failed:
        final_status = ExecutionPlanStatus.FAILED
    elif review:
        final_status = ExecutionPlanStatus.NEEDS_REVIEW
    execution_summary = f"Transferred {transferred}; skipped {skipped}; failed {failed}."
    post_audit_summary = (
        f"Destination audit complete. Review items: {review}."
        if not failed
        else f"Destination audit incomplete. Failed rows: {failed}; review items: {review}."
    )
    with session(config.database_path) as connection:
        mark_execution_plan_finished(
            connection,
            plan_id,
            final_status,
            execution_summary,
            post_audit_summary,
        )
        finished = get_execution_plan(connection, plan_id)
    if finished is None:
        raise typer.BadParameter(f"Unknown plan: {plan_id}")
    return finished


@app.command()
def den(
    source: Path | None = typer.Argument(None, help="Messy source folder or volume to consolidate."),
    destination: Path | None = typer.Option(None, "--dest", "-d", help="Destination root."),
    project_name: str | None = typer.Option(None, "--project", help="Optional project folder name."),
    workflow_name: str | None = typer.Option(None, "--workflow", "-w", help="Save or reuse workflow name."),
    layout: DenLayoutMode = typer.Option(DenLayoutMode.PRESERVE, "--layout", help="Destination layout."),
    action: DenTransferAction = typer.Option(DenTransferAction.COPY, "--action", help="copy or move."),
    template: str | None = typer.Option(None, "--template", help="Folder template override."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before execution."),
) -> None:
    """Consolidate a messy RAW source into a RAWDOG folder structure."""
    _, config = _load_or_exit()
    loaded_workflow = None
    with session(config.database_path) as connection:
        if workflow_name:
            loaded_workflow = get_workflow_by_name(connection, workflow_name)

    source_value = source or (loaded_workflow.source_root if loaded_workflow else None)
    destination_value = destination or (loaded_workflow.destination_root if loaded_workflow else None)
    if source_value is None or destination_value is None:
        raise typer.BadParameter("--workflow with saved paths, or source and --dest, are required.")
    source_root = parse_user_path(str(source_value))
    destination_root = parse_user_path(str(destination_value))
    try:
        ensure_existing_directory(source_root, "source")
        ensure_existing_directory(destination_root, "destination")
        ensure_consolidation_roots(source_root, destination_root)
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    effective_layout = loaded_workflow.layout_mode if loaded_workflow and not source else layout
    effective_action = loaded_workflow.transfer_action if loaded_workflow and not source else action
    if effective_action == DenTransferAction.MOVE:
        try:
            ensure_same_filesystem(source_root, destination_root)
        except SafetyError as exc:
            raise typer.BadParameter(str(exc)) from exc
    effective_template = template or (loaded_workflow.folder_template if loaded_workflow else None)
    effective_template = effective_template or (
        config.project_folder_template
        if effective_layout == DenLayoutMode.PROJECT or project_name
        else config.date_folder_template
    )
    plan = build_den_plan(
        source_root,
        destination_root,
        project_name=project_name,
        layout_mode=effective_layout,
        transfer_action=effective_action,
        folder_template=effective_template,
    )
    if workflow_name:
        with session(config.database_path) as connection:
            workflow = create_or_update_workflow(
                connection,
                ConsolidationWorkflowCreate(
                    name=workflow_name,
                    source_root=source_root,
                    destination_root=destination_root,
                    layout_mode=effective_layout,
                    transfer_action=effective_action,
                    folder_template=effective_template,
                ),
            )
            mark_workflow_planned(connection, workflow.workflow_id)
    execution_plan = _persist_den_execution_plan(config, plan)
    _print_execution_plan_start(execution_plan)
    summary = summarize_by_year(plan.rows)
    table = Table(title="RAWDOG Den Plan")
    table.add_column("Destination")
    table.add_column("Files", justify="right")
    table.add_column("GB", justify="right")
    table.add_column("Mode")
    table.add_row(
        str(plan.destination_folder),
        str(plan.files_to_transfer),
        f"{plan.bytes_to_transfer / 1_000_000_000:.2f}",
        f"{effective_layout.value} / {effective_action.value} / {'dry-run' if dry_run else 'commit'}",
    )
    console.print(table)
    if effective_layout == DenLayoutMode.PRESERVE:
        console.print(
            "Tip: use --layout preserve-dates to normalize date-like folders "
            "such as MMDDYYYY or YYYY.MM.DD to YYYYMMDD."
        )
    if summary:
        year_table = Table(title="Copy Estimate")
        year_table.add_column("Year")
        year_table.add_column("Files", justify="right")
        year_table.add_column("GB", justify="right")
        for row in summary:
            year_table.add_row(
                str(row["year"]),
                str(row["files_to_copy"]),
                str(row["estimated_gb"]),
            )
        console.print(year_table)
    skipped = sum(1 for row in plan.rows if row.status.startswith("skip"))
    collisions = sum(1 for row in plan.rows if row.status == "collision")
    console.print(f"Skipped existing: {skipped}")
    console.print(f"Collisions needing review: {collisions}")
    if dry_run:
        console.print(
            f"Plan #{execution_plan.plan_id} written to the database. "
            "Re-run with --commit to execute after reviewing."
        )
        return
    confirmed = Prompt.ask(
        "[bold red on black]Execute this den plan? Type yes[/]",
        default="no",
        console=console,
    )
    if confirmed.lower() != "yes":
        console.print("Plan not executed.")
        return
    finished_plan = _execute_persisted_plan(config, execution_plan.plan_id)
    if workflow_name:
        with session(config.database_path) as connection:
            workflow = get_workflow_by_name(connection, workflow_name)
            if workflow:
                mark_workflow_committed(connection, workflow.workflow_id)
    _print_execution_plan_start(finished_plan)


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
        latest_plans = list_execution_plans(connection, limit=3)
    table.add_row("Projects", str(len(projects)))
    table.add_row("Profiles", str(len(profiles)))
    console.print(table)
    if latest_plans:
        plan_table = Table(title="Recent Execution Plans")
        plan_table.add_column("ID")
        plan_table.add_column("Status")
        plan_table.add_column("What")
        plan_table.add_column("Updated")
        for plan in latest_plans:
            plan_table.add_row(
                str(plan.plan_id),
                plan.status.value,
                plan.what,
                plan.updated_at.isoformat(),
            )
        console.print(plan_table)


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

workflows_app = typer.Typer(help="Manage reusable RAWDOG consolidation workflows.")
app.add_typer(workflows_app, name="workflows")

queue_app = typer.Typer(help="Queue safe audit/copy/move plans.")
app.add_typer(queue_app, name="queue")

plans_app = typer.Typer(help="Inspect and resume persisted execution plans.")
app.add_typer(plans_app, name="plans")


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


@workflows_app.command("list")
def workflow_list() -> None:
    """List reusable consolidation workflows."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        workflows = list_workflows(connection)
    table = Table(title="RAWDOG Consolidation Workflows")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Layout")
    table.add_column("Action")
    table.add_column("Last Commit")
    for workflow in workflows:
        table.add_row(
            str(workflow.workflow_id),
            workflow.name,
            str(workflow.source_root),
            str(workflow.destination_root),
            workflow.layout_mode.value,
            workflow.transfer_action.value,
            workflow.last_committed_at.isoformat() if workflow.last_committed_at else "",
        )
    console.print(table)


@plans_app.command("list")
def plans_list(limit: int = typer.Option(10, "--limit", min=1, max=50)) -> None:
    """List recent persisted execution plans."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plans = list_execution_plans(connection, limit=limit)
    table = Table(title="RAWDOG Execution Plans")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Kind")
    table.add_column("What")
    table.add_column("Updated")
    for plan in plans:
        table.add_row(
            str(plan.plan_id),
            plan.status.value,
            plan.plan_kind,
            plan.what,
            plan.updated_at.isoformat(),
        )
    console.print(table)


@plans_app.command("show")
def plans_show(plan_id: int = typer.Argument(...)) -> None:
    """Show one persisted execution plan and its row summary."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    _print_execution_plan_start(plan)
    table = Table(title=f"Plan #{plan.plan_id} Rows")
    table.add_column("Status")
    table.add_column("Audit")
    table.add_column("Files", justify="right")
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.status, row.audit_status or "")
        counts[key] = counts.get(key, 0) + 1
    for (status, audit_status), count in sorted(counts.items()):
        table.add_row(status, audit_status, str(count))
    console.print(table)


@plans_app.command("resume")
def plans_resume(plan_id: int = typer.Argument(...)) -> None:
    """Resume a persisted copy/move execution plan."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
    _print_execution_plan_start(plan)
    if plan.status == ExecutionPlanStatus.DONE:
        console.print("Plan is already done.")
        return
    confirmed = Prompt.ask(
        "[bold red on black]Resume this execution plan? Type yes[/]",
        default="no",
        console=console,
    )
    if confirmed.lower() != "yes":
        console.print("Plan not resumed.")
        return
    finished = _execute_persisted_plan(config, plan_id)
    _print_execution_plan_start(finished)


@queue_app.command("create")
def queue_create(name: str = typer.Argument(...), notes: str | None = typer.Option(None, "--notes")) -> None:
    """Create or update a safe plan queue."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        queue = create_or_update_queue(connection, PlanQueueCreate(name=name, notes=notes))
    console.print(f"Queued plan #{queue.queue_id}: {queue.name}")


@queue_app.command("add-den")
def queue_add_den(
    name: str = typer.Argument(...),
    source: Path = typer.Argument(...),
    destination: Path = typer.Option(..., "--dest", "-d"),
    layout: DenLayoutMode = typer.Option(DenLayoutMode.PRESERVE, "--layout"),
    action: DenTransferAction = typer.Option(DenTransferAction.COPY, "--action"),
    project_name: str | None = typer.Option(None, "--project"),
    template: str | None = typer.Option(None, "--template"),
) -> None:
    """Add a safe den step to a queue."""
    _, config = _load_or_exit()
    source_root = parse_user_path(str(source))
    destination_root = parse_user_path(str(destination))
    try:
        ensure_existing_directory(source_root, "source")
        ensure_existing_directory(destination_root, "destination")
        ensure_consolidation_roots(source_root, destination_root)
        if action == DenTransferAction.MOVE:
            ensure_same_filesystem(source_root, destination_root)
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with session(config.database_path) as connection:
        queue = get_queue_by_name(connection, name) or create_or_update_queue(
            connection,
            PlanQueueCreate(name=name),
        )
        next_order = len(list_queue_steps(connection, queue.queue_id)) + 1
        step = add_queue_step(
            connection,
            PlanQueueStepCreate(
                queue_id=queue.queue_id,
                step_order=next_order,
                step_kind=PlanStepKind.DEN,
                source_root=source_root,
                destination_root=destination_root,
                layout_mode=layout,
                transfer_action=action,
                folder_template=template,
                project_name=project_name,
            ),
        )
    console.print(f"Added queue step #{step.step_order}: den {action.value}")


@queue_app.command("add-sniff")
def queue_add_sniff(name: str = typer.Argument(...), root: Path = typer.Argument(...)) -> None:
    """Add a read-only sniff step to a queue."""
    _add_read_only_queue_step(name, root, PlanStepKind.SNIFF)


@queue_app.command("add-score")
def queue_add_score(name: str = typer.Argument(...), root: Path = typer.Argument(...)) -> None:
    """Add a read-only score step to a queue."""
    _add_read_only_queue_step(name, root, PlanStepKind.SCORE)


def _add_read_only_queue_step(name: str, root: Path, step_kind: PlanStepKind) -> None:
    _, config = _load_or_exit()
    source_root = parse_user_path(str(root))
    try:
        ensure_existing_directory(source_root, "source")
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with session(config.database_path) as connection:
        queue = get_queue_by_name(connection, name) or create_or_update_queue(
            connection,
            PlanQueueCreate(name=name),
        )
        next_order = len(list_queue_steps(connection, queue.queue_id)) + 1
        step = add_queue_step(
            connection,
            PlanQueueStepCreate(
                queue_id=queue.queue_id,
                step_order=next_order,
                step_kind=step_kind,
                source_root=source_root,
            ),
        )
    console.print(f"Added queue step #{step.step_order}: {step_kind.value}")


@queue_app.command("list")
def queue_list() -> None:
    """List safe plan queues."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        queues = list_queues(connection)
    table = Table(title="RAWDOG Plan Queues")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Updated")
    for queue in queues:
        table.add_row(str(queue.queue_id), queue.name, queue.status, queue.updated_at.isoformat())
    console.print(table)


@queue_app.command("show")
def queue_show(name: str = typer.Argument(...)) -> None:
    """Show queued safe steps."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        queue = get_queue_by_name(connection, name)
        if not queue:
            raise typer.BadParameter(f"Unknown queue: {name}")
        steps = list_queue_steps(connection, queue.queue_id)
    table = Table(title=f"RAWDOG Queue: {queue.name}")
    table.add_column("#")
    table.add_column("Kind")
    table.add_column("Action")
    table.add_column("Source")
    table.add_column("Destination")
    for step in steps:
        table.add_row(
            str(step.step_order),
            step.step_kind.value,
            step.transfer_action.value if step.transfer_action else "",
            str(step.source_root or ""),
            str(step.destination_root or ""),
        )
    console.print(table)


@queue_app.command("run")
def queue_run(
    name: str = typer.Argument(...),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview the queue before execution."),
) -> None:
    """Preview or execute queued safe steps in order."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        queue = get_queue_by_name(connection, name)
        if not queue:
            raise typer.BadParameter(f"Unknown queue: {name}")
        steps = list_queue_steps(connection, queue.queue_id)
    if not steps:
        raise typer.BadParameter(f"Queue has no steps: {name}")

    total_files = 0
    total_bytes = 0
    runnable_steps = []
    for step in steps:
        if not step.source_root:
            raise typer.BadParameter(f"Queue step #{step.step_order} is missing a source.")
        try:
            ensure_existing_directory(step.source_root, "source")
            if step.step_kind == PlanStepKind.DEN:
                if not step.destination_root:
                    raise typer.BadParameter(
                        f"Queue step #{step.step_order} is missing a destination."
                    )
                ensure_existing_directory(step.destination_root, "destination")
                ensure_consolidation_roots(step.source_root, step.destination_root)
                if step.transfer_action == DenTransferAction.MOVE:
                    ensure_same_filesystem(step.source_root, step.destination_root)
        except SafetyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if step.step_kind == PlanStepKind.SNIFF:
            items = scan_raw_files(step.source_root)
            runnable_steps.append((step, items))
        elif step.step_kind == PlanStepKind.SCORE:
            result = score_items(scan_raw_files(step.source_root))
            runnable_steps.append((step, result))
        elif step.step_kind == PlanStepKind.DEN:
            layout_mode = step.layout_mode or DenLayoutMode.PRESERVE
            transfer_action = step.transfer_action or DenTransferAction.COPY
            folder_template = step.folder_template or (
                config.project_folder_template
                if layout_mode == DenLayoutMode.PROJECT or step.project_name
                else config.date_folder_template
            )
            plan = build_den_plan(
                step.source_root,
                step.destination_root,
                project_name=step.project_name,
                layout_mode=layout_mode,
                transfer_action=transfer_action,
                folder_template=folder_template,
            )
            runnable_steps.append((step, plan))
            total_files += plan.files_to_transfer
            total_bytes += plan.bytes_to_transfer
        else:
            raise typer.BadParameter(f"Queue step #{step.step_order} is not safe: {step.step_kind.value}")

    table = Table(title=f"RAWDOG Queue Run: {queue.name}")
    table.add_column("#")
    table.add_column("Kind")
    table.add_column("Action")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Files", justify="right")
    table.add_column("GB", justify="right")
    for step, result in runnable_steps:
        if step.step_kind == PlanStepKind.DEN:
            files = result.files_to_transfer
            gb = result.bytes_to_transfer / 1_000_000_000
            destination_text = str(result.destination_folder)
            action_text = result.transfer_action.value
        elif step.step_kind == PlanStepKind.SNIFF:
            files = len(result)
            gb = sum(item.size_bytes for item in result) / 1_000_000_000
            destination_text = ""
            action_text = "read-only"
        else:
            files = result.file_count
            gb = result.total_bytes / 1_000_000_000
            destination_text = ""
            action_text = f"read-only score {result.score}"
        table.add_row(
            str(step.step_order),
            step.step_kind.value,
            action_text,
            str(step.source_root),
            destination_text,
            str(files),
            f"{gb:.2f}",
        )
    console.print(table)
    console.print(
        f"Total queued transfer: {total_files} files / {total_bytes / 1_000_000_000:.2f} GB"
    )
    execution_plans = [
        _persist_den_execution_plan(config, result, queue_id=queue.queue_id)
        for step, result in runnable_steps
        if step.step_kind == PlanStepKind.DEN
    ]
    for execution_plan in execution_plans:
        _print_execution_plan_start(execution_plan)
    if dry_run:
        plan_ids = ", ".join(str(plan.plan_id) for plan in execution_plans) or "none"
        console.print(
            "Dry run only. Read-only steps were evaluated; transfer steps were not executed. "
            f"Persisted execution plans: {plan_ids}."
        )
        return

    confirmed = Prompt.ask(
        "[bold red on black]Execute this safe queue? Type yes[/]",
        default="no",
        console=console,
    )
    if confirmed.lower() != "yes":
        console.print("Queue not executed.")
        return
    for execution_plan in execution_plans:
        finished_plan = _execute_persisted_plan(config, execution_plan.plan_id)
        _print_execution_plan_start(finished_plan)


if __name__ == "__main__":
    app()
