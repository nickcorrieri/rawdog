# Author: Nicholas Corrieri

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rawdog.compare import same_name_and_size
from rawdog.datefolders import date_folder_timestamp
from rawdog.safety import ensure_archive_destination, ensure_no_overwrite, ensure_same_filesystem


def append_only_copy(
    source: Path,
    destination: Path,
    archive_root: Path,
    dry_run: bool = False,
) -> str:
    ensure_archive_destination(destination, archive_root)
    if destination.exists():
        if same_name_and_size(source, destination):
            return "skipped_existing_same_name_size"
        return "skipped_collision"

    if dry_run:
        return "planned"

    ensure_no_overwrite(destination)
    created_dirs = _create_destination_parent(destination, archive_root)
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        return "skipped_existing_partial"
    try:
        shutil.copy2(source, partial)
        os.rename(partial, destination)
        _timestamp_created_date_dirs(created_dirs)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return "copied"


def append_only_move(
    source: Path,
    destination: Path,
    destination_root: Path,
    dry_run: bool = False,
) -> str:
    ensure_archive_destination(destination, destination_root)
    ensure_same_filesystem(source, destination_root)
    if destination.exists():
        if same_name_and_size(source, destination):
            return "skipped_existing_same_name_size"
        return "skipped_collision"

    if dry_run:
        return "planned_move"

    ensure_no_overwrite(destination)
    created_dirs = _create_destination_parent(destination, destination_root)
    os.rename(source, destination)
    _timestamp_created_date_dirs(created_dirs)
    return "moved"


def _create_destination_parent(destination: Path, archive_root: Path) -> list[Path]:
    archive_resolved = archive_root.expanduser().resolve()
    parent = destination.parent.expanduser()
    created_dirs: list[Path] = []
    current = parent
    while not current.exists():
        created_dirs.append(current)
        if current == archive_resolved:
            break
        current = current.parent
    parent.mkdir(parents=True, exist_ok=True)
    return list(reversed(created_dirs))


def _timestamp_created_date_dirs(created_dirs: list[Path]) -> None:
    for directory in created_dirs:
        timestamp = date_folder_timestamp(directory.name)
        if timestamp is None:
            continue
        os.utime(directory, (timestamp, timestamp))
