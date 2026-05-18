# Author: Nicholas Corrieri

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rawdog import __version__
from rawdog.models import OrganizationMode, model_to_json_data
from rawdog.planner import slug_folder_name


def rawdog_version() -> str:
    return __version__


@dataclass(slots=True, kw_only=True)
class DestinationMemory:
    rawdog_version: str = field(default_factory=rawdog_version)
    memory_kind: str = "destination_project_memory"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    organization_mode: OrganizationMode
    project_name: str | None = None
    memory_name: str
    source_root: Path
    destination_root: Path
    destination_folder: Path
    folder_template: str
    earliest_capture_at: datetime | None = None
    profile_name: str | None = None


def memory_dir_for_destination(destination_folder: Path) -> Path:
    return destination_folder / ".rawdog"


def memory_file_for_destination(destination_folder: Path) -> Path:
    return memory_dir_for_destination(destination_folder) / "project.json"


def date_only_project_name(year: int, month: int | None = None) -> str:
    if month is None:
        return f"{year:04d}"
    return f"{year:04d}-{month:02d}"


def build_destination_memory(
    *,
    organization_mode: OrganizationMode,
    source_root: Path,
    destination_root: Path,
    destination_folder: Path,
    folder_template: str,
    project_name: str | None = None,
    earliest_capture_at: datetime | None = None,
    profile_name: str | None = None,
) -> DestinationMemory:
    return DestinationMemory(
        organization_mode=organization_mode,
        project_name=slug_folder_name(project_name) if project_name else None,
        memory_name=slug_folder_name(project_name) if project_name else "Date_Only",
        source_root=source_root,
        destination_root=destination_root,
        destination_folder=destination_folder,
        folder_template=folder_template,
        earliest_capture_at=earliest_capture_at,
        profile_name=profile_name,
    )


def write_destination_memory(memory: DestinationMemory, dry_run: bool = True) -> Path:
    path = memory_file_for_destination(memory.destination_folder)
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(model_to_json_data(memory), handle, indent=2)
        handle.write("\n")
    return path
