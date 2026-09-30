# Author: Nicholas Corrieri

from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from rawdog.compare import same_name_and_content
from rawdog.datefolders import date_folder_timestamp
from rawdog.safety import (
    SafetyError,
    absolute_lexical_path,
    ensure_archive_destination,
    ensure_no_overwrite,
    ensure_same_filesystem,
    open_directory,
    require_directory_path,
)
from rawdog.verifier import (
    capture_file_version,
    capture_open_file_version,
    open_regular_file,
    read_ancillary_payloads,
    require_file_version,
    set_ancillary_payloads,
)


def append_only_copy(
    source: Path,
    destination: Path,
    archive_root: Path,
    dry_run: bool = False,
    progress_callback: Callable[[int], None] | None = None,
    *,
    expected_source_version: dict | None = None,
) -> str:
    source = absolute_lexical_path(source)
    destination = absolute_lexical_path(destination)
    archive_root = absolute_lexical_path(archive_root)
    ensure_archive_destination(destination, archive_root)
    if not dry_run:
        _require_native_publication()
    source_version = expected_source_version if expected_source_version is not None else capture_file_version(source)
    require_file_version(source, source_version)
    if os.path.lexists(destination):
        if same_name_and_content(source, destination):
            require_file_version(source, source_version)
            return "skipped_existing_same_name_size"
        return "skipped_collision"

    if dry_run:
        return "planned"

    if os.path.lexists(destination.with_name(destination.name + ".partial")):
        return "skipped_existing_partial"
    root_descriptor = open_directory(archive_root)
    parent_descriptor = None
    partial_descriptor = None
    date_directories = []
    try:
        with open_regular_file(source) as source_descriptor:
            ensure_no_overwrite(destination)
            created_dirs = _create_destination_parent(destination, archive_root)
            ensure_archive_destination(destination, archive_root)
            require_directory_path(archive_root, root_descriptor)
            parent_descriptor = open_directory(destination.parent)
            date_directories = _open_created_date_dirs(created_dirs)
            partial = destination.with_name(f".rawdog-{uuid.uuid4().hex}.partial")
            partial_descriptor = os.open(partial.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=parent_descriptor)
            _copy2_with_progress(source, partial, progress_callback=progress_callback,
                                 source_fd=source_descriptor, destination_fd=partial_descriptor)
            _preserve_macos_birthtime(source, partial, source_fd=source_descriptor,
                                      destination_fd=partial_descriptor)
            os.fsync(partial_descriptor)
            require_file_version(source, source_version)
            partial_version = capture_open_file_version(partial_descriptor)
            if _payload(partial_version) != _payload(source_version):
                raise SafetyError(f"Copied bytes did not verify before publication: {source} -> {destination}")
            require_file_version(partial, partial_version)
            ensure_archive_destination(destination, archive_root)
            require_directory_path(archive_root, root_descriptor)
            require_directory_path(destination.parent, parent_descriptor)
            _rename_no_replace(partial, destination, source_directory_fd=parent_descriptor,
                                destination_directory_fd=parent_descriptor,
                                source_file_fd=partial_descriptor, expected_source_version=partial_version)
            os.fsync(parent_descriptor)
            published = capture_file_version(destination)
            if _payload(published) != _payload(source_version) or published["ino"] != partial_version["ino"]:
                raise SafetyError("published copy changed before its final verification")
            require_file_version(source, source_version)
            _timestamp_created_date_dirs(date_directories)
    finally:
        # Pathname cleanup could delete a replacement owned by another writer.
        # Retain incomplete artifacts for explicit review instead.
        if partial_descriptor is not None:
            os.close(partial_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        for _, descriptor in date_directories:
            os.close(descriptor)
        os.close(root_descriptor)
    return "copied"


def _copy2_with_progress(
    source: Path,
    destination: Path,
    *,
    progress_callback: Callable[[int], None] | None = None,
    chunk_size: int = 1024 * 1024,
    source_fd: int | None = None,
    destination_fd: int | None = None,
) -> None:
    if source_fd is None or destination_fd is None:
        raise SafetyError("copy requires exclusively owned file descriptors")
    source_stat = os.fstat(source_fd)
    os.lseek(source_fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(source_fd), "rb") as source_handle, os.fdopen(os.dup(destination_fd), "wb") as destination_handle:
        while True:
            chunk = source_handle.read(chunk_size)
            if not chunk:
                break
            destination_handle.write(chunk)
            if progress_callback:
                progress_callback(len(chunk))
    os.fchmod(destination_fd, stat.S_IMODE(source_stat.st_mode))
    os.utime(destination_fd, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    set_ancillary_payloads(destination_fd, read_ancillary_payloads(source_fd))


def _preserve_macos_birthtime(source: Path, destination: Path, *, source_fd: int,
                             destination_fd: int) -> None:
    if sys.platform != "darwin":
        return
    birthtime = getattr(os.fstat(source_fd), "st_birthtime", None)
    if birthtime is None:
        return
    try:
        _set_macos_birthtime(destination, birthtime, descriptor=destination_fd)
    except OSError:
        return


def _set_macos_birthtime(path: Path, timestamp: float, *, descriptor: int | None = None) -> None:
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
    if descriptor is not None:
        result = libc.fsetattrlist(descriptor, ctypes.byref(attr_list), ctypes.byref(timespec),
                                   ctypes.sizeof(timespec), 0)
    else:
        result = libc.setattrlist(os.fsencode(path), ctypes.byref(attr_list), ctypes.byref(timespec),
                                  ctypes.sizeof(timespec), fsopt_no_follow)
    if result != 0:
        raise OSError(ctypes.get_errno(), "failed to preserve macOS creation time", str(path))


def append_only_move(
    source: Path,
    destination: Path,
    destination_root: Path,
    dry_run: bool = False,
    *,
    expected_source_version: dict | None = None,
) -> str:
    source = absolute_lexical_path(source)
    destination = absolute_lexical_path(destination)
    destination_root = absolute_lexical_path(destination_root)
    ensure_archive_destination(destination, destination_root)
    ensure_same_filesystem(source, destination_root)
    if not dry_run:
        _require_native_publication()
    source_version = expected_source_version if expected_source_version is not None else capture_file_version(source)
    require_file_version(source, source_version)
    if os.path.lexists(destination):
        if same_name_and_content(source, destination):
            require_file_version(source, source_version)
            return "skipped_existing_same_name_size"
        return "skipped_collision"

    if dry_run:
        return "planned_move"

    root_descriptor = open_directory(destination_root)
    source_parent = None
    destination_parent = None
    date_directories = []
    try:
        with open_regular_file(source, require_path_after=False) as source_descriptor:
            ensure_no_overwrite(destination)
            created_dirs = _create_destination_parent(destination, destination_root)
            ensure_archive_destination(destination, destination_root)
            require_directory_path(destination_root, root_descriptor)
            source_parent = open_directory(source.parent)
            destination_parent = open_directory(destination.parent)
            date_directories = _open_created_date_dirs(created_dirs)
            require_file_version(source, source_version)
            require_directory_path(source.parent, source_parent)
            require_directory_path(destination.parent, destination_parent)
            _rename_for_move(source, destination, source_directory_fd=source_parent,
                             destination_directory_fd=destination_parent,
                             source_file_fd=source_descriptor, expected_source_version=source_version)
            os.fsync(destination_parent)
            os.fsync(source_parent)
            published = capture_file_version(destination)
            if (_payload(published) != _payload(source_version) or
                    (published["dev"], published["ino"]) != (source_version["dev"], source_version["ino"])):
                raise SafetyError("moved file changed before final verification")
            _timestamp_created_date_dirs(date_directories)
    finally:
        if source_parent is not None:
            os.close(source_parent)
        if destination_parent is not None:
            os.close(destination_parent)
        for _, descriptor in date_directories:
            os.close(descriptor)
        os.close(root_descriptor)
    return "moved"


def _rename_for_move(source: Path, destination: Path, *, source_directory_fd: int,
                     destination_directory_fd: int, source_file_fd: int,
                     expected_source_version: dict) -> None:
    try:
        _rename_no_replace(source, destination, source_directory_fd=source_directory_fd,
                            destination_directory_fd=destination_directory_fd,
                            source_file_fd=source_file_fd, expected_source_version=expected_source_version)
    except OSError as exc:
        if exc.errno in {errno.EPERM, errno.EACCES}:
            raise SafetyError(_rename_permission_message(source, destination, exc)) from exc
        raise


def _payload(version: dict) -> tuple:
    return version["size"], version["sha256"], version["ancillary"]


def _require_native_publication() -> None:
    if sys.platform != "darwin":
        raise SafetyError("native no-replace transfer is not qualified on this platform")
    if not hasattr(ctypes.CDLL("libc.dylib", use_errno=True), "renameatx_np"):
        raise SafetyError("native exclusive rename is unavailable; no replacement fallback is allowed")


def _rename_no_replace(source: Path, destination: Path, *, source_directory_fd: int,
                       destination_directory_fd: int, source_file_fd: int,
                       expected_source_version: dict) -> None:
    _require_native_publication()
    libc = ctypes.CDLL("libc.dylib", use_errno=True)
    exclusive_rename = libc.renameatx_np
    exclusive_rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    exclusive_rename.restype = ctypes.c_int
    require_directory_path(source.parent, source_directory_fd)
    require_directory_path(destination.parent, destination_directory_fd)
    require_file_version(source, expected_source_version)
    if capture_open_file_version(source_file_fd) != expected_source_version:
        raise SafetyError("held source changed before native publication")
    named = os.stat(source.name, dir_fd=source_directory_fd, follow_symlinks=False)
    if (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns, named.st_ctime_ns) != (
            expected_source_version["dev"], expected_source_version["ino"], expected_source_version["size"],
            expected_source_version["mtime_ns"], expected_source_version["ctime_ns"]):
        raise SafetyError("named source changed before native publication")
    # macOS SDK sys/stdio.h: RENAME_EXCL = 0x00000004. Unsupported
    # filesystem flags fail; never retry with a replacing rename.
    # renameatx_np has no expected-inode argument. A noncooperating external
    # writer can still race the final check-to-syscall interval.
    if exclusive_rename(source_directory_fd, os.fsencode(source.name), destination_directory_fd,
                        os.fsencode(destination.name), 0x00000004) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))


def _rename_permission_message(source: Path, destination: Path, exc: OSError) -> str:
    destination_parent = destination.parent
    return "\n".join(
        [
            f"Filesystem refused MOVE rename: {exc}",
            f"Source: {source}",
            f"Destination: {destination}",
            f"Source exists: {_yes_no(source.exists())}",
            f"Source parent writable: {_yes_no(_can_access(source.parent, os.W_OK))}",
            f"Destination parent exists: {_yes_no(destination_parent.exists())}",
            f"Destination parent writable: {_yes_no(_can_access(destination_parent, os.W_OK))}",
            f"Source flags: {_path_flags(source)}",
            f"Destination parent flags: {_path_flags(destination_parent)}",
            "Common causes: locked file, ACL/permission issue, read-only mount, or filesystem refusing rename.",
            f"Inspect on macOS: ls -lOe@ {source!s}",
            f"Inspect destination parent: ls -ldOe@ {destination_parent!s}",
        ]
    )


def _can_access(path: Path, mode: int) -> bool:
    try:
        return os.access(path, mode)
    except OSError:
        return False


def _path_flags(path: Path) -> str:
    try:
        flags = getattr(path.stat(), "st_flags", 0)
    except OSError:
        return "unavailable"
    if not flags:
        return "none"
    names = [
        name.lower()
        for name in ("UF_IMMUTABLE", "UF_APPEND", "SF_IMMUTABLE", "SF_APPEND", "UF_HIDDEN")
        if (value := getattr(stat, name, 0)) and flags & value
    ]
    return ", ".join(names) if names else str(flags)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _create_destination_parent(destination: Path, archive_root: Path) -> list[Path]:
    ensure_archive_destination(destination, archive_root)
    archive_resolved = absolute_lexical_path(archive_root)
    parent = absolute_lexical_path(destination.parent)
    created_dirs: list[Path] = []
    current = archive_resolved
    descriptor = open_directory(archive_resolved)
    try:
        for part in parent.relative_to(archive_resolved).parts:
            current /= part
            try:
                os.mkdir(part, dir_fd=descriptor)
                os.fsync(descriptor)
                created_dirs.append(current)
            except FileExistsError:
                pass
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        require_directory_path(parent, descriptor)
        return created_dirs
    finally:
        os.close(descriptor)


def _open_created_date_dirs(created_dirs: list[Path]) -> list[tuple[Path, int]]:
    opened = []
    for directory in created_dirs:
        if date_folder_timestamp(directory.name) is not None:
            try:
                opened.append((directory, open_directory(directory)))
            except Exception:
                for _, descriptor in opened:
                    os.close(descriptor)
                raise
    return opened


def _timestamp_created_date_dirs(created_dirs: list[tuple[Path, int]]) -> None:
    for directory, descriptor in created_dirs:
        timestamp = date_folder_timestamp(directory.name)
        require_directory_path(directory, descriptor)
        os.utime(descriptor, (timestamp, timestamp))
        os.fsync(descriptor)
