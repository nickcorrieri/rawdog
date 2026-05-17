# Author: Nicholas Corrieri

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, Field

from rawdog import __version__
from rawdog.models import OrganizationMode
from rawdog.planner import default_date_only_destination, slug_folder_name


def rawdog_version() -> str:
    try:
        return version("rawdog")
    except PackageNotFoundError:
        return __version__


class DestinationMemory(BaseModel):
    rawdog_version: str = Field(default_factory=rawdog_version)
    memory_kind: str = "destination_project_memory"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
        json.dump(memory.model_dump(mode="json"), handle, indent=2)
        handle.write("\n")
    return path
