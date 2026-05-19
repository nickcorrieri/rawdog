# Author: Nicholas Corrieri

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from rawdog.compare import same_name_and_size
from rawdog.datefolders import date_folder_timestamp
from rawdog.safety import ensure_archive_destination, ensure_no_overwrite, ensure_same_filesystem


def append_only_copy(
    source: Path,
    destination: Path,
    archive_root: Path,
    dry_run: bool = False,
    progress_callback: Callable[[int], None] | None = None,
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
        _copy2_with_progress(source, partial, progress_callback=progress_callback)
        os.rename(partial, destination)
        _preserve_macos_birthtime(source, destination)
        _timestamp_created_date_dirs(created_dirs)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return "copied"


def _copy2_with_progress(
    source: Path,
    destination: Path,
    *,
    progress_callback: Callable[[int], None] | None = None,
    chunk_size: int = 1024 * 1024,
) -> None:
    if progress_callback is None:
        shutil.copy2(source, destination)
        return
    with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
        while True:
            chunk = source_handle.read(chunk_size)
            if not chunk:
                break
            destination_handle.write(chunk)
            progress_callback(len(chunk))
    shutil.copystat(source, destination)


def _preserve_macos_birthtime(source: Path, destination: Path) -> None:
    if sys.platform != "darwin":
        return
    birthtime = getattr(source.stat(), "st_birthtime", None)
    if birthtime is None:
        return
    try:
        _set_macos_birthtime(destination, birthtime)
    except OSError:
        return


def _set_macos_birthtime(path: Path, timestamp: float) -> None:
    class AttrList(ctypes.Structure):
        _fields_ = [
            ("bitmapcount", ctypes.c_ushort),
            ("reserved", ctypes.c_ushort),
            ("commonattr", ctypes.c_uint),
            ("volattr", ctypes.c_uint),
            ("dirattr", ctypes.c_uint),
            ("fileattr", ctypes.c_uint),
            ("forkattr", ctypes.c_uint),
        ]

    class Timespec(ctypes.Structure):
        _fields_ = [
            ("tv_sec", ctypes.c_long),
            ("tv_nsec", ctypes.c_long),
        ]

    attr_bit_map_count = 5
    attr_cmn_crtime = 0x00000200
    fsopt_no_follow = 0x00000001
    attr_list = AttrList(attr_bit_map_count, 0, attr_cmn_crtime, 0, 0, 0, 0)
    seconds = int(timestamp)
    nanoseconds = int((timestamp - seconds) * 1_000_000_000)
    timespec = Timespec(seconds, nanoseconds)
    libc = ctypes.CDLL("libc.dylib", use_errno=True)
    result = libc.setattrlist(
        os.fsencode(path),
        ctypes.byref(attr_list),
        ctypes.byref(timespec),
        ctypes.sizeof(timespec),
        fsopt_no_follow,
    )
    if result != 0:
        raise OSError(ctypes.get_errno(), "failed to preserve macOS creation time", str(path))


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
