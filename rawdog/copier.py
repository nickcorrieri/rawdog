# Author: Nicholas Corrieri

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rawdog.safety import ensure_archive_destination, ensure_no_overwrite


class CopySkipped(RuntimeError):
    pass


def append_only_copy(source: Path, destination: Path, archive_root: Path, dry_run: bool = False) -> str:
    ensure_archive_destination(destination, archive_root)
    if destination.exists():
        source_size = source.stat().st_size
        destination_size = destination.stat().st_size
        if source.name == destination.name and source_size == destination_size:
            return "skipped_existing_same_name_size"
        return "skipped_collision"

    if dry_run:
        return "planned"

    ensure_no_overwrite(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        partial.unlink()
    shutil.copy2(source, partial)
    os.rename(partial, destination)
    return "copied"
