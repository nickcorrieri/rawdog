# Author: Nicholas Corrieri

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rawdog.compare import same_name_and_size
from rawdog.safety import ensure_archive_destination, ensure_no_overwrite, ensure_same_filesystem


class CopySkipped(RuntimeError):
    pass


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
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        return "skipped_existing_partial"
    try:
        shutil.copy2(source, partial)
        os.rename(partial, destination)
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.rename(source, destination)
    return "moved"
