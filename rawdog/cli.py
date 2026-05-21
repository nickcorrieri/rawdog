# Author: Nicholas Corrieri

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from rawdog.config import (
    build_config,
    default_config_path,
    default_database_path,
    load_config,
    save_config,
)
from rawdog.copier import append_only_copy, append_only_move
from rawdog.db import initialize, session
from rawdog.den import (
    DenPlan,
    build_den_plan,
    capture_date_counts,
    score_items,
    summarize_by_year,
)
from rawdog.drives import parse_user_path, standard_path_choices
from rawdog.execution import (
    add_execution_plan_rows,
    create_execution_plan,
    delete_execution_plan,
    get_execution_plan,
    get_latest_execution_plan,
    list_execution_plan_rows,
    list_execution_plans,
    list_execution_plans_for_prune,
    mark_execution_plan_finished,
    mark_execution_plan_started,
    update_execution_plan_row,
)
from rawdog.inventory import earliest_raw_capture_time, scan_raw_files
from rawdog.layout import LayoutAnalysis, analyze_source_layout
from rawdog.memory import (
    build_destination_memory,
    write_destination_memory,
)
from rawdog.models import (
    CollisionPolicy,
    ConsolidationWorkflowCreate,
    DateGroupMode,
    DenLayoutMode,
    DenTransferAction,
    ExecutionPlan,
    ExecutionPlanCreate,
    ExecutionPlanRow,
    ExecutionPlanRowCreate,
    ExecutionPlanStatus,
    ImportProfileCreate,
    NamingConvention,
    OrganizationMode,
    PlanQueueCreate,
    PlanQueueStepCreate,
    PlanStepKind,
    ProjectCreate,
    RawdogConfig,
    Store,
    StoreCreate,
    StoreKind,
)
from rawdog.planner import default_date_only_destination, default_project_destination
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
from rawdog.reports import write_operation_manifest
from rawdog.runlock import (
    ActiveRunError,
    active_run_is_alive,
    active_run_path,
    begin_active_run,
    clear_active_run,
    finish_active_run,
    read_active_run,
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
from rawdog.stores import (
    create_or_update_store,
    find_store_for_path,
    get_store_by_name,
    list_store_files_by_original_source,
    list_stores,
    mark_store_used,
    record_store_file,
    remove_store_registration,
)
from rawdog.verifier import verify_same_bytes
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

STYLE_TEXT = "bright_white on black"
STYLE_TITLE = "bold bright_green on black"
STYLE_ACTION = "bold black on bright_yellow"
STYLE_SAFE = "bold bright_green on black"
STYLE_WARN = "bold bright_white on dark_red"
STYLE_PATH = "bold bright_cyan on black"
STYLE_MUTED = "bright_white on grey15"
STYLE_ROW = "bright_white on black"
STYLE_ROW_ALT = "bright_white on grey11"
STYLE_ROW_HEADER = "bold bright_white on grey15"
STYLE_ROW_SELECTED = "bold black on bright_yellow"
STYLE_ROWS = [STYLE_ROW, STYLE_ROW_ALT]
STYLE_PANEL = STYLE_TEXT
console = Console(force_terminal=True, color_system="256", style=STYLE_TEXT)

RAWDOG_ASCII = r"""
  .----------------------------------------------------------------.
  |  RRRR    AAA   W   W  DDDD    OOO    GGGG                     |
  |  R   R  A   A  W   W  D   D  O   O  G                         |
  |  RRRR   AAAAA  W W W  D   D  O   O  G  GG                     |
  |  R  R   A   A  WW WW  D   D  O   O  G   G                     |
  |  R   R  A   A  W   W  DDDD    OOO    GGGG                     |
  |----------------------------------------------------------------|
  |    _________                                                   |
  |   /  _____  \__        FETCH . DEN . BREED . SNIFF             |
  |  |  [_____]    _)      APPEND-ONLY PHOTO OPS                   |
  |   \___________/        NO DELETE . NO OVERWRITE . FULL AUDIT   |
  |        / \__                                                   |
  |       (    @\___       ARCHIVE DOG ONLINE                      |
  |        /         O                                             |
  |       /   (_____/                                              |
  |      /_____/   U                                               |
  '----------------------------------------------------------------'
"""


def _load_or_exit() -> tuple[Path, RawdogConfig]:
    config_path = default_config_path()
    if not config_path.exists():
        raise typer.BadParameter(_init_guidance_text())
    config = load_config(config_path)
    initialize(config.database_path)
    return config_path, config


def _init_guidance_text() -> str:
    config_path = default_config_path()
    database_path = default_database_path()
    return "\n".join(
        [
            "RAWDOG is not initialized yet.",
            "",
            "Start here:",
            "  rawdog init --mode project --working-root ~/Pictures/RAWDOG --archive-root /Volumes/WD_BLACK/RAWDOG_Archive",
            "",
            "You can run that command from any folder. The important choices are:",
            "  working-root: local/project workspace, for example ~/Pictures/RAWDOG",
            "  archive-root: external/archive destination, for example /Volumes/WD_BLACK/RAWDOG_Archive",
            "",
            "Or just run `rawdog`, press 1, and RAWDOG will walk you through setup.",
            f"Config will be saved at: {config_path}",
            f"Database will be saved at: {database_path}",
        ]
    )


def _is_initialized() -> bool:
    return default_config_path().exists()


def _print_init_guidance() -> None:
    console.print(
        Panel(
            _init_guidance_text(),
            title="First Run Setup",
            border_style="yellow",
        )
    )


def _prompt(text: str) -> str:
    return f"[bold black on bright_yellow]{text}[/]"


def _print_option(key: str, text: str) -> None:
    _print_full_row([(key, STYLE_ROW_SELECTED), (" ", STYLE_ROW), (text, STYLE_ROW)], style=STYLE_ROW)


def _terminal_width() -> int:
    return max(console.width, shutil.get_terminal_size((console.width, 24)).columns)


def _print_full_row(parts: list[tuple[str, str]], *, style: str = STYLE_ROW) -> None:
    row = Text(style=style)
    for value, part_style in parts:
        row.append(value, style=part_style)
    width = _terminal_width()
    lines = row.wrap(console, width, overflow="fold")
    for line in lines or [row]:
        if line.cell_len < width:
            line.append(" " * (width - line.cell_len), style=style)
        console.print(line, overflow="crop", no_wrap=True)


def _print_section_row(text: str, *, style: str = STYLE_ROW_HEADER) -> None:
    _print_full_row([(text, style)], style=style)


def _print_path_option(index: str, name: str, path: Path) -> None:
    _print_full_row(
        [
            (f"{index}.", STYLE_ROW_SELECTED),
            (" ", STYLE_ROW),
            (f"{name}: ", "bold bright_white on black"),
            (str(path), STYLE_PATH),
        ],
        style=STYLE_ROW,
    )


def _print_notice(text: str, *, style: str = STYLE_MUTED) -> None:
    _print_full_row([(text, style)], style=style)


def _print_error(text: str) -> None:
    _print_full_row([(text, STYLE_WARN)], style=STYLE_WARN)


def _print_folder_option(index: str, name: str, size_bytes: int | None = None) -> None:
    size = f"  {_format_bytes(size_bytes)}" if size_bytes is not None else ""
    _print_full_row(
        [
            (f"{index}.", STYLE_ROW_SELECTED),
            (" ", STYLE_ROW),
            (name, "bold bright_white on black"),
            (size, STYLE_MUTED),
        ],
        style=STYLE_ROW,
    )


def _styled_table(*args, **kwargs) -> Table:
    kwargs.setdefault("style", STYLE_PANEL)
    kwargs.setdefault("row_styles", STYLE_ROWS)
    kwargs.setdefault("border_style", "bright_green")
    kwargs.setdefault("header_style", STYLE_ROW_HEADER)
    kwargs.setdefault("expand", True)
    kwargs.setdefault("width", _terminal_width())
    return Table(*args, **kwargs)


def _choose_path(label: str, *, browse_number_selection: bool = False) -> Path:
    choices = _standard_path_choices(limit=9)
    while True:
        _print_section_row(f"{label} (Ctrl-C to exit)")
        for index, (name, path) in enumerate(choices, start=1):
            _print_path_option(str(index), name, path)
        _print_option("0.", "Other / type a path directly")
        _print_notice("Tip: enter b7 to browse option 7, or type a full path directly.")
        prompt = "Choose a folder to browse, or type a path" if browse_number_selection else "Choose a path or type one"
        selection = Prompt.ask(_prompt(prompt), default="1", console=console).strip()
        if selection == "0":
            return parse_user_path(Prompt.ask(_prompt("Path"), console=console))
        if selection.lower().startswith("b") and len(selection) > 1:
            try:
                browse_index = int(selection[1:])
            except ValueError:
                console.print("[bold red]Invalid browse choice.[/] Use b plus a number, like b7.")
                continue
            if 1 <= browse_index <= len(choices):
                return _browse_folder(choices[browse_index - 1][1])
            console.print("[bold red]Invalid browse choice.[/] Try again.")
            continue
        if selection.startswith(("/", "~", ".")):
            return parse_user_path(selection)
        try:
            index = int(selection)
        except ValueError:
            console.print("[bold red]Invalid choice.[/] Enter a number or a path.")
            continue
        if 1 <= index <= len(choices):
            if browse_number_selection:
                return _browse_folder(choices[index - 1][1])
            return choices[index - 1][1]
        console.print("[bold red]Invalid choice.[/] Try again.")


def _choose_source_path(label: str) -> Path:
    yards = _known_stores(StoreKind.YARD)
    page = 0
    while True:
        _print_section_row(f"{label} (Ctrl-C to exit)")
        if yards:
            _print_notice("Established RAWDOG yards", style=STYLE_SAFE)
            page_stores = _store_page(yards, page)
            for index, store in enumerate(page_stores, start=1):
                _print_path_option(str(index), store.name, store.root_path)
            if _has_next_store_page(yards, page):
                _print_option("6.", "Next yards")
        else:
            _print_notice("No RAWDOG yards registered yet.", style=STYLE_ROW_SELECTED)
        _print_option("9.", "Explore common folders / volumes")
        _print_option("0.", "Enter manual path")
        selection = Prompt.ask(_prompt("Choose existing source folder"), default="9", console=console).strip()
        if selection == "6" and yards and _has_next_store_page(yards, page):
            page = _next_store_page(yards, page)
            continue
        if selection == "9":
            return _choose_explored_source_path(label)
        if selection == "0":
            path = _manual_existing_directory("Source path")
            if path:
                return path
            continue
        try:
            index = int(selection)
        except ValueError:
            console.print("[bold red]Invalid source choice.[/] Try again.")
            continue
        page_stores = _store_page(yards, page)
        if 1 <= index <= len(page_stores):
            store = page_stores[index - 1]
            path = store.root_path
            if path.exists() and path.is_dir():
                _mark_store_used(store)
                return path
            console.print(f"[bold red]Source folder is not available:[/] {path}")
            continue
        console.print("[bold red]Invalid source choice.[/] Try again.")


def _choose_explored_source_path(label: str) -> Path:
    start = _choose_standard_root(f"{label} start")
    return _browse_folder(start, confirm_label="Use this source folder", manual_mode="existing", max_children=6)


def _choose_den_destination_path(label: str) -> Path:
    _, config = _load_or_exit()
    dens = _known_stores(StoreKind.DEN)
    while True:
        _print_section_row(f"{label} (Ctrl-C to exit)")
        primary_den = next((store for store in dens if store.name.lower() == "primary"), None)
        default_den = config.archive_root or (primary_den.root_path if primary_den else None)
        if default_den:
            default_label = "Default den from init" if config.archive_root else "Primary registered den"
            _print_path_option("1", default_label, default_den)
        else:
            _print_full_row(
                [
                    ("1.", STYLE_ROW_SELECTED),
                    (" ", STYLE_ROW),
                    ("Default / primary den: ", "bold bright_white on black"),
                    ("not configured", STYLE_MUTED),
                ],
                style=STYLE_ROW,
            )
        _print_option("2.", "Pick a registered den")
        _print_option("3.", "Pick a volume / drive / path")
        _print_option("0.", "Enter manual path")
        selection = Prompt.ask(
            _prompt("Choose den destination"),
            default="1" if default_den else "2",
            console=console,
        ).strip()
        if selection == "1":
            if not default_den:
                console.print("[bold yellow]No default den configured.[/]")
                continue
            path = _confirm_destination_path(default_den)
            if path:
                _register_or_mark_store_path(path, StoreKind.DEN, "primary")
                return path
            continue
        if selection == "2":
            path = _pick_registered_store(dens, "den")
            if path:
                return path
            continue
        if selection == "3":
            start = _choose_standard_root("Destination start")
            return _browse_den_destination(start, dens)
        if selection == "0":
            path = _manual_destination_path("Destination path")
            if path:
                _register_or_mark_store_path(path, StoreKind.DEN, path.name or "den")
                return path
            continue
        console.print("[bold red]Invalid den destination choice.[/] Try again.")


def _choose_standard_root(label: str) -> Path:
    choices = _standard_path_choices(limit=9)
    while True:
        _print_section_row(f"{label} (Ctrl-C to exit)")
        for index, (name, path) in enumerate(choices, start=1):
            _print_path_option(str(index), name, path)
        _print_option("0.", "Enter manual path")
        selection = Prompt.ask(_prompt("Choose starting folder"), default="1", console=console).strip()
        if selection == "0":
            path = _manual_existing_directory("Starting path")
            if path:
                return path
            continue
        if selection.lower().startswith("b") and len(selection) > 1:
            try:
                browse_index = int(selection[1:])
            except ValueError:
                _print_error("Invalid browse choice. Use b plus a number, like b7.")
                continue
            if 1 <= browse_index <= len(choices):
                path = choices[browse_index - 1][1]
                if path.exists() and path.is_dir():
                    return path
                _print_error(f"Folder is not available: {path}")
                continue
            _print_error("Invalid browse choice. Try again.")
            continue
        try:
            index = int(selection)
        except ValueError:
            _print_error("Invalid path choice. Try again.")
            continue
        if 1 <= index <= len(choices):
            path = choices[index - 1][1]
            if path.exists() and path.is_dir():
                return path
            _print_error(f"Folder is not available: {path}")
            continue
        _print_error("Invalid path choice. Try again.")


def _browse_folder(
    start: Path,
    *,
    confirm_label: str = "Use this folder",
    manual_mode: str = "any",
    max_children: int = 6,
) -> Path:
    current = start.expanduser().resolve()
    folder_page = 0
    while True:
        _print_full_row([("Browsing: ", STYLE_ROW_HEADER), (str(current), STYLE_PATH)], style=STYLE_ROW_HEADER)
        all_folders = _sorted_child_folders(current)
        page_count = max(1, (len(all_folders) + max_children - 1) // max_children)
        if folder_page >= page_count:
            folder_page = 0
        folders = all_folders[folder_page * max_children : folder_page * max_children + max_children]
        if len(all_folders) > max_children:
            _print_notice(f"Folders page {folder_page + 1} of {page_count}; sorted by sampled size.")
        for index, (path, size_bytes) in enumerate(folders, start=1):
            _print_folder_option(str(index), path.name, size_bytes)
        if len(all_folders) > max_children:
            _print_option("7", "More folders")
        _print_option("8", "Parent folder")
        _print_option("9", confirm_label)
        _print_option("0", "Manual path")
        selection = Prompt.ask(_prompt("Choose folder (Ctrl-C to exit)"), default="9", console=console).strip()
        if selection in {".", "9"}:
            return current
        if selection == "7" and len(all_folders) > max_children:
            folder_page = (folder_page + 1) % page_count
            continue
        if selection in {"..", "8"}:
            current = current.parent
            folder_page = 0
            continue
        if selection == "0":
            if manual_mode == "existing":
                path = _manual_existing_directory("Manual path")
                if path:
                    current = path
                    folder_page = 0
                continue
            if manual_mode == "destination":
                path = _manual_destination_path("Manual destination")
                if path:
                    return path
                continue
            current = parse_user_path(Prompt.ask(_prompt("Path"), console=console)).expanduser().resolve()
            folder_page = 0
            continue
        if selection.startswith(("/", "~", ".")):
            path = parse_user_path(selection).expanduser().resolve()
            if manual_mode == "existing" and not _is_existing_directory(path):
                continue
            current = path
            folder_page = 0
            continue
        try:
            index = int(selection)
        except ValueError:
            _print_error("Invalid folder choice. Try again.")
            continue
        if 1 <= index <= len(folders):
            current = folders[index - 1][0]
            folder_page = 0
            continue
        _print_error("Invalid folder choice. Try again.")


def _browse_den_destination(start: Path, dens: list) -> Path:
    current = start.expanduser().resolve()
    folder_page = 0
    while True:
        _print_full_row([("Browsing destination: ", STYLE_ROW_HEADER), (str(current), STYLE_PATH)], style=STYLE_ROW_HEADER)
        dens_here = _stores_under_path(dens, current)
        if dens_here:
            _print_notice("Known dens in this path", style=STYLE_SAFE)
            for index, store in enumerate(dens_here[:5], start=1):
                _print_path_option(f"D{index}", store.name, store.root_path)
            _print_notice("Tip: choose D1 directly, or choose 7 for a paged den selector.")
        all_folders = _sorted_child_folders(current)
        page_count = max(1, (len(all_folders) + 4) // 5)
        if folder_page >= page_count:
            folder_page = 0
        folders = all_folders[folder_page * 5 : folder_page * 5 + 5]
        if len(all_folders) > 5:
            _print_notice(f"Folders page {folder_page + 1} of {page_count}; sorted by sampled size.")
        for index, (path, size_bytes) in enumerate(folders, start=1):
            _print_folder_option(str(index), path.name, size_bytes)
        if len(all_folders) > 5:
            _print_option("6", "More folders")
        _print_option("7", "Select a known den in this path")
        _print_option("8", "Parent folder")
        _print_option("9", "Create / use DEN here")
        _print_option("0", "Manual path")
        selection = Prompt.ask(_prompt("Choose destination folder (Ctrl-C to exit)"), default="9", console=console).strip()
        if selection.lower().startswith("d") and len(selection) > 1:
            try:
                den_index = int(selection[1:])
            except ValueError:
                _print_error("Invalid den choice. Use D plus a number, like D1.")
                continue
            if 1 <= den_index <= len(dens_here[:5]):
                store = dens_here[den_index - 1]
                _mark_store_used(store)
                return store.root_path
            _print_error("Invalid den choice. Try again.")
            continue
        if selection == "6" and len(all_folders) > 5:
            folder_page = (folder_page + 1) % page_count
            continue
        if selection == "7":
            path = _pick_registered_store(dens_here, "den")
            if path:
                return path
            continue
        if selection == "8":
            current = current.parent
            folder_page = 0
            continue
        if selection == "9":
            path = _confirm_destination_path(current)
            if path:
                _register_or_mark_store_path(path, StoreKind.DEN, path.name or "den")
                return path
            continue
        if selection == "0":
            path = _manual_destination_path("Destination path")
            if path:
                _register_or_mark_store_path(path, StoreKind.DEN, path.name or "den")
                return path
            continue
        if selection.startswith(("/", "~", ".")):
            path = _manual_destination_path("Destination path", initial=selection)
            if path:
                _register_or_mark_store_path(path, StoreKind.DEN, path.name or "den")
                return path
            continue
        try:
            index = int(selection)
        except ValueError:
            _print_error("Invalid destination choice. Try again.")
            continue
        if 1 <= index <= len(folders):
            current = folders[index - 1][0]
            folder_page = 0
            continue
        _print_error("Invalid destination choice. Try again.")


def _standard_path_choices(*, limit: int | None = None) -> list[tuple[str, Path]]:
    choices = standard_path_choices()
    return choices[:limit] if limit else choices


def _known_stores(store_kind: StoreKind) -> list[Store]:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            return _list_configured_stores(connection, config, store_kind)
    except typer.BadParameter:
        return []


def _list_configured_stores(connection, config: RawdogConfig, store_kind: StoreKind) -> list[Store]:
    _ensure_configured_store_registered(connection, config, store_kind)
    return list_stores(connection, store_kind=store_kind)


def _ensure_configured_store_registered(connection, config: RawdogConfig, store_kind: StoreKind) -> None:
    configured_root = config.working_root if store_kind == StoreKind.YARD else config.archive_root
    if configured_root is None:
        return
    root_path = configured_root.expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        return
    opposite_root = config.archive_root if store_kind == StoreKind.YARD else config.working_root
    if opposite_root and opposite_root.expanduser().resolve() == root_path:
        return
    row = connection.execute("SELECT name, store_kind FROM stores WHERE root_path = ?", (str(root_path),)).fetchone()
    if row and row["store_kind"] == store_kind.value:
        return
    name = row["name"] if row else "primary"
    create_or_update_store(
        connection,
        StoreCreate(name=name, root_path=root_path, store_kind=store_kind),
    )


STORE_PICKER_PAGE_SIZE = 5


def _store_page(stores: list[Store], page: int) -> list[Store]:
    start = page * STORE_PICKER_PAGE_SIZE
    return stores[start : start + STORE_PICKER_PAGE_SIZE]


def _has_next_store_page(stores: list[Store], page: int) -> bool:
    return (page + 1) * STORE_PICKER_PAGE_SIZE < len(stores)


def _next_store_page(stores: list[Store], page: int) -> int:
    next_page = page + 1
    if next_page * STORE_PICKER_PAGE_SIZE >= len(stores):
        return 0
    return next_page


def _mark_store_used(store: Store) -> None:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            mark_store_used(connection, store.store_id)
    except typer.BadParameter:
        return


def _mark_store_path_used(path: Path, store_kind: StoreKind) -> None:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            store = find_store_for_path(connection, path, store_kind)
            if store:
                mark_store_used(connection, store.store_id)
    except typer.BadParameter:
        return


def _store_for_exact_path(root_path: Path, store_kind: StoreKind) -> Store | None:
    resolved = root_path.expanduser().resolve()
    for store in _known_stores(store_kind):
        if store.root_path == resolved:
            return store
    return None


def _register_or_mark_store_path(path: Path, store_kind: StoreKind, preferred_name: str) -> Store | None:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            existing = find_store_for_path(connection, path, store_kind)
            if existing:
                return mark_store_used(connection, existing.store_id)
            name = _available_store_name(connection, store_kind, preferred_name)
            store = create_or_update_store(
                connection,
                StoreCreate(name=name, root_path=path, store_kind=store_kind),
            )
            return mark_store_used(connection, store.store_id)
    except typer.BadParameter:
        return None


def _available_store_name(connection, store_kind: StoreKind, preferred_name: str) -> str:
    base = preferred_name.strip() or store_kind.value
    candidate = base
    counter = 2
    while get_store_by_name(connection, candidate, store_kind):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _stores_under_path(stores: list[Store], root: Path) -> list[Store]:
    resolved = root.expanduser().resolve()
    return [
        store
        for store in stores
        if store.root_path == resolved or resolved in store.root_path.parents
    ]


def _pick_registered_store(stores: list[Store], noun: str) -> Path | None:
    if not stores:
        _print_notice(f"No registered RAWDOG {noun}s available here.", style=STYLE_ROW_SELECTED)
        return None
    page = 0
    while True:
        page_stores = _store_page(stores, page)
        for index, store in enumerate(page_stores, start=1):
            _print_path_option(str(index), store.name, store.root_path)
        if _has_next_store_page(stores, page):
            _print_option("6.", f"Next {noun}s")
        _print_option("0.", "Back")
        selection = Prompt.ask(_prompt(f"Choose RAWDOG {noun}"), default="1", console=console).strip()
        if selection == "0":
            return None
        if selection == "6" and _has_next_store_page(stores, page):
            page = _next_store_page(stores, page)
            continue
        try:
            index = int(selection)
        except ValueError:
            _print_error("Invalid store choice. Try again.")
            continue
        if 1 <= index <= len(page_stores):
            store = page_stores[index - 1]
            _mark_store_used(store)
            return store.root_path
        _print_error("Invalid store choice. Try again.")


def _manual_existing_directory(label: str) -> Path | None:
    path = parse_user_path(Prompt.ask(_prompt(label), console=console)).expanduser().resolve()
    return path if _is_existing_directory(path) else None


def _is_existing_directory(path: Path) -> bool:
    if path.exists() and path.is_dir():
        return True
    _print_error(f"Folder must already exist: {path}")
    return False


def _manual_destination_path(label: str, initial: str | None = None) -> Path | None:
    raw = initial if initial is not None else Prompt.ask(_prompt(label), console=console)
    return _confirm_destination_path(parse_user_path(raw).expanduser().resolve())


def _confirm_destination_path(path: Path) -> Path | None:
    if path.exists():
        if path.is_dir():
            return path
        _print_error(f"Destination exists but is not a folder: {path}")
        return None
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        _print_error(f"Parent folder does not exist: {parent}")
        return None
    if _yes_no(f"Destination does not exist. Create {path}?", default=True):
        path.mkdir(parents=True, exist_ok=True)
        return path
    return None


def _sorted_child_folders(root: Path) -> list[tuple[Path, int]]:
    try:
        children = [path for path in root.iterdir() if path.is_dir()]
    except OSError as exc:
        _print_error(f"Cannot read folder: {exc}")
        return []
    return sorted(
        ((path, _estimate_folder_size(path)) for path in children),
        key=lambda item: (-item[1], item[0].name.lower()),
    )


def _estimate_folder_size(root: Path, *, max_files: int = 500) -> int:
    total = 0
    counted = 0
    stack = [root]
    while stack and counted < max_files:
        folder = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if counted >= max_files:
                break
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    total += entry.stat().st_size
                    counted += 1
            except OSError:
                continue
    return total


def _format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1000
    return f"{value:.1f} TB"


def _format_duration(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remainder = minutes % 60
    return f"{hours} hr {remainder} min" if remainder else f"{hours} hr"


def _format_copy_progress(copied_bytes: int, total_bytes: int, started_at: float) -> str:
    elapsed = max(monotonic() - started_at, 0.001)
    mbps = copied_bytes / elapsed / 1_000_000
    if copied_bytes <= 0 or mbps <= 0:
        eta = "calculating"
    else:
        eta = _format_duration(max(total_bytes - copied_bytes, 0) / (mbps * 1_000_000))
    return (
        f"{_format_bytes(copied_bytes)} / {_format_bytes(total_bytes)} copied | "
        f"avg {mbps:.1f} MB/s | ETA {eta}"
    )


def _same_filesystem_best_effort(source_root: Path, destination_root: Path) -> bool:
    try:
        return source_root.stat().st_dev == destination_root.stat().st_dev
    except OSError:
        return False


def _build_wings_command(
    *,
    caffeinate_path: str,
    rawdog_executable: str,
    args: list[str],
    pid: int | None,
) -> list[str]:
    base = [caffeinate_path, "-dimsu"]
    if pid is not None:
        return [*base, "-w", str(pid)]
    if args and Path(args[0]).name == "rawdog":
        return [*base, *args]
    return [*base, rawdog_executable, *args]


def _print_big_job_warning(plan: DenPlan, source_root: Path, destination_root: Path, action: DenTransferAction) -> None:
    if plan.files_to_transfer < 1000 and plan.bytes_to_transfer < 50_000_000_000:
        return
    estimates = []
    for mbps in (30, 50, 80, 120):
        seconds = plan.bytes_to_transfer / (mbps * 1_000_000)
        estimates.append(f"{mbps} MB/s: {_format_duration(seconds)}")
    lines = [
        f"Queued: {plan.files_to_transfer} files / {_format_bytes(plan.bytes_to_transfer)}",
        "Copy estimates are rough and depend on drive speed, cable, filesystem, and current load.",
        "Estimated transfer time: " + " | ".join(estimates),
    ]
    if action == DenTransferAction.COPY and _same_filesystem_best_effort(source_root, destination_root):
        lines.append(
            "Source and destination appear to be on the same filesystem; copy may be slower because the "
            "drive is reading and writing at the same time."
        )
        lines.append(
            "For reviewed same-drive consolidation, --action move is faster and preserves Finder Created date."
        )
    lines.append("During commit, RAWDOG updates progress by file and bytes copied.")
    console.print(Panel("\n".join(lines), title="Large Job", border_style="bright_yellow", style=STYLE_PANEL))


def _choose_store_path(label: str, store_kind: StoreKind) -> Path:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            stores = _list_configured_stores(connection, config, store_kind)
    except typer.BadParameter:
        stores = []
    if not stores:
        return _choose_path(label, browse_number_selection=True)
    noun = "den" if store_kind == StoreKind.DEN else "yard"
    page = 0
    while True:
        _print_section_row(f"{label} (Ctrl-C to exit)")
        _print_notice(f"Established RAWDOG {noun}s", style=STYLE_SAFE)
        page_stores = _store_page(stores, page)
        for index, store in enumerate(page_stores, start=1):
            _print_path_option(str(index), store.name, store.root_path)
        if _has_next_store_page(stores, page):
            _print_option("6.", f"Next {noun}s")
        _print_option("0.", "Other / browse common paths")
        _print_notice("Tip: enter b1 to browse inside an established store.")
        selection = Prompt.ask(_prompt("Choose store, browse, or type a path"), default="1", console=console).strip()
        if selection == "0":
            return _choose_path(label, browse_number_selection=True)
        if selection == "6" and _has_next_store_page(stores, page):
            page = _next_store_page(stores, page)
            continue
        if selection.lower().startswith("b") and len(selection) > 1:
            try:
                browse_index = int(selection[1:])
            except ValueError:
                _print_error("Invalid browse choice. Use b plus a number, like b1.")
                continue
            if 1 <= browse_index <= len(page_stores):
                store = page_stores[browse_index - 1]
                _mark_store_used(store)
                return _browse_folder(store.root_path)
            _print_error("Invalid browse choice. Try again.")
            continue
        if selection.startswith(("/", "~", ".")):
            return parse_user_path(selection)
        try:
            index = int(selection)
        except ValueError:
            _print_error("Invalid choice. Enter a number, b-number, or a path.")
            continue
        if 1 <= index <= len(page_stores):
            store = page_stores[index - 1]
            _mark_store_used(store)
            return store.root_path
        _print_error("Invalid choice. Try again.")


def _choose_project_root(label: str, folder_name: str) -> Path:
    base = _choose_path(f"{label} base location")
    while True:
        _print_full_row([("Selected base: ", STYLE_ROW_HEADER), (str(base), STYLE_PATH)], style=STYLE_ROW_HEADER)
        _print_option("1.", "Search for existing folder under this base")
        _print_option("2.", f"Create {folder_name} here")
        _print_option("3.", "Use this root directly")
        _print_option("4.", "Enter exact path")
        _print_option("0.", "Pick a different base")
        choice = Prompt.ask(
            "Choose folder action (Ctrl-C to exit)",
            choices=["0", "1", "2", "3", "4"],
            default="2",
            console=console,
        )
        if choice == "0":
            base = _choose_path(f"{label} base location")
            continue
        if choice == "1":
            found = _search_folders(base, Prompt.ask("Folder name search", console=console).strip())
            if not found:
                _print_notice("No matching folders found.", style=STYLE_ROW_SELECTED)
                continue
            for index, path in enumerate(found, start=1):
                _print_path_option(str(index), path.name, path)
            picked = Prompt.ask("Choose folder", default="1", console=console).strip()
            try:
                return found[int(picked) - 1]
            except (ValueError, IndexError):
                _print_error("Invalid choice. Try again.")
                continue
        if choice == "2":
            target = base / folder_name
            if _yes_no(f"Create or use {target}?", default=True):
                target.mkdir(parents=True, exist_ok=True)
                return target
            continue
        if choice == "3":
            if _yes_no(
                f"Use {base} directly? Projects may be written directly under this root.",
                default=False,
            ):
                return base
            continue
        return parse_user_path(Prompt.ask("Exact path", console=console))


def _search_folders(base: Path, query: str) -> list[Path]:
    if not query:
        return []
    lowered = query.lower()
    matches: list[Path] = []
    for path in base.expanduser().iterdir() if base.expanduser().exists() else []:
        if path.is_dir() and lowered in path.name.lower():
            matches.append(path)
    return sorted(matches)[:20]


def _print_layout_analysis(analysis: LayoutAnalysis) -> None:
    table = _styled_table(title="Source Layout Detection")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("RAW/video files", str(analysis.file_count))
    table.add_row("Camera-dump files", str(analysis.raw_dump_files))
    table.add_row("Semi-organized files", str(analysis.organized_files))
    table.add_row("Recommendation", analysis.recommendation)
    table.add_row("Confidence", f"{analysis.confidence}%")
    console.print(table)
    for signal in analysis.signals:
        _print_notice(f"- {signal}", style=STYLE_ROW)
    _print_full_row(
        [
            ("Operator confirmation required: ", STYLE_ROW_SELECTED),
            ("RAWDOG suggests layout behavior but never silently reorganizes.", STYLE_ROW_SELECTED),
        ],
        style=STYLE_ROW_SELECTED,
    )


def _destination_inside_source(source_root: Path, destination_root: Path) -> bool:
    source = source_root.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    return source in destination.parents


def _print_ai_review_prompt(
    title: str,
    paths: list[Path],
    suggestion: str,
    *,
    plan_id: int | None = None,
    rows: list[ExecutionPlanRow] | None = None,
) -> None:
    if not paths and not rows:
        return
    shown_rows = (rows or [])[:6]
    shown_paths = paths[:8] if not shown_rows else []
    prompt_lines = [
        "This is what is going on:",
        f"RAWDOG found: {title}.",
        "",
        "Meaning:",
        f"- {suggestion}",
        "- RAWDOG has paused any cleanup-style decision for these rows.",
        "- Do not delete or remove originals based only on this warning.",
        "",
    ]
    if plan_id is not None:
        prompt_lines.extend(
            [
                "Useful RAWDOG commands:",
                f"- rawdog plans show {plan_id}",
                f"- rawdog plans review {plan_id}",
                f"- rawdog plans show {plan_id} --ops",
                f"- rawdog plans ops {plan_id} --verbose --limit 100",
                "",
            ]
        )
    if shown_rows:
        prompt_lines.append("Example rows to review:")
        for row in shown_rows:
            reason = _review_reason(row)
            prompt_lines.extend(
                [
                    f"- Row #{row.row_id}: {reason}",
                    f"  Source: {row.source_path}",
                    f"  Destination: {row.destination_path}",
                ]
            )
            if row.error:
                prompt_lines.append(f"  Error: {row.error}")
        if rows and len(rows) > len(shown_rows):
            prompt_lines.append(f"- ...and {len(rows) - len(shown_rows)} more rows.")
        prompt_lines.append("")
    elif shown_paths:
        prompt_lines.extend(["Relevant paths:", *[f"- {path}" for path in shown_paths]])
        if len(paths) > len(shown_paths):
            prompt_lines.append(f"- ...and {len(paths) - len(shown_paths)} more paths.")
        prompt_lines.append("")
    prompt_lines.extend(
        [
            "Decision options:",
            "- Resume: only after the source, destination, mount, free space, and permissions look correct.",
            "- Leave paused: safest choice if anything is unclear.",
            "- Manually inspect: compare source and destination size/path before deciding.",
            "- Skip: acceptable only when the destination copy is intentionally already present.",
            "- Retry/resume: useful for mount, cable, free-space, or permission failures after fixing the cause.",
            "",
            "Prompt to paste into ChatGPT/AI:",
            "I need help reviewing a RAWDOG archival plan before taking any cleanup action.",
            "Use the row IDs, source paths, destination paths, statuses, audit reasons, and errors below.",
            "Help me decide whether to resume, leave paused, skip, retry, or manually inspect each group.",
            "Do not suggest deleting originals unless I explicitly confirm verified backups.",
        ]
    )
    console.print(
        Panel(
            "\n".join(prompt_lines),
            title=f"Ask ChatGPT / AI Review Prompt: {title}",
            border_style="yellow",
        )
    )


def _review_reason(row: ExecutionPlanRow) -> str:
    parts = [f"status={row.status}"]
    if row.audit_status:
        parts.append(f"audit={row.audit_status}")
    if row.status == "failed":
        parts.append("transfer failed before RAWDOG could verify the destination")
    elif row.status in {"collision", "skipped_collision"}:
        parts.append("same filename exists at destination with a different size")
    elif row.status == "skipped_existing_partial":
        parts.append("pre-existing .partial file requires manual review")
    elif row.audit_status == "destination_missing":
        parts.append("destination file is missing after transfer/audit")
    elif row.audit_status == "size_mismatch":
        parts.append("destination size does not match source")
    elif row.audit_status and row.audit_status.startswith("needs"):
        parts.append("manual review required before cleanup")
    return "; ".join(parts)


def _needs_plan_review(row: ExecutionPlanRow) -> bool:
    audit_status = row.audit_status or ""
    return (
        row.status == "failed"
        or row.status.startswith("skip")
        or row.status.startswith("skipped")
        or row.status in {"collision", "skipped_existing_partial"}
        or audit_status.startswith("needs")
        or audit_status.endswith("missing")
        or audit_status == "size_mismatch"
        or bool(row.error)
    )


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
    while True:
        banner = Text()
        banner.append(RAWDOG_ASCII, style=STYLE_ACTION)
        banner.append("RAWDOG\n", style=STYLE_TITLE)
        banner.append(
            "RAW photo managing tool that can fetch, copy, and audit your RAW libraries.",
            style=STYLE_PANEL,
        )
        console.print(Panel(banner, border_style="green", style=STYLE_PANEL, expand=True))

        table = _styled_table(
            title="Choose A Workflow",
            title_style=STYLE_ACTION,
            border_style="green",
            style=STYLE_PANEL,
            row_styles=STYLE_ROWS,
            expand=True,
        )
        table.add_column("Option", style=STYLE_ACTION, justify="right")
        table.add_column("Workflow", style=STYLE_SAFE)
        table.add_column("Action", style=STYLE_PATH)
        table.add_row("i", "Setup / settings", "Set yards, dens, and defaults")
        table.add_row("1", "Fetch card -> Yard", "Copy card/flash files to yard")
        table.add_row("2", "COPY/archive -> Den", "Copy files to archive; source stays")
        table.add_row("3", "Junkyard report only", "No writes; reports den-recorded files")
        table.add_row("4", "MOVE same-drive -> Den", "Move files with same-filesystem rename")
        table.add_row("5", "Audit / inspect folder", "Sniff layout or score a folder")
        table.add_row("6", "Verify source -> destination", "Check source is represented")
        table.add_row("7", "Review / resume old plans", "Inspect, run, resume, or prune")
        table.add_row("8", "Help", "Show command examples")
        table.add_row("9", "Den / yard management", "Create, relink, list, or forget stores")
        table.add_row("0", "Quit", "Exit RAWDOG")
        console.print(table)
        _print_full_row(
            [
                ("Preview-first: ", STYLE_WARN),
                ("fetch, breed, and den do not write archive files unless you explicitly choose commit.", STYLE_WARN),
            ],
            style=STYLE_WARN,
        )
        if not _is_initialized():
            _print_init_guidance()
        _print_latest_plan_hint()
        choice = Prompt.ask(
            _prompt("CHOOSE AN OPTION"),
            choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "i", "init", "initialize", "setup"],
            default="i" if not _is_initialized() else "1",
            console=console,
        )
        if choice == "0":
            _print_notice("Goodbye.", style=STYLE_SAFE)
            return
        try:
            _run_home_choice(choice)
        except typer.BadParameter as exc:
            _print_error(f"Error: {exc}")
        except SafetyError as exc:
            _print_error(f"Safety stop: {exc}")
        except KeyboardInterrupt:
            _print_notice("Cancelled.", style=STYLE_ROW_SELECTED)
        Prompt.ask(
            _prompt("Press Enter to return to RAWDOG"),
            console=console,
        )


def _print_latest_plan_hint() -> None:
    try:
        _, config = _load_or_exit()
        with session(config.database_path) as connection:
            latest_plan = get_latest_execution_plan(connection)
        if latest_plan:
            _print_full_row(
                [
                    ("Last plan: ", STYLE_ROW_SELECTED),
                    (f"#{latest_plan.plan_id} {latest_plan.status.value} - {latest_plan.what}", STYLE_ROW_SELECTED),
                ],
                style=STYLE_ROW_SELECTED,
            )
    except (typer.BadParameter, OSError, sqlite3.Error):
        pass


def _optional_prompt(label: str) -> str | None:
    value = Prompt.ask(label, default="", console=console).strip()
    return value or None


def _yes_no(label: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = Prompt.ask(f"{label} {suffix}", default="y" if default else "n", console=console)
        answer = raw.strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        console.print("[bold red]Please answer y or n.[/]")


def _parse_cli_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def _run_home_choice(choice: str) -> None:
    if choice in {"i", "init", "initialize", "setup"}:
        _home_init()
    elif choice == "1":
        _home_fetch()
    elif choice == "2":
        _home_backup()
    elif choice == "3":
        _home_cleanup_review()
    elif choice == "4":
        _home_fast_move()
    elif choice == "5":
        _home_inspect()
    elif choice == "6":
        _home_verify()
    elif choice == "7":
        _home_status()
    elif choice == "8":
        _show_command_examples()
    elif choice == "9":
        _home_store_setup()


def _home_init() -> None:
    mode_choice = Prompt.ask(
        "How do you organize your shoots?",
        choices=["date", "project"],
        default="project",
        console=console,
    )
    working_root = (
        _choose_project_root("Default working library", "RAWDOG_YARD")
        if _yes_no("Set default working path?")
        else None
    )
    archive_root = (
        _choose_project_root("Default archive library", "RAWDOG_DEN")
        if _yes_no("Set default archive path?")
        else None
    )
    init(
        working_root=working_root,
        archive_root=archive_root,
        mode=OrganizationMode(mode_choice),
        date_template="YYYY/YYYY-MM",
        project_template="YYYY/YYYYMMDD_PROJECT",
    )
    if working_root and _confirm_store_registration(working_root, StoreKind.YARD):
        _setup_store("primary", working_root, StoreKind.YARD)
    if archive_root and _confirm_store_registration(archive_root, StoreKind.DEN):
        _setup_store("primary", archive_root, StoreKind.DEN)


def _confirm_store_registration(root: Path, store_kind: StoreKind) -> bool:
    noun = "working yard" if store_kind == StoreKind.YARD else "archive den"
    _print_full_row(
        [
            (f"Selected {noun}: ", STYLE_ROW_HEADER),
            (str(root.expanduser().resolve()), STYLE_PATH),
        ],
        style=STYLE_ROW_HEADER,
    )
    return _yes_no(
        f"Register {root.expanduser().resolve()} as a RAWDOG {store_kind.value}?",
        default=True,
    )


def _home_fetch() -> None:
    source = _choose_source_path("Import source")
    destination = _choose_store_path("Import destination", StoreKind.YARD)
    project_name = _optional_prompt("Project name, or Enter for date/layout detection")
    detect_sessions = _yes_no("Detect sessions by time gaps?")
    fetch(
        source=source,
        destination=destination,
        profile=None,
        project_name=project_name,
        profile_name=None,
        naming=None,
        collision_policy=None,
        verify_after_copy=None,
        detect_sessions=detect_sessions,
        dry_run=True,
    )


def _print_copy_to_den_guidance() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "This is the safe archive path.",
                    "",
                    "What happens:",
                    "1. RAWDOG scans the working source.",
                    "2. It writes a dry-run plan first.",
                    "3. On commit, it copies files into the den without deleting the source.",
                    "4. Existing same-name/same-size files are skipped; collisions are held for review.",
                    "",
                    "Use this when you finished editing and want the den/archive to receive a copy.",
                ]
            ),
            title="Archive Copy -> Den",
            border_style="green",
            style=STYLE_PANEL,
            expand=True,
        )
    )


def _print_fast_move_guidance() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "You selected transfer mode: MOVE.",
                    "Fast move is only for moving files on the same drive/filesystem.",
                    "",
                    "What happens:",
                    "1. RAWDOG scans the source and writes a reviewable dry-run plan.",
                    "2. It refuses if source and destination are not on the same filesystem.",
                    "3. On commit, it uses os.rename to move each file into the den.",
                    "4. File names stay unchanged; existing destination files are never overwritten.",
                    "5. Skipped/existing rows stay in the source folder for review; RAWDOG does not delete them.",
                    "",
                    "Use this to clean up same-drive folder mess without duplicating storage.",
                    "For copy/archive, use menu option 2 instead.",
                ]
            ),
            title="Fast Same-Drive MOVE -> Den",
            border_style="yellow",
            style=STYLE_PANEL,
            expand=True,
        )
    )


def _home_backup() -> None:
    _print_copy_to_den_guidance()
    source = _choose_store_path("Working project/source", StoreKind.YARD)
    destination = _choose_store_path("Archive destination", StoreKind.DEN)
    project_name = _optional_prompt("Project name, or Enter to skip")
    backup(
        project_name=project_name,
        source=source,
        destinations=[destination],
        profile=None,
        dry_run=True,
    )


def _home_cleanup_review() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "Junkyard is report-only. It does not delete files.",
                    "RAWDOG compares a yard against a den catalog and reports files that appear represented in the den.",
                    "Use the report to decide what you want to remove manually from your working disk.",
                ]
            ),
            title="Junkyard Cleanup Review",
            border_style="yellow",
            style=STYLE_PANEL,
            expand=True,
        )
    )
    yard = _choose_store_path("Working yard to review", StoreKind.YARD)
    den_root = _choose_store_path("Den to compare against", StoreKind.DEN)
    yard_store = _store_for_exact_path(yard, StoreKind.YARD)
    den_store = _store_for_exact_path(den_root, StoreKind.DEN)
    if yard_store is None:
        raise typer.BadParameter("Selected yard is not registered. Use option 9 to register it first.")
    if den_store is None:
        raise typer.BadParameter("Selected den is not registered. Use option 9 to register it first.")
    junkyard(
        yard_name=yard_store.name,
        den_name=den_store.name,
        validate_first=True,
    )


def _home_fast_move() -> None:
    _print_fast_move_guidance()
    _home_den(action=DenTransferAction.MOVE)


def _home_den(action: DenTransferAction = DenTransferAction.COPY) -> None:
    if action == DenTransferAction.COPY:
        _print_den_guidance()
    source = _choose_source_path("Messy source")
    destination = _choose_den_destination_path("Clean destination")
    if action == DenTransferAction.MOVE:
        try:
            ensure_same_filesystem(source, destination)
        except SafetyError as exc:
            raise typer.BadParameter(
                f"Fast move is same-drive only: {exc}. Use option 2 for safe copy-to-den instead."
            ) from exc
    _print_transfer_mode(action, source, destination)
    destination_inside_source = _destination_inside_source(source, destination)
    layout_analysis = analyze_source_layout(
        source,
        exclude_roots=[destination] if destination_inside_source else [],
    )
    _print_layout_analysis(layout_analysis)
    default_layout = "date" if layout_analysis.recommendation == "ddd" else "preserve-dates"
    layout = _choose_den_layout(default_layout)
    group_by = _choose_date_grouping(layout) if _layout_generates_date_groups(layout) else None
    project_name = _optional_prompt("Project name, or Enter to skip")
    start_date, end_date = (
        _choose_project_date_scope(source, [destination] if destination_inside_source else [])
        if layout in {DenLayoutMode.PROJECT, DenLayoutMode.PROJECT_DATES}
        else (None, None)
    )
    dry_run = not _yes_no(f"Commit {action.value.upper()} plan now? Dry-run is safer.", default=False)
    den(
        source=source,
        destination=destination,
        project_name=project_name,
        workflow_name=None,
        layout=layout,
        action=action,
        template=None,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        limit=None,
        dry_run=dry_run,
    )


def _print_transfer_mode(action: DenTransferAction, source: Path, destination: Path) -> None:
    if action == DenTransferAction.MOVE:
        title = "Transfer Mode: MOVE"
        lines = [
            "RAWDOG will create a MOVE plan.",
            "On commit, each successful row uses os.rename on the same filesystem.",
            "Source files that move successfully will no longer remain at the source path.",
            "Skipped/existing rows remain at the source path for review; skip is not a delete signal.",
            "Existing destination files are never overwritten.",
        ]
        border_style = "yellow"
    else:
        title = "Transfer Mode: COPY"
        lines = [
            "RAWDOG will create a COPY plan.",
            "On commit, source files remain in place.",
            "Existing destination files are never overwritten.",
        ]
        border_style = "green"
    lines.extend([f"Source: {source}", f"Destination: {destination}"])
    console.print(Panel("\n".join(lines), title=title, border_style=border_style, style=STYLE_PANEL, expand=True))


def _choose_den_layout(default_layout: str) -> DenLayoutMode:
    options = [
        ("1", DenLayoutMode.PRESERVE),
        ("2", DenLayoutMode.PRESERVE_DATES),
        ("3", DenLayoutMode.DATE),
        ("4", DenLayoutMode.PROJECT),
        ("5", DenLayoutMode.PROJECT_DATES),
    ]
    by_key = {key: layout for key, layout in options}
    by_value = {layout.value: layout for _, layout in options}
    default_choice = next((key for key, layout in options if layout.value == default_layout), "2")
    _print_den_layout_guidance(options)
    while True:
        choice = Prompt.ask(
            "Choose layout",
            choices=[key for key, _ in options] + [layout.value for _, layout in options],
            default=default_choice,
            console=console,
        )
        if choice in by_key:
            return by_key[choice]
        if choice in by_value:
            return by_value[choice]


def _layout_generates_date_groups(layout: DenLayoutMode) -> bool:
    return layout in {DenLayoutMode.PRESERVE_DATES, DenLayoutMode.DATE, DenLayoutMode.PROJECT_DATES}


def _choose_date_grouping(layout: DenLayoutMode) -> DateGroupMode:
    if layout == DenLayoutMode.PRESERVE_DATES:
        _print_full_row(
            [
                ("Date grouping only applies to camera-dump rows. ", STYLE_ROW_SELECTED),
                ("Existing meaningful/date folders are still preserved or normalized.", STYLE_ROW_SELECTED),
            ],
            style=STYLE_ROW_SELECTED,
        )
    table = _styled_table(title="Date Grouping")
    table.add_column("Option", justify="right", style=STYLE_ACTION)
    table.add_column("Grouping", style=STYLE_ACTION)
    table.add_column("Example", style=STYLE_SAFE)
    if layout == DenLayoutMode.PROJECT_DATES:
        table.add_row("1", "month", "Soccer-202601")
        table.add_row("2", "day", "Soccer-20260115")
    else:
        table.add_row("1", "month", "2026/2026-01")
        table.add_row("2", "day", "2026/20260115")
    console.print(table)
    choice = Prompt.ask(
        "Group generated date folders by",
        choices=["1", "2", "month", "day"],
        default="1",
        console=console,
    )
    return DateGroupMode.DAY if choice in {"2", "day"} else DateGroupMode.MONTH


def _den_template_for_grouping(layout: DenLayoutMode, group_by: DateGroupMode | None) -> str | None:
    if group_by is None:
        return None
    if layout == DenLayoutMode.PROJECT_DATES:
        return "YYYY/PROJECT-YYYYMMDD" if group_by == DateGroupMode.DAY else "YYYY/PROJECT-YYYYMM"
    return "YYYY/YYYYMMDD" if group_by == DateGroupMode.DAY else "YYYY/YYYY-MM"


def _choose_project_date_scope(
    source_root: Path,
    exclude_roots: list[Path],
) -> tuple[date | None, date | None]:
    items = scan_raw_files(source_root, exclude_roots=exclude_roots)
    counts = capture_date_counts(items)
    if len(counts) <= 2:
        return None, None
    dates = sorted(counts)
    console.print(
        Panel(
            "\n".join(
                [
                    f"[bold yellow]This source spans {len(dates)} capture dates.[/]",
                    f"First date: {dates[0].isoformat()}",
                    f"Last date: {dates[-1].isoformat()}",
                    "",
                    "If this is one project, keep all dates.",
                    "If this card/folder contains multiple projects, scope this plan to a date range.",
                ]
            ),
            title="Project Scope Check",
            border_style="yellow",
            style=STYLE_PANEL,
        )
    )
    if not _yes_no("Scope this project plan to a date range?", default=False):
        return None, None
    while True:
        start_raw = Prompt.ask("Start date YYYY-MM-DD", default=dates[0].isoformat(), console=console)
        end_raw = Prompt.ask("End date YYYY-MM-DD", default=dates[-1].isoformat(), console=console)
        try:
            start = _parse_cli_date(start_raw)
            end = _parse_cli_date(end_raw)
        except ValueError as exc:
            console.print(f"[bold red]Invalid date:[/] {exc}")
            continue
        if start > end:
            console.print("[bold red]Start date must be before or equal to end date.[/]")
            continue
        return start, end


def _print_project_scope_warning(
    source_root: Path,
    exclude_roots: list[Path],
    *,
    start_date: date | None,
    end_date: date | None,
) -> None:
    if start_date is not None or end_date is not None:
        console.print(
            "[bold green]Project date scope:[/] "
            f"{start_date.isoformat() if start_date else 'beginning'} -> "
            f"{end_date.isoformat() if end_date else 'end'}"
        )
        return
    items = scan_raw_files(source_root, exclude_roots=exclude_roots)
    counts = capture_date_counts(items)
    if len(counts) <= 2:
        return
    dates = sorted(counts)
    console.print(
        Panel(
            "\n".join(
                [
                    f"This project source spans {len(dates)} capture dates.",
                    f"First date: {dates[0].isoformat()}",
                    f"Last date: {dates[-1].isoformat()}",
                    "If this is not one project, rerun with --start-date and --end-date, "
                    "or split into separate project plans.",
                ]
            ),
            title="Project Scope Review",
            border_style="yellow",
            style=STYLE_PANEL,
        )
    )


def _print_den_layout_guidance(options: list[tuple[str, DenLayoutMode]] | None = None) -> None:
    table = _styled_table(title="DEN Layout Options")
    if options:
        table.add_column("Option", justify="right", style=STYLE_ACTION)
    table.add_column("Layout", style=STYLE_ACTION)
    table.add_column("What it does", style=STYLE_SAFE)
    descriptions = {
        DenLayoutMode.PRESERVE: "Mirror source folders exactly. No generated date grouping; camera wrappers are kept.",
        DenLayoutMode.PRESERVE_DATES: "Keep meaningful folders, normalize existing date-like folders, and drop camera wrappers. Camera dumps can group by month/day.",
        DenLayoutMode.DATE: "Ignore source folders and group by capture date. Default grouping is month.",
        DenLayoutMode.PROJECT: "Create one dated project/session folder from the earliest file date; files are directly inside it.",
        DenLayoutMode.PROJECT_DATES: "Create project plus date buckets. Default month buckets look like Soccer-202601.",
    }
    rows = options or [(None, layout) for layout in DenLayoutMode]
    for key, layout in rows:
        if key is None:
            table.add_row(layout.value, descriptions[layout])
        else:
            table.add_row(key, layout.value, descriptions[layout])
    console.print(table)


def _print_den_guidance() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "[bold green]DEN is for consolidation into an archive store.[/]",
                    "",
                    "Same drive: audit first, review the plan, then MOVE can be fast and avoids duplicate storage.",
                    "Different drives: COPY first, validate, then keep source cleanup/manual moves separate.",
                    "",
                    "App Support remembers known dens and yards.",
                    "Each den/yard also carries .rawdog/store.json and .rawdog/store.sqlite.",
                    "",
                    "After this den is established, use backup/breed to copy it to another drive.",
                ]
            ),
            title="Den Workflow",
            border_style="yellow",
            style=STYLE_PANEL,
            expand=True,
        )
    )


def _home_inspect() -> None:
    root = _choose_source_path("Folder to inspect")
    action = Prompt.ask("Inspect action", choices=["sniff", "score"], default="sniff", console=console)
    if action == "score":
        score(root=root)
    else:
        sniff(roots=[root])


def _home_verify() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "Verify checks whether a source is represented in a destination.",
                    "It is useful before manual cleanup or before trusting an archive copy.",
                    "This command does not delete, rename, or move files.",
                ]
            ),
            title="Verify Source -> Destination",
            border_style="green",
            style=STYLE_PANEL,
            expand=True,
        )
    )
    source = _choose_source_path("Source to verify")
    destination = _choose_den_destination_path("Destination to check")
    verify(source=source, destination=destination)


def _home_status() -> None:
    status()
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plans = list_execution_plans(connection, limit=5)
    if not plans:
        return
    table = _styled_table(title="Recent Plans")
    table.add_column("ID", justify="right")
    table.add_column("Status")
    table.add_column("What")
    for plan in plans:
        table.add_row(str(plan.plan_id), plan.status.value, plan.what)
    console.print(table)
    if not _yes_no("Review operation paths for a recent plan?", default=False):
        return
    plan_ids = {str(plan.plan_id): plan.plan_id for plan in plans}
    plan_choice = Prompt.ask(
        "Plan ID",
        choices=list(plan_ids),
        default=str(plans[0].plan_id),
        console=console,
    )
    mode = Prompt.ask(
        "Review mode",
        choices=["concise", "verbose"],
        default="concise",
        console=console,
    )
    with session(config.database_path) as connection:
        rows = list_execution_plan_rows(connection, plan_ids[plan_choice])
    _print_plan_operation_review(
        config,
        plan_ids[plan_choice],
        rows,
        limit=50,
        verbose=mode == "verbose",
    )


def _home_store_setup() -> None:
    while True:
        _print_section_row("Den / Yard Management")
        _print_option("1.", "Register or relink an archive DEN")
        _print_option("2.", "Register or relink a working YARD")
        _print_option("3.", "List archive dens")
        _print_option("4.", "List working yards")
        _print_option("5.", "Forget a den registration")
        _print_option("6.", "Forget a yard registration")
        _print_option("0.", "Back")
        choice = Prompt.ask(
            _prompt("Choose store action"),
            choices=["0", "1", "2", "3", "4", "5", "6"],
            default="1",
            console=console,
        )
        if choice == "0":
            return
        if choice == "1":
            _home_register_store(StoreKind.DEN)
            continue
        if choice == "2":
            _home_register_store(StoreKind.YARD)
            continue
        if choice == "3":
            _print_store_table(StoreKind.DEN)
            continue
        if choice == "4":
            _print_store_table(StoreKind.YARD)
            continue
        if choice == "5":
            identifier = Prompt.ask("Den name or store ID to forget", console=console).strip()
            if identifier:
                _remove_store(identifier, StoreKind.DEN)
            continue
        if choice == "6":
            identifier = Prompt.ask("Yard name or store ID to forget", console=console).strip()
            if identifier:
                _remove_store(identifier, StoreKind.YARD)


def _home_register_store(store_kind: StoreKind) -> None:
    label = "archive den" if store_kind == StoreKind.DEN else "working yard"
    _print_notice(
        f"Register/relink a {label}. If the folder already has .rawdog metadata, RAWDOG will reuse it.",
        style=STYLE_ROW_SELECTED,
    )
    name = Prompt.ask("Store name", default="primary", console=console)
    root = _choose_path(f"{store_kind.value.title()} root")
    _print_notice("Optional description only; this is for your own label, not RAWDOG behavior.")
    notes = _optional_prompt("Store description, or Enter to skip")
    _setup_store(name=name, root=root, store_kind=store_kind, notes=notes)


def _show_queue_examples() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "rawdog queue create old_drive_cleanup",
                    "rawdog queue add-sniff old_drive_cleanup /Volumes/OldDrive",
                    "rawdog queue add-score old_drive_cleanup /Volumes/OldDrive",
                    "rawdog queue add-den old_drive_cleanup /Volumes/OldDrive --dest /Volumes/Archive",
                    "rawdog queue show old_drive_cleanup",
                    "rawdog queue run old_drive_cleanup --commit",
                ]
            ),
            title="Queue Starter",
            border_style="yellow",
        )
    )


def _show_command_examples() -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    "rawdog init",
                    "rawdog yard setup primary --root ~/Pictures/RAWDOG",
                    "rawdog dens setup primary --root /Volumes/WD_BLACK/RAWDOG_Archive",
                    "rawdog fetch /Volumes/CARD --destination ~/Pictures/RAWDOG --project Wedding_Smith",
                    "rawdog den /Volumes/OldDrive --dest /Volumes/Archive --layout preserve-dates",
                    "rawdog junkyard --yard primary --den primary",
                    "rawdog backup --source ~/Pictures/RAWDOG --dest /Volumes/Archive",
                    "rawdog plans list",
                    "rawdog --help",
                ]
            ),
            title="Command Examples",
            border_style="green",
        )
    )


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
    naming: NamingConvention | None = typer.Option(
        None,
        "--naming",
        help="Source layout behavior: detect, keep-existing, ddd, or project-label.",
    ),
    collision_policy: CollisionPolicy | None = typer.Option(
        None,
        "--collision-policy",
        help="Collision behavior remembered with the profile. RAWDOG defaults to skip/review.",
    ),
    verify_after_copy: bool | None = typer.Option(
        None,
        "--verify/--no-verify",
        help="Remember verify preference.",
    ),
    detect_sessions: bool = typer.Option(False, "--detect-sessions", help="Suggest time-gap splits."),
    dry_run: bool | None = typer.Option(
        None,
        "--dry-run/--commit",
        help="Preview before copying.",
    ),
) -> None:
    """Fetch RAW and camera video files from an SD card or import source into the working library."""
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
        ensure_existing_directory(destination_root, "destination")
        ensure_import_roots(source_root, destination_root)
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    layout_analysis = analyze_source_layout(source_root)
    _print_layout_analysis(layout_analysis)

    effective_naming = naming or (
        loaded_profile.naming_convention if loaded_profile else NamingConvention.DETECT
    )
    if effective_naming == NamingConvention.DETECT:
        if layout_analysis.recommendation == "keep-existing":
            effective_naming = NamingConvention.KEEP_EXISTING
        elif layout_analysis.recommendation == "ddd":
            effective_naming = NamingConvention.DDD
    if project_name:
        effective_naming = NamingConvention.PROJECT_LABEL
    effective_collision_policy = collision_policy or (
        loaded_profile.collision_policy if loaded_profile else CollisionPolicy.SKIP
    )
    effective_verify = (
        verify_after_copy
        if verify_after_copy is not None
        else (loaded_profile.verify_after_copy if loaded_profile else True)
    )
    effective_dry_run = (
        dry_run
        if dry_run is not None
        else (loaded_profile.dry_run_default if loaded_profile else True)
    )

    project = None
    if project_name:
        with session(config.database_path) as connection:
            project = get_project_by_name(connection, project_name)
            if project is None and not effective_dry_run:
                try:
                    project = create_project(connection, ProjectCreate(name=project_name))
                except ProjectError as exc:
                    raise typer.BadParameter(str(exc)) from exc
            if not effective_dry_run:
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
                        naming_convention=effective_naming,
                        collision_policy=effective_collision_policy,
                        verify_after_copy=effective_verify,
                        dry_run_default=effective_dry_run,
                        project_id=project.project_id if project else None,
                    ),
                )
                touch_profile(connection, remembered_profile.profile_id)
            elif project is None:
                console.print(f"Project would be created on commit: {project_name}")
    elif profile_name and not effective_dry_run:
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
                    naming_convention=effective_naming,
                    collision_policy=effective_collision_policy,
                    verify_after_copy=effective_verify,
                    dry_run_default=effective_dry_run,
                ),
            )
    elif loaded_profile and not effective_dry_run:
        with session(config.database_path) as connection:
            touch_profile(connection, loaded_profile.profile_id)
    elif profile_name:
        console.print(f"Profile would be saved on commit: {profile_name}")

    console.print("Fetch is append-only and never assigns projects silently.")
    console.print(f"Source: {source_root}")
    console.print(f"Destination: {destination_root}")
    console.print(f"Mode: {(loaded_profile.organization_mode if loaded_profile else config.organization_mode).value}")
    console.print(f"Naming: {effective_naming.value}")
    console.print(f"Collision policy: {effective_collision_policy.value}")
    console.print(f"Verify after copy: {'yes' if effective_verify else 'no'}")
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
            or (project.created_at if project else datetime.now(UTC)),
            (project.preferred_folder_template if project else None) or effective_template,
        )
        console.print(f"Project: {preview_project_name}")
        console.print(f"Default project folder: {destination_folder}")
    elif earliest_capture_at:
        if effective_naming == NamingConvention.KEEP_EXISTING:
            destination_folder = destination_root
            console.print(f"Default keep-existing root: {destination_folder}")
        else:
            destination_folder = default_date_only_destination(
                destination_root,
                earliest_capture_at,
                effective_template,
            )
            console.print(f"Default DDD/date folder: {destination_folder}")
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
        memory_path = write_destination_memory(memory, dry_run=effective_dry_run)
        console.print(f"Destination memory planned: {memory_path}")
    console.print(f"Session detection: {'on' if detect_sessions else 'off'}")
    console.print(f"Dry run: {'yes' if effective_dry_run else 'no'}")
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
    loaded_profile = None
    if profile:
        with session(config.database_path) as connection:
            loaded_profile = get_profile_by_name(connection, profile)
        if not loaded_profile:
            raise typer.BadParameter(f"Unknown profile: {profile}")
    resolved_source = source or (
        loaded_profile.source_root if loaded_profile else config.working_root
    )
    resolved_destinations = (
        destinations
        or ([loaded_profile.destination_root] if loaded_profile else None)
        or ([config.archive_root] if config.archive_root else [])
    )
    try:
        if resolved_source:
            ensure_existing_directory(resolved_source, "source")
        for destination in resolved_destinations:
            ensure_existing_directory(destination, "destination")
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print("Breed is append-only. It never deletes destination files.")
    console.print(f"Project: {project_name or 'not specified'}")
    console.print(f"Source: {resolved_source or 'profile/import specific'}")
    if resolved_destinations:
        for destination in resolved_destinations:
            console.print(f"Archive destination: {destination}")
    else:
        console.print("Archive destination: profile/import specific")
    console.print(f"Profile: {profile or 'not specified'}")
    console.print(f"Dry run: {'yes' if dry_run else 'no'}")


@app.command()
def backup(
    project_name: str | None = typer.Option(None, "--project", help="Project to archive."),
    source: Path | None = typer.Option(None, "--source", "-s", help="Working project source."),
    destinations: list[Path] | None = typer.Option(None, "--dest", "-d", help="Archive destination."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Saved archive/import profile."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before archiving."),
) -> None:
    """Alias for breed: append-only backup from working library to archive storage."""
    breed(
        project_name=project_name,
        source=source,
        destinations=destinations,
        profile=profile,
        dry_run=dry_run,
    )


@app.command()
def sniff(roots: list[Path] | None = typer.Argument(None, help="Folders or volumes to inspect.")) -> None:
    """Inspect folders or configured RAWDOG roots."""
    _, config = _load_or_exit()
    sniff_roots = roots or [root for root in [config.working_root, config.archive_root] if root]
    if not sniff_roots:
        raise typer.BadParameter("No roots provided and no default roots are configured.")
    table = _styled_table(title="RAWDOG Sniff")
    table.add_column("Root")
    table.add_column("RAW/video files", justify="right")
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
    table = _styled_table(title="RAWDOG Score")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Score", str(result.score))
    table.add_row("RAW/video files", str(result.file_count))
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
    what = f"{plan.transfer_action.value} RAW/camera video files into a RAWDOG destination"
    subject = f"{plan.source_root} -> {plan.destination_root}"
    expected = (
        f"{plan.files_to_transfer} files should be at {plan.destination_folder}; "
        f"this destination is treated as the archive store for this den plan; "
        f"{skipped} already-present files skipped; {collisions} collisions held for review."
    )
    if plan.excluded_roots:
        expected += " Excluded from source scan: " + ", ".join(str(path) for path in plan.excluded_roots) + "."
    if plan.limited_to:
        expected += f" Limited preview: first {plan.limited_to} RAW/camera video files only."
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
            f"[bold bright_green on black]What we're doing:[/] [bright_white on black]{plan.what}[/]",
            f"[bold bright_cyan on black]What we're doing it to:[/] [bright_white on black]{plan.subject}[/]",
            f"[bold black on bright_yellow]What should be where when done:[/] [bright_white on black]{plan.expected_result}[/]",
            f"[bold bright_green on black]Execution:[/] [bright_white on black]{plan.execution_summary}[/]",
            f"[bold black on bright_yellow]Post audit:[/] [bright_white on black]{plan.post_audit_summary}[/]",
        ]
    )
    console.print(Panel(body, title=f"RAWDOG Plan #{plan.plan_id}", border_style="bright_green", style=STYLE_PANEL))


def _operation_manifest_path(config: RawdogConfig, plan_id: int) -> Path:
    return config.database_path.parent / "plans" / f"plan-{plan_id}-ops.csv"


def _operation_manifest_rows(rows: list[ExecutionPlanRow]) -> list[dict[str, object]]:
    return [_operation_manifest_row(row) for row in rows]


def _operation_manifest_row(row: ExecutionPlanRow) -> dict[str, object]:
    partial_path = row.destination_path.with_name(row.destination_path.name + ".partial")
    if row.status == "collision":
        return {
            "plan_id": row.plan_id,
            "row_id": row.row_id,
            "operation": "hold_collision",
            "source_path": row.source_path,
            "destination_path": row.destination_path,
            "partial_path": "",
            "size_bytes": row.size_bytes,
            "python_api": "none",
            "safety_rule": "destination exists with same name but different size; skip and review",
            "status": row.status,
            "will_write": "no",
        }
    if row.status.startswith("skip"):
        return {
            "plan_id": row.plan_id,
            "row_id": row.row_id,
            "operation": "skip",
            "source_path": row.source_path,
            "destination_path": row.destination_path,
            "partial_path": "",
            "size_bytes": row.size_bytes,
            "python_api": "none",
            "safety_rule": "already represented or excluded by plan",
            "status": row.status,
            "will_write": "no",
        }
    if row.transfer_action == DenTransferAction.MOVE:
        return {
            "plan_id": row.plan_id,
            "row_id": row.row_id,
            "operation": "same_filesystem_move",
            "source_path": row.source_path,
            "destination_path": row.destination_path,
            "partial_path": "",
            "size_bytes": row.size_bytes,
            "python_api": "Path.mkdir + os.rename",
            "safety_rule": "destination root containment; same filesystem; no overwrite",
            "status": row.status,
            "will_write": "yes" if row.status in {"plan_copy", "planned", "failed"} else "no",
        }
    return {
        "plan_id": row.plan_id,
        "row_id": row.row_id,
        "operation": "copy_with_partial",
        "source_path": row.source_path,
        "destination_path": row.destination_path,
        "partial_path": partial_path,
        "size_bytes": row.size_bytes,
        "python_api": "Path.mkdir + Python file copy/shutil.copystat + os.rename + macOS setattrlist best-effort",
        "safety_rule": "destination root containment; no overwrite; partial staging; best-effort created-date preservation",
        "status": row.status,
        "will_write": "yes" if row.status in {"plan_copy", "planned", "failed"} else "no",
    }


def _write_plan_operation_manifest(
    config: RawdogConfig,
    plan_id: int,
    rows: list[ExecutionPlanRow],
    export_path: Path | None = None,
) -> Path:
    path = export_path or _operation_manifest_path(config, plan_id)
    return write_operation_manifest(path, _operation_manifest_rows(rows))


def _print_plan_operation_review(
    config: RawdogConfig,
    plan_id: int,
    rows: list[ExecutionPlanRow],
    *,
    limit: int = 20,
    export_path: Path | None = None,
    verbose: bool = False,
) -> Path:
    manifest_path = _write_plan_operation_manifest(config, plan_id, rows, export_path)
    console.print(
        Panel(
            "\n".join(
                [
                    "[bold green]No shell commands will be run.[/]",
                    "RAWDOG uses Python filesystem APIs for copy, move, mkdir, stat, and SQLite writes.",
                    f"Operation manifest: {manifest_path}",
                ]
            ),
            title="Filesystem Operation Review",
            border_style="yellow",
            style=STYLE_PANEL,
        )
    )
    _print_destination_folder_summary(rows)
    table = _styled_table(
        title=f"Plan #{plan_id} {'Verbose ' if verbose else ''}Operations Preview",
        style=STYLE_PANEL,
        row_styles=STYLE_ROWS,
        expand=True,
    )
    table.add_column("Row", justify="right", width=7, no_wrap=True)
    table.add_column("Operation", width=18)
    table.add_column("Write", justify="center", width=5, no_wrap=True)
    table.add_column("Full Paths" if verbose else "Path", overflow="fold")
    for item in _operation_manifest_rows(rows[:limit]):
        if verbose:
            details = "\n".join(
                [
                    f"API: {item['python_api']}",
                    f"Source: {item['source_path']}",
                    f"Destination: {item['destination_path']}",
                    f"Partial: {item['partial_path'] or '-'}",
                    f"Rule: {item['safety_rule']}",
                ]
            )
        else:
            details = f"{item['source_path']} -> {item['destination_path']}"
        table.add_row(
            str(item["row_id"]),
            str(item["operation"]),
            str(item["will_write"]),
            details,
        )
    console.print(table)
    if len(rows) > limit:
        _print_notice(f"Showing first {limit} of {len(rows)} operations.", style=STYLE_ROW_SELECTED)
    return manifest_path


def _print_destination_folder_summary(rows: list[ExecutionPlanRow], *, limit: int = 10) -> None:
    counts: dict[Path, int] = {}
    bytes_by_folder: dict[Path, int] = {}
    for row in rows:
        if row.status not in {"plan_copy", "planned", "failed"}:
            continue
        folder = row.destination_path.parent
        counts[folder] = counts.get(folder, 0) + 1
        bytes_by_folder[folder] = bytes_by_folder.get(folder, 0) + row.size_bytes
    if not counts:
        return
    table = _styled_table(title=f"Top {min(limit, len(counts))} Destination Folders", expand=True)
    table.add_column("Files", justify="right", width=7)
    table.add_column("GB", justify="right", width=8)
    table.add_column("Folder", overflow="fold")
    for folder, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]:
        table.add_row(str(count), f"{bytes_by_folder[folder] / 1_000_000_000:.2f}", str(folder))
    console.print(table)


def _prompt_run_reviewed_plan(config: RawdogConfig, plan_id: int) -> None:
    if not sys.stdin.isatty():
        _print_notice(f"Next: run `rawdog plans run {plan_id}` to execute this reviewed plan.", style=STYLE_ROW_SELECTED)
        return
    choice = Prompt.ask(
        _prompt(f"Next for plan #{plan_id}: r = run, p = pause"),
        choices=["r", "p"],
        default="p",
        console=console,
    )
    if choice == "r":
        _confirm_and_execute_plan(config, plan_id, action="Run", review_already_shown=True)
    else:
        _print_notice(f"Plan #{plan_id} left paused.")


def _prompt_dry_run_plan_next(config: RawdogConfig, plan_id: int) -> None:
    if not sys.stdin.isatty():
        _print_notice(f"Next: run `rawdog plans ops {plan_id}` to inspect paths.", style=STYLE_ROW_SELECTED)
        return
    while True:
        choice = Prompt.ask(
            _prompt(f"Next for dry-run plan #{plan_id}: c = concise paths, v = verbose, r = run, p = pause"),
            choices=["c", "v", "r", "p"],
            default="c",
            console=console,
        )
        if choice in {"c", "v"}:
            with session(config.database_path) as connection:
                rows = list_execution_plan_rows(connection, plan_id)
            _print_plan_operation_review(config, plan_id, rows, limit=50, verbose=choice == "v")
            continue
        if choice == "r":
            _confirm_and_execute_plan(config, plan_id, action="Run")
            return
        _print_notice(f"Plan #{plan_id} left paused. Review later with `rawdog plans ops {plan_id}`.")
        return


def _confirm_and_execute_plan(
    config: RawdogConfig,
    plan_id: int,
    *,
    action: str = "Run",
    review_already_shown: bool = False,
) -> None:
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    if plan.status == ExecutionPlanStatus.DONE:
        console.print("Plan is already done.")
        return
    if not review_already_shown:
        _print_plan_operation_review(config, plan_id, rows)
    commit_phrase = f"COMMIT PLAN {plan_id}"
    _print_full_row(
        [
            ("WRITE ACTION: ", STYLE_WARN),
            (f"type {commit_phrase} to execute this plan", STYLE_WARN),
        ],
        style=STYLE_WARN,
    )
    _print_full_row(
        [("Anything else leaves the plan paused.", STYLE_ROW_SELECTED)],
        style=STYLE_ROW_SELECTED,
    )
    confirmed = Prompt.ask(
        _prompt(f"{action} this execution plan"),
        default="no",
        console=console,
    )
    if confirmed != commit_phrase:
        console.print("Plan not executed.")
        return
    finished = _execute_persisted_plan(config, plan_id)
    _print_execution_plan_start(finished)


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
    try:
        begin_active_run(config.database_path, plan_id=plan_id, what=plan.what)
    except ActiveRunError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        return _execute_persisted_plan_unlocked(config, plan, rows)
    finally:
        finish_active_run(config.database_path, plan_id=plan_id)


def _execute_persisted_plan_unlocked(
    config: RawdogConfig,
    plan: ExecutionPlan,
    rows: list[ExecutionPlanRow],
) -> ExecutionPlan:
    plan_id = plan.plan_id
    with session(config.database_path) as connection:
        mark_execution_plan_started(connection, plan_id)

    transferred = 0
    skipped = 0
    review = 0
    failed = 0
    review_rows: list[ExecutionPlanRow] = []
    failed_rows: list[ExecutionPlanRow] = []
    copy_bytes_total = sum(
        row.size_bytes
        for row in rows
        if row.status in {"plan_copy", "planned", "failed"}
        and row.transfer_action == DenTransferAction.COPY
    )
    execution_started_at = datetime.now(UTC)
    progress_started_at = monotonic()
    console.print(
        Panel(
            "\n".join(
                [
                    f"Rows: {len(rows)}",
                    f"Started: {execution_started_at.isoformat()}",
                    f"Copy bytes queued: {_format_bytes(copy_bytes_total)}",
                    "Copy ETA is based on actual copied bytes in this execution session; skipped rows do not improve the ETA.",
                ]
            ),
            title=f"Executing Plan #{plan_id}",
            border_style="bright_green",
            style=STYLE_PANEL,
        )
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold bright_green on black]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[bright_white on black]{task.fields[status]}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        file_task = progress.add_task("Files", total=len(rows), status="starting")
        byte_task = progress.add_task(
            "Copy bytes",
            total=copy_bytes_total or 1,
            status=_format_copy_progress(0, copy_bytes_total, progress_started_at),
        )
        bytes_copied_total = 0
        for row in rows:
            progress.update(
                file_task,
                status=(
                    f"{transferred} copied / {skipped} skipped / {failed} failed - "
                    f"{row.source_path.name} -> {row.destination_path.parent}"
                ),
            )
            row_bytes_advanced = 0

            def advance_bytes(amount: int) -> None:
                nonlocal bytes_copied_total, row_bytes_advanced
                row_bytes_advanced += amount
                bytes_copied_total += amount
                progress.advance(byte_task, amount)
                progress.update(
                    byte_task,
                    status=_format_copy_progress(
                        bytes_copied_total,
                        copy_bytes_total,
                        progress_started_at,
                    ),
                )

            if row.status not in {"plan_copy", "planned", "failed"}:
                audit_status = _audit_execution_row(row, row.status)
                if audit_status.startswith("needs") or audit_status.endswith("missing"):
                    review += 1
                    review_rows.append(row)
                if row.status.startswith("skip"):
                    skipped += 1
                with session(config.database_path) as connection:
                    if audit_status == "destination_verified":
                        store = find_store_for_path(connection, row.destination_path, StoreKind.DEN)
                        if store:
                            record_store_file(
                                store,
                                store_path=row.destination_path,
                                original_source_path=row.source_path,
                                size_bytes=row.size_bytes,
                                execution_plan_id=plan_id,
                                execution_row_id=row.row_id,
                            )
                    update_execution_plan_row(
                        connection,
                        row.row_id,
                        status=row.status,
                        audit_status=audit_status,
                    )
                progress.advance(file_task, 1)
                continue
            try:
                if plan.destination_root is None:
                    raise SafetyError("execution plan is missing destination root")
                if (
                    row.transfer_action == DenTransferAction.MOVE
                    and not row.source_path.exists()
                    and row.destination_path.exists()
                    and row.destination_path.stat().st_size == row.size_bytes
                ):
                    status = "moved"
                else:
                    status = (
                        append_only_move(row.source_path, row.destination_path, plan.destination_root)
                        if row.transfer_action == DenTransferAction.MOVE
                        else append_only_copy(
                            row.source_path,
                            row.destination_path,
                            plan.destination_root,
                            progress_callback=advance_bytes,
                        )
                    )
                audit_status = _audit_execution_row(row, status)
                if status in {"copied", "moved"}:
                    transferred += 1
                elif status.startswith("skipped"):
                    skipped += 1
                if audit_status.startswith("needs") or audit_status.endswith("missing"):
                    review += 1
                    review_rows.append(row)
                with session(config.database_path) as connection:
                    if audit_status == "destination_verified":
                        store = find_store_for_path(connection, row.destination_path, StoreKind.DEN)
                        if store:
                            record_store_file(
                                store,
                                store_path=row.destination_path,
                                original_source_path=row.source_path,
                                size_bytes=row.size_bytes,
                                execution_plan_id=plan_id,
                                execution_row_id=row.row_id,
                            )
                    update_execution_plan_row(
                        connection,
                        row.row_id,
                        status=status,
                        audit_status=audit_status,
                    )
            except Exception as exc:
                failed += 1
                failed_rows.append(row)
                with session(config.database_path) as connection:
                    update_execution_plan_row(
                        connection,
                        row.row_id,
                        status="failed",
                        audit_status="not_audited",
                        error=str(exc),
                    )
            finally:
                progress.advance(file_task, 1)
                progress.update(
                    file_task,
                    status=f"{transferred} copied / {skipped} skipped / {failed} failed",
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
    _print_ai_review_prompt(
        "rows needing manual review",
        [row.destination_path for row in review_rows],
        "do not move or clean these rows automatically; inspect the listed destination paths and "
        "compare against the matching source files first.",
        plan_id=plan_id,
        rows=review_rows,
    )
    _print_ai_review_prompt(
        "failed transfer rows",
        [row.destination_path for row in failed_rows],
        "pause execution, check mount state/free space/permissions, then resume the persisted plan "
        "only after the storage issue is understood.",
        plan_id=plan_id,
        rows=failed_rows,
    )
    return finished


@app.command()
def den(
    source: Path | None = typer.Argument(None, help="Messy source folder or volume to consolidate."),
    destination: Path | None = typer.Option(None, "--dest", "-d", help="Destination root."),
    project_name: str | None = typer.Option(None, "--project", help="Optional project folder name."),
    workflow_name: str | None = typer.Option(None, "--workflow", "-w", help="Save or reuse workflow name."),
    layout: DenLayoutMode = typer.Option(DenLayoutMode.PRESERVE, "--layout", help="Destination layout."),
    action: DenTransferAction = typer.Option(
        DenTransferAction.COPY,
        "--action",
        "--transfer-action",
        help="copy or move.",
    ),
    template: str | None = typer.Option(None, "--template", help="Folder template override."),
    group_by: DateGroupMode | None = typer.Option(
        None,
        "--group-by",
        help="Generated date grouping for date/project-dates layouts: month or day.",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Only include files captured on or after this date.",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Only include files captured on or before this date.",
    ),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Limit the planning scan for review."),
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
    try:
        start_date_value = _parse_cli_date(start_date) if start_date else None
        end_date_value = _parse_cli_date(end_date) if end_date else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if start_date_value and end_date_value and start_date_value > end_date_value:
        raise typer.BadParameter("--start-date must be before or equal to --end-date.")
    source_root = parse_user_path(str(source_value))
    destination_root = parse_user_path(str(destination_value))
    effective_layout = loaded_workflow.layout_mode if loaded_workflow and not source else layout
    effective_action = loaded_workflow.transfer_action if loaded_workflow and not source else action
    destination_inside_source = _destination_inside_source(source_root, destination_root)
    if destination_inside_source and effective_action == DenTransferAction.MOVE:
        raise typer.BadParameter(
            "Whole-source move into a child destination is not allowed. "
            "Use --action copy for a whole-drive consolidation preview, or choose a narrower old-folder source."
        )
    exclude_roots = [destination_root] if destination_inside_source else []
    try:
        ensure_existing_directory(source_root, "source")
        ensure_existing_directory(destination_root, "destination")
        ensure_consolidation_roots(
            source_root,
            destination_root,
            allow_destination_inside_source=destination_inside_source,
        )
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if effective_action == DenTransferAction.MOVE:
        try:
            ensure_same_filesystem(source_root, destination_root)
        except SafetyError as exc:
            raise typer.BadParameter(str(exc)) from exc
    with session(config.database_path) as connection:
        den_store = find_store_for_path(connection, destination_root, StoreKind.DEN)
    if den_store:
        console.print(
            "[bold green]Established den:[/] "
            f"{den_store.name} ({den_store.store_id}) at {den_store.root_path}"
        )
    else:
        console.print(
            "[bold yellow]Unregistered den destination:[/] "
            "run `rawdog dens setup --root DESTINATION` to give this archive a portable store catalog."
        )
    effective_template = (
        template
        or _den_template_for_grouping(effective_layout, group_by)
        or (loaded_workflow.folder_template if loaded_workflow else None)
    )
    effective_template = effective_template or (
        "YYYY/PROJECT-YYYYMM"
        if effective_layout == DenLayoutMode.PROJECT_DATES
        else (
            config.project_folder_template
            if effective_layout == DenLayoutMode.PROJECT or project_name
            else config.date_folder_template
        )
    )
    layout_analysis = analyze_source_layout(source_root, exclude_roots=exclude_roots, limit=limit)
    _print_layout_analysis(layout_analysis)
    if effective_layout in {DenLayoutMode.PROJECT, DenLayoutMode.PROJECT_DATES}:
        _print_project_scope_warning(
            source_root,
            exclude_roots,
            start_date=start_date_value,
            end_date=end_date_value,
        )
    if exclude_roots:
        console.print(
            "[bold yellow]Destination is inside source:[/] "
            "RAWDOG will exclude the destination subtree from source inventory."
        )
        for excluded_root in exclude_roots:
            console.print(f"Excluded: {excluded_root}")
    plan = build_den_plan(
        source_root,
        destination_root,
        project_name=project_name,
        layout_mode=effective_layout,
        transfer_action=effective_action,
        folder_template=effective_template,
        exclude_roots=exclude_roots,
        start_date=start_date_value,
        end_date=end_date_value,
        limit=limit,
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
    table = _styled_table(title="RAWDOG Den Plan")
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
        year_table = _styled_table(title="Copy Estimate")
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
    _print_big_job_warning(plan, source_root, destination_root, effective_action)
    collision_paths = [row.destination_path for row in plan.rows if row.status == "collision"]
    _print_ai_review_prompt(
        "destination collisions",
        collision_paths,
        "skip these rows for now, inspect the source and destination manually, and only copy after "
        "confirming they are not conflicting originals.",
    )
    if dry_run:
        with session(config.database_path) as connection:
            rows = list_execution_plan_rows(connection, execution_plan.plan_id)
        manifest_path = _write_plan_operation_manifest(config, execution_plan.plan_id, rows)
        console.print(
            f"Plan #{execution_plan.plan_id} written to the database. "
            "Review operation paths before executing."
        )
        console.print(f"Operation manifest written: {manifest_path}")
        _prompt_dry_run_plan_next(config, execution_plan.plan_id)
        return
    _confirm_and_execute_plan(config, execution_plan.plan_id, action="Execute")
    with session(config.database_path) as connection:
        finished_plan = get_execution_plan(connection, execution_plan.plan_id)
    if finished_plan is None or finished_plan.status != ExecutionPlanStatus.DONE:
        return
    if workflow_name:
        with session(config.database_path) as connection:
            workflow = get_workflow_by_name(connection, workflow_name)
            if workflow:
                mark_workflow_committed(connection, workflow.workflow_id)


@app.command()
def status() -> None:
    """Show configured paths, projects, and archive state summary."""
    _, config = _load_or_exit()
    table = _styled_table(title="RAWDOG Status")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Organization mode", config.organization_mode.value)
    table.add_row("Working root", str(config.working_root or "profile/import specific"))
    table.add_row("Archive root", str(config.archive_root or "profile/import specific"))
    table.add_row("Database", str(config.database_path))
    with session(config.database_path) as connection:
        projects = list_projects(connection)
        profiles = list_profiles(connection)
        stores = list_stores(connection)
        latest_plans = list_execution_plans(connection, limit=3)
    active_run = _read_active_run_or_none(config)
    table.add_row("Projects", str(len(projects)))
    table.add_row("Profiles", str(len(profiles)))
    table.add_row("Known stores", str(len(stores)))
    if active_run:
        state = "running" if active_run_is_alive(active_run) else "stale"
        table.add_row(
            "Active run",
            f"plan #{active_run.plan_id} ({state}, pid {active_run.pid})",
        )
    console.print(table)
    if active_run:
        _print_active_run_notice(config)
    if latest_plans:
        plan_table = _styled_table(title="Recent Execution Plans")
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


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def wings(
    ctx: typer.Context,
    pid: int | None = typer.Option(None, "--pid", "-p", help="Keep the Mac awake until this PID exits."),
) -> None:
    """Run RAWDOG under macOS caffeinate, or attach to the active RAWDOG run."""
    if sys.platform != "darwin":
        raise typer.BadParameter("rawdog wings uses macOS caffeinate and is only available on macOS.")
    caffeinate_path = shutil.which("caffeinate")
    if caffeinate_path is None:
        raise typer.BadParameter("macOS caffeinate command was not found.")
    args = list(ctx.args)
    if pid is not None and args:
        raise typer.BadParameter("Use either --pid or a RAWDOG command, not both.")
    if pid is None and not args:
        _, config = _load_or_exit()
        active_run = read_active_run(config.database_path)
        if active_run is None:
            raise typer.BadParameter(
                "No active RAWDOG run found. Use `rawdog wings plans resume 10` "
                "or `rawdog wings --pid PID`."
            )
        if not active_run_is_alive(active_run):
            raise typer.BadParameter(
                f"Active marker for plan #{active_run.plan_id} is stale. "
                "If no RAWDOG copy/move is running, clear it with `rawdog plans active-clear --force`."
            )
        pid = active_run.pid
    command = _build_wings_command(
        caffeinate_path=caffeinate_path,
        rawdog_executable=sys.argv[0],
        args=args,
        pid=pid,
    )
    detail = f"PID {pid}" if pid is not None else "rawdog " + " ".join(args)
    console.print(
        Panel(
            "\n".join(
                [
                    "Keeping the Mac awake with caffeinate.",
                    f"Target: {detail}",
                    "Screen lock is OK. Do not sleep, log out, unplug drives, or disconnect docks.",
                ]
            ),
            title="RAWDOG Wings",
            border_style="bright_green",
            style=STYLE_PANEL,
        )
    )
    raise typer.Exit(subprocess.run(command).returncode)


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


@app.command()
def junkyard(
    yard_name: str | None = typer.Option(None, "--yard", help="Limit report to one registered yard."),
    den_name: str | None = typer.Option(None, "--den", help="Limit report to one registered den."),
    before: str | None = typer.Option(None, "--before", help="Only show yard files modified before YYYY-MM-DD."),
    validate_first: bool = typer.Option(
        False,
        "--validate-first",
        "--verify-disk",
        help="Also check matched den files on disk by path and size before reporting them.",
    ),
    hash_check: bool = typer.Option(
        False,
        "--hash-check",
        help="Meticulous mode: SHA-256 hash yard and den files before reporting cleanup candidates.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm long hash-check work in non-interactive runs."),
) -> None:
    """Report working files that appear safe to scrap. This never deletes files."""
    _, config = _load_or_exit()
    before_dt = datetime.fromisoformat(before).replace(tzinfo=UTC) if before else None
    with session(config.database_path) as connection:
        if yard_name:
            yard_store = get_store_by_name(connection, yard_name, StoreKind.YARD)
            if yard_store is None:
                raise typer.BadParameter(f"Unknown yard: {yard_name}")
            yards = [yard_store]
        else:
            yards = _list_configured_stores(connection, config, StoreKind.YARD)
        if den_name:
            den_store = get_store_by_name(connection, den_name, StoreKind.DEN)
            if den_store is None:
                raise typer.BadParameter(f"Unknown den: {den_name}")
            dens = [den_store]
        else:
            dens = _list_configured_stores(connection, config, StoreKind.DEN)
    den_by_source: dict[Path, object] = {}
    for den_store in dens:
        den_by_source.update(list_store_files_by_original_source(den_store))
    validate_first = validate_first or hash_check
    if hash_check:
        _print_notice(
            "Hash check reads both yard and den files. This is meticulous and may take a long time.",
            style=STYLE_ROW_SELECTED,
        )
        if not yes and sys.stdin.isatty() and not _yes_no("Continue with SHA-256 hash checking?", default=False):
            console.print("Hash check cancelled.")
            return
    table = _styled_table(title="RAWDOG Junkyard Report", style=STYLE_PANEL, row_styles=STYLE_ROWS, expand=True)
    table.add_column("Yard File")
    table.add_column("Matched Den File")
    table.add_column("Bytes", justify="right")
    matches: list[tuple[Path, Path, int]] = []
    for yard_store in yards:
        for item in scan_raw_files(yard_store.root_path):
            if before_dt and datetime.fromtimestamp(item.path.stat().st_mtime, tz=UTC) >= before_dt:
                continue
            record = den_by_source.get(item.path.expanduser().resolve())
            if record is None or record.size_bytes != item.size_bytes:
                continue
            matches.append((item.path, record.store_path, item.size_bytes))
    candidates = 0
    missing_or_changed = 0
    hash_mismatches = 0
    total_bytes = 0
    total_hash_bytes = sum(size_bytes * 2 for _, _, size_bytes in matches)
    progress = None
    hash_task = None
    hashed_bytes = 0
    if hash_check:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold bright_green on black]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[bright_white on black]{task.fields[status]}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        progress.start()
        hash_task = progress.add_task("Hash check", total=total_hash_bytes or 1, status=_format_bytes(0))
    try:
        for yard_path, den_path, size_bytes in matches:
            if validate_first:
                try:
                    den_stat = den_path.stat()
                except OSError:
                    missing_or_changed += 1
                    continue
                if den_stat.st_size != size_bytes:
                    missing_or_changed += 1
                    continue
            if hash_check:
                try:
                    matched = verify_same_bytes(yard_path, den_path)
                except OSError:
                    missing_or_changed += 1
                    continue
                finally:
                    hashed_bytes += size_bytes * 2
                    if progress and hash_task is not None:
                        progress.update(hash_task, completed=hashed_bytes, status=_format_bytes(hashed_bytes))
                if not matched:
                    hash_mismatches += 1
                    continue
            candidates += 1
            total_bytes += size_bytes
            table.add_row(str(yard_path), str(den_path), str(size_bytes))
    finally:
        if progress:
            progress.stop()
    console.print(table)
    if hash_check:
        _print_notice(
            f"Report only: {candidates} working files ({total_bytes / 1_000_000_000:.2f} GB) "
            "appear den-recorded and matched by SHA-256. "
            f"{missing_or_changed} catalog matches were missing or size-changed on disk; "
            f"{hash_mismatches} had hash mismatches. RAWDOG did not delete or move anything.",
            style=STYLE_ROW_SELECTED,
        )
    elif validate_first:
        _print_notice(
            f"Report only: {candidates} working files ({total_bytes / 1_000_000_000:.2f} GB) "
            "appear den-recorded and were validated on disk by path + size. "
            f"{missing_or_changed} catalog matches were missing or size-changed on disk. "
            "RAWDOG did not delete or move anything.",
            style=STYLE_ROW_SELECTED,
        )
    else:
        _print_notice(
            f"Report only: {candidates} working files ({total_bytes / 1_000_000_000:.2f} GB) "
            "match the den catalog by original source path and size. "
            "This is not a fresh disk/hash validation. Run with --validate-first for path + size checks, "
            "or --hash-check for SHA-256 matching. "
            "RAWDOG did not delete or move anything.",
            style=STYLE_ROW_SELECTED,
        )


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

dens_app = typer.Typer(help="Manage RAWDOG archive stores.")
app.add_typer(dens_app, name="dens")

yard_app = typer.Typer(help="Manage RAWDOG working stores.")
app.add_typer(yard_app, name="yard")


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
    table = _styled_table(title="RAWDOG Projects")
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


def _setup_store(name: str, root: Path, store_kind: StoreKind, notes: str | None = None) -> None:
    _, config = _load_or_exit()
    root_path = parse_user_path(str(root))
    try:
        ensure_existing_directory(root_path, f"{store_kind.value} root")
    except SafetyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with session(config.database_path) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name=name, root_path=root_path, store_kind=store_kind, notes=notes),
        )
        store = mark_store_used(connection, store.store_id)
    if store.name != name:
        _print_notice(
            f"Store name '{name}' was already used for another {store_kind.value}; registered this path as '{store.name}'.",
            style=STYLE_ROW_SELECTED,
        )
    console.print(
        Panel(
            "\n".join(
                [
                    f"[bold yellow]Name:[/] [bold green]{store.name}[/]",
                    f"[bold yellow]Type:[/] [bold green]{store.store_kind.value}[/]",
                    f"[bold yellow]Root:[/] [bold cyan]{store.root_path}[/]",
                    f"[bold yellow]Store ID:[/] [bold green]{store.store_id}[/]",
                    f"[bold yellow]Portable metadata:[/] [bold cyan]{store.root_path / '.rawdog'}[/]",
                    "[bold green]App Support remembers this store path, and the store carries its own catalog.[/]",
                ]
            ),
            title=f"RAWDOG {store.store_kind.value.title()} Store",
            border_style="green",
            style=STYLE_PANEL,
            expand=True,
        )
    )
    console.print(f"[bold green]Registered {store.store_kind.value} store:[/] {store.name} -> {store.root_path}")


def _remove_store(identifier: str, store_kind: StoreKind, *, yes: bool = False) -> None:
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        existing = get_store_by_name(connection, identifier, store_kind)
        if existing is None:
            rows = [store for store in list_stores(connection, store_kind) if store.store_id == identifier]
            existing = rows[0] if rows else None
        if existing is None:
            raise typer.BadParameter(f"No {store_kind.value} store named or identified by {identifier!r}.")
        _print_notice(
            f"Forget {store_kind.value} store '{existing.name}' at {existing.root_path} from App Support memory only.",
            style=STYLE_ROW_SELECTED,
        )
        _print_notice("This does not delete media files or the portable .rawdog catalog.")
        if not yes and not _yes_no("Forget this store registration?", default=False):
            _print_notice("Store registration left unchanged.", style=STYLE_MUTED)
            return
        removed = remove_store_registration(connection, existing.store_id, store_kind)
    if removed:
        _print_notice(f"Forgot {removed.store_kind.value} store: {removed.name} -> {removed.root_path}", style=STYLE_SAFE)


def _print_store_table(store_kind: StoreKind) -> None:
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        stores = _list_configured_stores(connection, config, store_kind)
    title = "RAWDOG Dens" if store_kind == StoreKind.DEN else "RAWDOG Yards"
    table = _styled_table(title=title, style=STYLE_PANEL, row_styles=STYLE_ROWS, expand=True)
    table.add_column("Store ID")
    table.add_column("Name")
    table.add_column("Root")
    table.add_column("Available")
    table.add_column("Last Used")
    table.add_column("Uses", justify="right")
    table.add_column("Updated")
    for store in stores:
        table.add_row(
            store.store_id,
            store.name,
            str(store.root_path),
            "yes" if store.root_path.exists() else "missing",
            store.last_used_at.isoformat() if store.last_used_at else "never",
            str(store.use_count),
            store.updated_at.isoformat(),
        )
    console.print(table)


@dens_app.command("setup")
def den_store_setup(
    name: str = typer.Argument("primary", help="Den store name."),
    root: Path | None = typer.Option(None, "--root", "-r", help="Archive root to register as a den."),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Create or update a den archive store."""
    root_path = root or _choose_path("Den archive root")
    _setup_store(name=name, root=root_path, store_kind=StoreKind.DEN, notes=notes)


@dens_app.command("list")
def den_store_list() -> None:
    """List den archive stores."""
    _print_store_table(StoreKind.DEN)


@dens_app.command("remove")
def den_store_remove(
    identifier: str = typer.Argument(..., help="Den store name or store ID to forget from App Support."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Forget a den registration without deleting files or portable metadata."""
    _remove_store(identifier, StoreKind.DEN, yes=yes)


@yard_app.command("setup")
def yard_setup(
    name: str = typer.Argument("primary", help="Yard store name."),
    root: Path | None = typer.Option(None, "--root", "-r", help="Working root to register as a yard."),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Create or update a yard working store."""
    root_path = root or _choose_path("Yard working root")
    _setup_store(name=name, root=root_path, store_kind=StoreKind.YARD, notes=notes)


@yard_app.command("list")
def yard_list() -> None:
    """List yard working stores."""
    _print_store_table(StoreKind.YARD)


@yard_app.command("remove")
def yard_remove(
    identifier: str = typer.Argument(..., help="Yard store name or store ID to forget from App Support."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Forget a yard registration without deleting files or portable metadata."""
    _remove_store(identifier, StoreKind.YARD, yes=yes)


@profiles_app.command("create")
def profile_create(
    name: str = typer.Argument(...),
    source: Path | None = typer.Option(None, "--source", "-s"),
    destination: Path | None = typer.Option(None, "--destination", "-d"),
    mode: OrganizationMode = typer.Option(OrganizationMode.PROJECT, "--mode"),
    template: str = typer.Option("YYYY/YYYYMMDD_PROJECT", "--template"),
    naming: NamingConvention = typer.Option(NamingConvention.DETECT, "--naming"),
    collision_policy: CollisionPolicy = typer.Option(CollisionPolicy.SKIP, "--collision-policy"),
    verify_after_copy: bool = typer.Option(True, "--verify/--no-verify"),
    dry_run_default: bool = typer.Option(True, "--dry-run-default/--commit-default"),
    exclude_patterns: list[str] = typer.Option(None, "--exclude"),
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
                naming_convention=naming,
                collision_policy=collision_policy,
                verify_after_copy=verify_after_copy,
                dry_run_default=dry_run_default,
                exclude_patterns=exclude_patterns or [],
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
    table = _styled_table(title="RAWDOG Import Profiles")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Naming")
    table.add_column("Collision")
    table.add_column("Template")
    for profile in profiles:
        table.add_row(
            str(profile.profile_id),
            profile.name,
            str(profile.source_root),
            str(profile.destination_root),
            profile.naming_convention.value,
            profile.collision_policy.value,
            profile.folder_template,
        )
    console.print(table)


@workflows_app.command("list")
def workflow_list() -> None:
    """List reusable consolidation workflows."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        workflows = list_workflows(connection)
    table = _styled_table(title="RAWDOG Consolidation Workflows")
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
    table = _styled_table(title="RAWDOG Execution Plans")
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


@plans_app.command("prune")
def plans_prune(
    keep: int = typer.Option(20, "--keep", min=0, help="Keep this many newest plans."),
    before: str | None = typer.Option(None, "--before", help="Only prune plans updated before YYYY-MM-DD."),
    include_done: bool = typer.Option(False, "--include-done", help="Also allow completed plans to be pruned."),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Preview before pruning."),
) -> None:
    """Prune old persisted plans. Conservative by default: planned dry-runs only."""
    _, config = _load_or_exit()
    try:
        before_dt = (
            datetime.combine(_parse_cli_date(before), datetime.min.time(), tzinfo=UTC)
            if before
            else None
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with session(config.database_path) as connection:
        plans = list_execution_plans_for_prune(
            connection,
            keep=keep,
            before=before_dt,
            include_done=include_done,
        )
    table = _styled_table(title="RAWDOG Plans Prune Preview")
    table.add_column("ID", justify="right")
    table.add_column("Status")
    table.add_column("Updated")
    table.add_column("What")
    for plan in plans:
        table.add_row(str(plan.plan_id), plan.status.value, plan.updated_at.isoformat(), plan.what)
    console.print(table)
    console.print(
        "[bold yellow]Safety:[/] prune never removes started, failed, or needs-review plans. "
        "By default it removes only planned dry-run plans."
    )
    if not plans:
        console.print("No prunable plans found.")
        return
    if dry_run:
        console.print("Dry run only. Re-run with --commit to prune these plans.")
        return
    confirmed = Prompt.ask(
        "[bold red]Delete these plan records and operation manifests? Type PRUNE PLANS[/]",
        default="no",
        console=console,
    )
    if confirmed != "PRUNE PLANS":
        console.print("Plans not pruned.")
        return
    removed_manifests = 0
    with session(config.database_path) as connection:
        for plan in plans:
            delete_execution_plan(connection, plan.plan_id)
            manifest = _operation_manifest_path(config, plan.plan_id)
            if manifest.exists():
                manifest.unlink()
                removed_manifests += 1
    console.print(f"Pruned {len(plans)} plans and {removed_manifests} operation manifests.")


@plans_app.command("show")
def plans_show(
    plan_id: int = typer.Argument(...),
    ops: bool = typer.Option(False, "--ops", help="Also show filesystem operation preview."),
) -> None:
    """Show one persisted execution plan and its row summary."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    _print_execution_plan_start(plan)
    table = _styled_table(title=f"Plan #{plan.plan_id} Rows")
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
    review_paths = [
        row.destination_path
        for row in rows
        if _needs_plan_review(row)
    ]
    review_rows = [row for row in rows if _needs_plan_review(row)]
    _print_ai_review_prompt(
        "persisted plan review items",
        review_paths,
        "keep the plan paused, inspect these paths, and only resume after you understand why RAWDOG "
        "held or failed these rows.",
        plan_id=plan_id,
        rows=review_rows,
    )
    if ops:
        _print_plan_operation_review(config, plan_id, rows)


def _skip_reason(row: ExecutionPlanRow) -> str:
    if row.status in {"skipped_existing_same_name_size", "skip_existing_same_name_size"}:
        return "destination already has same name and size"
    if row.status == "skipped_existing_partial":
        return "destination has a pre-existing .partial that needs review"
    if row.status == "skipped_collision" or row.status == "collision":
        return "destination has same name but different size"
    if row.status.startswith("skip"):
        return "planned skip"
    return row.audit_status or "skipped"


def _print_active_run_notice(config: RawdogConfig) -> None:
    run = _read_active_run_or_none(config)
    if run is None:
        _print_notice("No active RAWDOG plan marker found.", style=STYLE_SAFE)
        return
    state = "running" if active_run_is_alive(run) else "stale"
    lines = [
        f"Plan: #{run.plan_id}",
        f"PID: {run.pid}",
        f"State: {state}",
        f"Started: {run.started_at.isoformat()}",
        f"What: {run.what}",
        f"Marker: {active_run_path(config.database_path)}",
    ]
    if state == "running":
        lines.append("Avoid brew upgrades, drive disconnects, or starting another plan until this finishes.")
    else:
        lines.append("If no RAWDOG copy/move is running, clear this with: rawdog plans active-clear --force")
    console.print(Panel("\n".join(lines), title="Active RAWDOG Run", border_style="yellow", style=STYLE_PANEL))


def _read_active_run_or_none(config: RawdogConfig):
    try:
        return read_active_run(config.database_path)
    except (OSError, ValueError, KeyError):
        _print_notice(
            f"Active-run marker is unreadable: {active_run_path(config.database_path)}",
            style=STYLE_WARN,
        )
        _print_notice("If no RAWDOG copy/move is running, clear it with: rawdog plans active-clear --force")
        return None


@plans_app.command("active")
def plans_active() -> None:
    """Show the active plan execution marker, if any."""
    _, config = _load_or_exit()
    _print_active_run_notice(config)


@plans_app.command("active-clear")
def plans_active_clear(force: bool = typer.Option(False, "--force", help="Clear a stale active-run marker.")) -> None:
    """Clear a stale active plan marker after confirming no RAWDOG copy/move is running."""
    _, config = _load_or_exit()
    try:
        run = read_active_run(config.database_path)
    except (OSError, ValueError, KeyError):
        if not force:
            raise typer.BadParameter("Active-run marker is unreadable. Use --force to clear it.") from None
        removed = clear_active_run(config.database_path)
        if removed:
            _print_notice("Cleared unreadable active-run marker.", style=STYLE_WARN)
        return
    if run is None:
        _print_notice("No active RAWDOG plan marker found.", style=STYLE_SAFE)
        return
    if active_run_is_alive(run) and not force:
        raise typer.BadParameter(
            f"Plan #{run.plan_id} still appears to be running as PID {run.pid}. "
            "Use --force only if you are certain that process is not an active RAWDOG copy/move."
        )
    if not force:
        raise typer.BadParameter("Use --force to clear the active-run marker.")
    removed = clear_active_run(config.database_path)
    if removed:
        _print_notice(f"Cleared active-run marker for plan #{run.plan_id}.", style=STYLE_WARN)


@plans_app.command("skipped")
def plans_skipped(
    plan_id: int = typer.Argument(...),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Skipped rows to show in terminal."),
    export: Path | None = typer.Option(None, "--export", "-o", help="Optional CSV export path for skipped rows."),
) -> None:
    """Show skipped rows for a persisted execution plan."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    skipped_rows = [
        row
        for row in rows
        if row.status.startswith("skip") or row.status.startswith("skipped") or row.status == "collision"
    ]
    _print_execution_plan_start(plan)
    if export:
        export_path = write_operation_manifest(export, _operation_manifest_rows(skipped_rows))
        console.print(f"Skipped row export written: {export_path}")
    table = _styled_table(title=f"Plan #{plan_id} Skipped Rows")
    table.add_column("Row", justify="right")
    table.add_column("Status")
    table.add_column("Reason")
    table.add_column("Source")
    table.add_column("Destination")
    for row in skipped_rows[:limit]:
        table.add_row(
            str(row.row_id),
            row.status,
            _skip_reason(row),
            str(row.source_path),
            str(row.destination_path),
        )
    console.print(table)
    if len(skipped_rows) > limit:
        _print_notice(f"Showing first {limit} of {len(skipped_rows)} skipped rows.", style=STYLE_ROW_SELECTED)
    if not skipped_rows:
        _print_notice("No skipped rows found for this plan.", style=STYLE_SAFE)


def _print_plan_review_rows(plan_id: int, rows: list[ExecutionPlanRow], *, start: int, page_size: int) -> None:
    page_rows = rows[start : start + page_size]
    table = _styled_table(
        title=f"Plan #{plan_id} Review Rows {start + 1}-{start + len(page_rows)} of {len(rows)}",
        style=STYLE_PANEL,
        row_styles=STYLE_ROWS,
        expand=True,
    )
    table.add_column("Row", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Audit", no_wrap=True)
    table.add_column("Reason", overflow="fold")
    table.add_column("Source", overflow="fold")
    table.add_column("Destination", overflow="fold")
    table.add_column("Error", overflow="fold")
    for row in page_rows:
        table.add_row(
            str(row.row_id),
            row.status,
            row.audit_status or "",
            _review_reason(row),
            str(row.source_path),
            str(row.destination_path),
            row.error or "",
        )
    console.print(table)


@plans_app.command("review")
def plans_review(
    plan_id: int = typer.Argument(...),
    page_size: int = typer.Option(20, "--limit", min=1, max=100, help="Rows per page."),
) -> None:
    """Interactively inspect failed, skipped, held, and review-needed rows for a plan."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    review_rows = [row for row in rows if _needs_plan_review(row)]
    _print_execution_plan_start(plan)
    if not review_rows:
        _print_notice("No failed, skipped, held, or review-needed rows found.", style=STYLE_SAFE)
        return
    offset = 0
    while True:
        _print_plan_review_rows(plan_id, review_rows, start=offset, page_size=page_size)
        next_offset = offset + page_size
        if next_offset >= len(review_rows):
            _print_notice("End of review rows.", style=STYLE_SAFE)
            return
        if not sys.stdin.isatty():
            _print_notice(
                f"Showing first {page_size} of {len(review_rows)} review rows. Re-run in a terminal to page.",
                style=STYLE_ROW_SELECTED,
            )
            return
        choice = Prompt.ask(
            _prompt("Press Enter for next page, or 0 to quit inspection"),
            default="",
            console=console,
        ).strip()
        if choice == "0":
            _print_notice("Inspection stopped.", style=STYLE_ROW_SELECTED)
            return
        offset = next_offset


@plans_app.command("ops")
def plans_ops(
    plan_id: int = typer.Argument(...),
    limit: int = typer.Option(50, "--limit", min=1, max=500, help="Rows to preview in terminal."),
    export: Path | None = typer.Option(None, "--export", "-o", help="Optional CSV export path."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show API, partial path, and safety rule details."),
) -> None:
    """Review exact Python filesystem operations for a persisted plan."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
        rows = list_execution_plan_rows(connection, plan_id)
    _print_execution_plan_start(plan)
    _print_plan_operation_review(config, plan_id, rows, limit=limit, export_path=export, verbose=verbose)
    _prompt_run_reviewed_plan(config, plan_id)


@plans_app.command("run")
def plans_run(plan_id: int = typer.Argument(...)) -> None:
    """Run a reviewed persisted copy/move execution plan."""
    _, config = _load_or_exit()
    _confirm_and_execute_plan(config, plan_id, action="Run")


@plans_app.command("resume")
def plans_resume(plan_id: int = typer.Argument(...)) -> None:
    """Resume a persisted copy/move execution plan."""
    _, config = _load_or_exit()
    with session(config.database_path) as connection:
        plan = get_execution_plan(connection, plan_id)
        if plan is None:
            raise typer.BadParameter(f"Unknown plan: {plan_id}")
    _print_execution_plan_start(plan)
    with session(config.database_path) as connection:
        rows = list_execution_plan_rows(connection, plan_id)
    _print_plan_operation_review(config, plan_id, rows)
    _confirm_and_execute_plan(config, plan_id, action="Resume", review_already_shown=True)


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
    group_by: DateGroupMode | None = typer.Option(
        None,
        "--group-by",
        help="Generated date grouping for date/project-dates layouts: month or day.",
    ),
) -> None:
    """Add a safe den step to a queue."""
    _, config = _load_or_exit()
    source_root = parse_user_path(str(source))
    destination_root = parse_user_path(str(destination))
    destination_inside_source = _destination_inside_source(source_root, destination_root)
    if destination_inside_source and action == DenTransferAction.MOVE:
        raise typer.BadParameter(
            "Whole-source move into a child destination is not allowed. "
            "Use --action copy, or choose a narrower old-folder source."
        )
    try:
        ensure_existing_directory(source_root, "source")
        ensure_existing_directory(destination_root, "destination")
        ensure_consolidation_roots(
            source_root,
            destination_root,
            allow_destination_inside_source=destination_inside_source,
        )
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
                folder_template=template or _den_template_for_grouping(layout, group_by),
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
    table = _styled_table(title="RAWDOG Plan Queues")
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
    table = _styled_table(title=f"RAWDOG Queue: {queue.name}")
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
                destination_inside_source = _destination_inside_source(
                    step.source_root,
                    step.destination_root,
                )
                if destination_inside_source and step.transfer_action == DenTransferAction.MOVE:
                    raise typer.BadParameter(
                        f"Queue step #{step.step_order} cannot move a whole source into a child destination."
                    )
                ensure_existing_directory(step.destination_root, "destination")
                ensure_consolidation_roots(
                    step.source_root,
                    step.destination_root,
                    allow_destination_inside_source=destination_inside_source,
                )
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
                "YYYY/PROJECT-YYYYMM"
                if layout_mode == DenLayoutMode.PROJECT_DATES
                else (
                    config.project_folder_template
                    if layout_mode == DenLayoutMode.PROJECT or step.project_name
                    else config.date_folder_template
                )
            )
            plan = build_den_plan(
                step.source_root,
                step.destination_root,
                project_name=step.project_name,
                layout_mode=layout_mode,
                transfer_action=transfer_action,
                folder_template=folder_template,
                exclude_roots=(
                    [step.destination_root]
                    if _destination_inside_source(step.source_root, step.destination_root)
                    else []
                ),
            )
            runnable_steps.append((step, plan))
            total_files += plan.files_to_transfer
            total_bytes += plan.bytes_to_transfer
        else:
            raise typer.BadParameter(
                f"Queue step #{step.step_order} is not safe: {step.step_kind.value}"
            )

    table = _styled_table(title=f"RAWDOG Queue Run: {queue.name}")
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
    if total_bytes >= 50_000_000_000:
        _print_notice(
            f"Long queue tip: run this through `rawdog wings queue run {name} --commit` "
            "so macOS stays awake.",
            style=STYLE_ROW_SELECTED,
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
        "[bold red]Execute this safe queue? Type yes[/]",
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
