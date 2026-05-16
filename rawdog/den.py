# Author: Nicholas Corrieri

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rawdog.copier import append_only_copy, append_only_move
from rawdog.datefolders import normalize_date_folder_parts
from rawdog.inventory import InventoryItem, earliest_raw_capture_time, scan_raw_files
from rawdog.models import DenLayoutMode, DenTransferAction
from rawdog.planner import default_date_only_destination, default_project_destination


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
) -> DenPlan:
    source_root = source_root.expanduser().resolve()
    destination_root = destination_root.expanduser()
    items = scan_raw_files(source_root)
    earliest = earliest_raw_capture_time(source_root) or datetime.now(timezone.utc)
    if layout_mode in {DenLayoutMode.PRESERVE, DenLayoutMode.PRESERVE_DATES}:
        destination_folder = destination_root
    elif layout_mode == DenLayoutMode.PROJECT or project_name:
        destination_folder = default_project_destination(
            destination_root,
            project_name or source_root.name,
            earliest,
            folder_template,
        )
    else:
        destination_folder = default_date_only_destination(destination_root, earliest, folder_template)

    rows = [
        _plan_row(
            source_root,
            destination_folder,
            item,
            normalize_date_folders=layout_mode == DenLayoutMode.PRESERVE_DATES,
        )
        for item in items
    ]
    return DenPlan(
        source_root=source_root,
        destination_root=destination_root,
        destination_folder=destination_folder,
        rows=rows,
        transfer_action=transfer_action,
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
    destination_folder: Path,
    item: InventoryItem,
    *,
    normalize_date_folders: bool = False,
) -> DenPlanRow:
    relative_path = (
        _normalize_relative_date_folders(item.relative_path)
        if normalize_date_folders
        else item.relative_path
    )
    destination = destination_folder / relative_path
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
