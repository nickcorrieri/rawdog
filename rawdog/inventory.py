# Author: Nicholas Corrieri

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rawdog.metadata import capture_time_fallback, is_camera_capture_file

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
) -> list[InventoryItem]:
    root = root.expanduser().resolve()
    resolved_excludes = tuple(path.expanduser().resolve() for path in (exclude_roots or []))
    items: list[InventoryItem] = []
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
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
            if _is_excluded(path, resolved_excludes) or not path.is_file() or not is_camera_capture_file(path):
                continue
            stat = path.stat()
            items.append(
                InventoryItem(
                    path=path,
                    relative_path=path.relative_to(root),
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
            )
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
    return min(capture_time_fallback(item.path) for item in items)


def _is_excluded(path: Path, exclude_roots: tuple[Path, ...]) -> bool:
    resolved = path.expanduser().resolve()
    for exclude_root in exclude_roots:
        if resolved == exclude_root or exclude_root in resolved.parents:
            return True
    return False
