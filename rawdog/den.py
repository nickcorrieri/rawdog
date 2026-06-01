# Author: Nicholas Corrieri

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from rawdog.copier import append_only_copy, append_only_move
from rawdog.datefolders import normalize_date_folder_parts
from rawdog.filenames import destination_path_for_filename_policy
from rawdog.inventory import InventoryItem, scan_raw_files
from rawdog.layout import is_camera_dump_part
from rawdog.metadata import capture_times
from rawdog.models import DenLayoutMode, DenTransferAction, DestinationFilenamePolicy
from rawdog.planner import (
    default_date_only_destination,
    default_project_destination,
    render_folder_template,
)


@dataclass(frozen=True)
class DenPlanRow:
    source_path: Path
    destination_path: Path
    size_bytes: int
    status: str


@dataclass(frozen=True)
class ReflowTimeShiftPlanRow:
    source_path: Path
    destination_path: Path
    original_capture_at: datetime
    shifted_capture_at: datetime
    time_shift_seconds: int
    basis: str


@dataclass(frozen=True)
class DenPlan:
    source_root: Path
    destination_root: Path
    destination_folder: Path
    rows: list[DenPlanRow]
    transfer_action: DenTransferAction = DenTransferAction.COPY
    excluded_roots: list[Path] | None = None
    limited_to: int | None = None
    time_shift_rows: list[ReflowTimeShiftPlanRow] = field(default_factory=list)

    @property
    def files_to_copy(self) -> int:
        return sum(1 for row in self.rows if row.status == "plan_copy")

    @property
    def bytes_to_copy(self) -> int:
        return sum(row.size_bytes for row in self.rows if row.status == "plan_copy")

    @property
    def files_to_transfer(self) -> int:
        return self.files_to_copy

    @property
    def bytes_to_transfer(self) -> int:
        return self.bytes_to_copy


@dataclass(frozen=True)
class LibraryScore:
    score: int
    file_count: int
    total_bytes: int
    duplicate_names: int
    year_count: int
    notes: list[str]


def build_den_plan(
    source_root: Path,
    destination_root: Path,
    *,
    project_name: str | None = None,
    layout_mode: DenLayoutMode = DenLayoutMode.PRESERVE,
    transfer_action: DenTransferAction = DenTransferAction.COPY,
    folder_template: str = "YYYY/YYYY-MM",
    exclude_roots: list[Path] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int | None = None,
    preserve_dates_drop_parts: set[str] | None = None,
    filename_policy: DestinationFilenamePolicy = DestinationFilenamePolicy.ORIGINAL,
) -> DenPlan:
    source_root = source_root.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    excluded_roots = [path.expanduser().resolve() for path in (exclude_roots or [])]
    items = scan_raw_files(source_root, exclude_roots=excluded_roots, limit=limit)
    item_capture_times = capture_times([item.path for item in items])
    items = _filter_items_by_capture_date(
        items,
        start_date=start_date,
        end_date=end_date,
        item_capture_times=item_capture_times,
    )
    earliest = min((item_capture_times[item.path] for item in items), default=datetime.now(UTC))
    if layout_mode in {
        DenLayoutMode.PRESERVE,
        DenLayoutMode.PRESERVE_DATES,
        DenLayoutMode.DATE,
        DenLayoutMode.PROJECT_DATES,
    }:
        destination_folder = destination_root
    elif layout_mode == DenLayoutMode.PROJECT or project_name:
        destination_folder = default_project_destination(
            destination_root,
            project_name or source_root.name,
            earliest,
            folder_template,
        )

    rows: list[DenPlanRow] = []
    planned_destinations: set[Path] = set()
    for item in items:
        row = _plan_row(
            source_root,
            destination_root,
            destination_folder,
            item,
            layout_mode=layout_mode,
            folder_template=folder_template,
            project_name=project_name or source_root.name,
            preserve_dates_drop_parts=preserve_dates_drop_parts or set(),
            filename_policy=filename_policy,
            reserved_destinations=planned_destinations,
            captured_at=item_capture_times[item.path],
        )
        if row.status == "plan_copy":
            if row.destination_path in planned_destinations:
                row = DenPlanRow(
                    source_path=row.source_path,
                    destination_path=row.destination_path,
                    size_bytes=row.size_bytes,
                    status="collision",
                )
            else:
                planned_destinations.add(row.destination_path)
        rows.append(row)
    return DenPlan(
        source_root=source_root,
        destination_root=destination_root,
        destination_folder=destination_folder,
        rows=rows,
        transfer_action=transfer_action,
        excluded_roots=excluded_roots,
        limited_to=limit,
    )


def execute_den_plan(plan: DenPlan) -> list[DenPlanRow]:
    executed: list[DenPlanRow] = []
    for row in plan.rows:
        if row.status != "plan_copy":
            executed.append(row)
            continue
        status = (
            append_only_move(row.source_path, row.destination_path, plan.destination_root)
            if plan.transfer_action == DenTransferAction.MOVE
            else append_only_copy(row.source_path, row.destination_path, plan.destination_root)
        )
        executed.append(
            DenPlanRow(
                source_path=row.source_path,
                destination_path=row.destination_path,
                size_bytes=row.size_bytes,
                status=status,
            )
        )
    return executed


def summarize_by_year(rows: list[DenPlanRow]) -> list[dict[str, object]]:
    summary: dict[str, dict[str, object]] = defaultdict(
        lambda: {"year": "unknown", "files_to_copy": 0, "total_bytes": 0, "estimated_gb": 0.0}
    )
    for row in rows:
        if row.status != "plan_copy":
            continue
        year = _year_from_destination(row.destination_path)
        bucket = summary[year]
        bucket["year"] = year
        bucket["files_to_copy"] = int(bucket["files_to_copy"]) + 1
        bucket["total_bytes"] = int(bucket["total_bytes"]) + row.size_bytes
        bucket["estimated_gb"] = round(int(bucket["total_bytes"]) / 1_000_000_000, 2)
    return [summary[key] for key in sorted(summary)]


def capture_date_counts(items: list[InventoryItem]) -> Counter[date]:
    item_capture_times = capture_times([item.path for item in items])
    return Counter(item_capture_times[item.path].date() for item in items)


def score_items(items: list[InventoryItem]) -> LibraryScore:
    total_bytes = sum(item.size_bytes for item in items)
    name_counts = Counter(item.path.name for item in items)
    duplicate_names = sum(1 for count in name_counts.values() if count > 1)
    item_capture_times = capture_times([item.path for item in items])
    years = {item_capture_times[item.path].year for item in items}
    score = 100
    notes: list[str] = []
    if not items:
        return LibraryScore(0, 0, 0, 0, 0, ["No RAW, JPEG, or camera video files found."])
    if duplicate_names:
        score -= min(30, duplicate_names * 2)
        notes.append(f"{duplicate_names} duplicated filenames need review.")
    if len(years) > 5:
        score -= 10
        notes.append("Many capture years in one source; consider project/session splits.")
    if not notes:
        notes.append("No obvious filename or year-spread issues found.")
    return LibraryScore(
        score=max(score, 0),
        file_count=len(items),
        total_bytes=total_bytes,
        duplicate_names=duplicate_names,
        year_count=len(years),
        notes=notes,
    )


def _filter_items_by_capture_date(
    items: list[InventoryItem],
    *,
    start_date: date | None,
    end_date: date | None,
    item_capture_times: dict[Path, datetime],
) -> list[InventoryItem]:
    if start_date is None and end_date is None:
        return items
    filtered = []
    for item in items:
        captured_on = item_capture_times[item.path].date()
        if start_date is not None and captured_on < start_date:
            continue
        if end_date is not None and captured_on > end_date:
            continue
        filtered.append(item)
    return filtered


def _plan_row(
    source_root: Path,
    destination_root: Path,
    destination_folder: Path,
    item: InventoryItem,
    *,
    layout_mode: DenLayoutMode,
    folder_template: str,
    project_name: str,
    preserve_dates_drop_parts: set[str],
    filename_policy: DestinationFilenamePolicy,
    reserved_destinations: set[Path],
    captured_at: datetime,
) -> DenPlanRow:
    relative_path = (
        _drop_preserve_dates_parts(item.relative_path, preserve_dates_drop_parts)
        if layout_mode == DenLayoutMode.PRESERVE_DATES
        else item.relative_path
    )
    if layout_mode == DenLayoutMode.DATE or (
        layout_mode == DenLayoutMode.PRESERVE_DATES
        and _has_camera_dump_relative_path(source_root, relative_path)
    ):
        preserved_prefix = (
            ()
            if layout_mode == DenLayoutMode.DATE
            else _meaningful_prefix_before_camera_dump(source_root, relative_path)
        )
        year_scoped_prefix = _year_scoped_prefix(preserved_prefix, captured_at)
        destination_parent = (
            destination_root
            / Path(*year_scoped_prefix)
            / _date_destination_without_duplicate_prefix(
                year_scoped_prefix,
                default_date_only_destination(Path(), captured_at, folder_template),
            )
        )
    elif layout_mode == DenLayoutMode.PROJECT_DATES:
        destination_parent = (
            destination_root
            / render_folder_template(folder_template, captured_at, project_name=project_name)
        )
    elif layout_mode == DenLayoutMode.PRESERVE_DATES:
        preserved_path = _year_scoped_preserved_path(
            relative_path,
            captured_at,
        )
        destination_parent = destination_folder / preserved_path.parent
    elif layout_mode == DenLayoutMode.PROJECT:
        destination_parent = destination_folder
    else:
        destination_parent = destination_folder / relative_path.parent
    destination = destination_path_for_filename_policy(
        item.path,
        destination_parent,
        captured_at,
        policy=filename_policy,
        reserved_destinations=reserved_destinations,
        size_bytes=item.size_bytes,
    )
    status = "plan_copy"
    if destination.exists():
        if destination.name == item.path.name and destination.stat().st_size == item.size_bytes:
            status = "skip_existing_same_name_size"
        else:
            status = "collision"
    return DenPlanRow(
        source_path=item.path,
        destination_path=destination,
        size_bytes=item.size_bytes,
        status=status,
    )


def _drop_preserve_dates_parts(relative_path: Path, drop_parts: set[str]) -> Path:
    if not drop_parts:
        return relative_path
    parent_parts = tuple(part for part in relative_path.parent.parts if part not in drop_parts)
    return (Path(*parent_parts) / relative_path.name) if parent_parts else Path(relative_path.name)


def _has_camera_dump_relative_path(source_root: Path, relative_path: Path) -> bool:
    if is_camera_dump_part(source_root.name):
        return True
    parent_parts = relative_path.parts[:-1]
    return any(is_camera_dump_part(part) for part in parent_parts)


def _meaningful_prefix_before_camera_dump(source_root: Path, relative_path: Path) -> tuple[str, ...]:
    if is_camera_dump_part(source_root.name):
        return ()
    prefix: list[str] = []
    for part in relative_path.parts[:-1]:
        if is_camera_dump_part(part):
            break
        prefix.append(part)
    return normalize_date_folder_parts(tuple(prefix))


def _date_destination_without_duplicate_prefix(
    preserved_prefix: tuple[str, ...],
    date_destination: Path,
) -> Path:
    if not preserved_prefix or not date_destination.parts:
        return date_destination
    if date_destination.parts[0] in preserved_prefix:
        return Path(*date_destination.parts[1:])
    return date_destination


def _normalize_relative_date_folders(relative_path: Path) -> Path:
    if not relative_path.parts:
        return relative_path
    parent_parts = normalize_date_folder_parts(relative_path.parent.parts)
    return Path(*parent_parts) / relative_path.name


def _year_scoped_preserved_path(relative_path: Path, captured_at: datetime) -> Path:
    normalized = _normalize_relative_date_folders(relative_path)
    if not normalized.parts:
        return normalized
    year = f"{captured_at.year:04d}"
    first_part = normalized.parts[0]
    if first_part == year:
        return normalized
    if len(first_part) == 8 and first_part.isdigit() and first_part.startswith(year):
        return Path(year) / normalized
    if first_part.startswith(f"{year}-") or first_part.startswith(f"{year}_"):
        return Path(year) / normalized
    return Path(year) / normalized


def _year_scoped_prefix(prefix: tuple[str, ...], captured_at: datetime) -> tuple[str, ...]:
    if not prefix:
        return prefix
    year = f"{captured_at.year:04d}"
    if prefix[0] == year:
        return prefix
    return (year, *prefix)


def _year_from_destination(path: Path) -> str:
    for part in path.parts:
        if len(part) == 4 and part.isdigit():
            return part
    return "unknown"
