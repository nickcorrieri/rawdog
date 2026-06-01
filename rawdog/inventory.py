# Author: Nicholas Corrieri

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rawdog.metadata import capture_times, is_camera_capture_file

DEFAULT_SKIPPED_DIRS = {
    ".DocumentRevisions-V100",
    ".Spotlight-V100",
    ".TemporaryItems",
    ".Trashes",
    ".fseventsd",
    ".rawdog",
    "__MACOSX",
}


@dataclass(frozen=True)
class InventoryItem:
    path: Path
    relative_path: Path
    size_bytes: int
    mtime_ns: int


def scan_raw_files(
    root: Path,
    *,
    exclude_roots: list[Path] | None = None,
    limit: int | None = None,
    on_item: Callable[[InventoryItem], None] | None = None,
    on_progress: Callable[[Path, int, int], None] | None = None,
) -> list[InventoryItem]:
    root = root.expanduser().resolve()
    resolved_excludes = tuple(path.expanduser().resolve() for path in (exclude_roots or []))
    items: list[InventoryItem] = []
    scanned_entries = 0
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        if on_progress is not None:
            on_progress(current_path, scanned_entries, len(items))
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if dirname not in DEFAULT_SKIPPED_DIRS
            and not _is_excluded(current_path / dirname, resolved_excludes)
        )
        for filename in sorted(filenames):
            if filename.startswith("._"):
                continue
            path = current_path / filename
            scanned_entries += 1
            if on_progress is not None and scanned_entries % 100 == 0:
                on_progress(path, scanned_entries, len(items))
            if _is_excluded(path, resolved_excludes) or not path.is_file() or not is_camera_capture_file(path):
                continue
            stat = path.stat()
            item = InventoryItem(
                path=path,
                relative_path=path.relative_to(root),
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
            items.append(item)
            if on_item is not None:
                on_item(item)
            if on_progress is not None:
                on_progress(path, scanned_entries, len(items))
            if limit is not None and len(items) >= limit:
                return items
    return items



def earliest_raw_capture_time(
    root: Path,
    *,
    exclude_roots: list[Path] | None = None,
) -> datetime | None:
    items = scan_raw_files(root, exclude_roots=exclude_roots)
    if not items:
        return None
    times = capture_times([item.path for item in items])
    return min(times[item.path] for item in items)


def _is_excluded(path: Path, exclude_roots: tuple[Path, ...]) -> bool:
    resolved = path.expanduser().resolve()
    for exclude_root in exclude_roots:
        if resolved == exclude_root or exclude_root in resolved.parents:
            return True
    return False
