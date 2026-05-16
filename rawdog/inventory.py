# Author: Nicholas Corrieri

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rawdog.metadata import capture_time_fallback, is_raw_file


@dataclass(frozen=True)
class InventoryItem:
    path: Path
    relative_path: Path
    size_bytes: int
    mtime_ns: int


def scan_raw_files(root: Path) -> list[InventoryItem]:
    root = root.expanduser().resolve()
    items: list[InventoryItem] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not is_raw_file(path):
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
    return items


def earliest_raw_capture_time(root: Path) -> datetime | None:
    items = scan_raw_files(root)
    if not items:
        return None
    return min(capture_time_fallback(item.path) for item in items)
