# Author: Nicholas Corrieri

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rawdog.copier import append_only_copy, append_only_move
from rawdog.datefolders import normalize_date_folder_parts
from rawdog.inventory import InventoryItem, scan_raw_files
from rawdog.layout import is_camera_dump_part
from rawdog.metadata import capture_time_fallback
from rawdog.models import DenLayoutMode, DenTransferAction
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
class DenPlan:
    source_root: Path
    destination_root: Path
    destination_folder: Path
    rows: list[DenPlanRow]
    transfer_action: DenTransferAction = DenTransferAction.COPY
    excluded_roots: list[Path] | None = None
    limited_to: int | None = None

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
    limit: int | None = None,
) -> DenPlan:
    source_root = source_root.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    excluded_roots = [path.expanduser().resolve() for path in (exclude_roots or [])]
    items = scan_raw_files(source_root, exclude_roots=excluded_roots, limit=limit)
    earliest = min((capture_time_fallback(item.path) for item in items), default=datetime.now(UTC))
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

    rows = [
        _plan_row(
            source_root,
            destination_root,
            destination_folder,
            item,
            layout_mode=layout_mode,
            folder_template=folder_template,
            project_name=project_name or source_root.name,
        )
        for item in items
    ]
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


def score_items(items: list[InventoryItem]) -> LibraryScore:
    total_bytes = sum(item.size_bytes for item in items)
    name_counts = Counter(item.path.name for item in items)
    duplicate_names = sum(1 for count in name_counts.values() if count > 1)
    years = {
        datetime.fromtimestamp(item.path.stat().st_mtime).year
        for item in items
    }
    score = 100
    notes: list[str] = []
    if not items:
        return LibraryScore(0, 0, 0, 0, 0, ["No RAW files found."])
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


def _plan_row(
    source_root: Path,
    destination_root: Path,
    destination_folder: Path,
    item: InventoryItem,
    *,
    layout_mode: DenLayoutMode,
    folder_template: str,
    project_name: str,
) -> DenPlanRow:
    if layout_mode == DenLayoutMode.DATE or (
        layout_mode == DenLayoutMode.PRESERVE_DATES
        and _has_camera_dump_relative_path(source_root, item.relative_path)
    ):
        captured_at = capture_time_fallback(item.path)
        preserved_prefix = (
            ()
            if layout_mode == DenLayoutMode.DATE
            else _meaningful_prefix_before_camera_dump(source_root, item.relative_path)
        )
        destination = (
            destination_root
            / Path(*preserved_prefix)
            / default_date_only_destination(Path(), captured_at, folder_template)
            / item.path.name
        )
    elif layout_mode == DenLayoutMode.PROJECT_DATES:
        captured_at = capture_time_fallback(item.path)
        destination = (
            destination_root
            / render_folder_template(folder_template, captured_at, project_name=project_name)
            / item.path.name
        )
    elif layout_mode == DenLayoutMode.PRESERVE_DATES:
        destination = destination_folder / _normalize_relative_date_folders(item.relative_path)
    elif layout_mode == DenLayoutMode.PROJECT:
        destination = destination_folder / item.path.name
    else:
        destination = destination_folder / item.relative_path
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


def _normalize_relative_date_folders(relative_path: Path) -> Path:
    if not relative_path.parts:
        return relative_path
    parent_parts = normalize_date_folder_parts(relative_path.parent.parts)
    return Path(*parent_parts) / relative_path.name


def _year_from_destination(path: Path) -> str:
    for part in path.parts:
        if len(part) == 4 and part.isdigit():
            return part
    return "unknown"
