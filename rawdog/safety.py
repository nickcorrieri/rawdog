# Author: Nicholas Corrieri

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


class SafetyError(RuntimeError):
    pass


FORBIDDEN_ARGUMENTS = {
    "--delete",
    "--prune",
    "--cleanup",
    "--fix",
    "--rename",
    "--sync",
}


def reject_dangerous_arguments(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    found = sorted(
        arg
        for arg in args
        if arg in FORBIDDEN_ARGUMENTS
        or any(arg.startswith(f"{forbidden}=") for forbidden in FORBIDDEN_ARGUMENTS)
    )
    if found:
        joined = ", ".join(found)
        raise SafetyError(f"RAWDOG does not support destructive arguments: {joined}")


def ensure_distinct_roots(working_root: Path, archive_root: Path) -> None:
    ensure_no_symlink_components(working_root)
    ensure_no_symlink_components(archive_root)
    working = working_root.expanduser().resolve()
    archive = archive_root.expanduser().resolve()
    if working == archive:
        raise SafetyError("working_root and archive_root must be different paths")


def ensure_existing_directory(path: Path, label: str) -> None:
    ensure_no_symlink_components(path)
    resolved = path.expanduser()
    if not resolved.exists():
        raise SafetyError(f"{label} does not exist: {path}")
    if not resolved.is_dir():
        raise SafetyError(f"{label} must be a directory: {path}")


def ensure_import_roots(source_root: Path, destination_root: Path) -> None:
    ensure_no_symlink_components(source_root)
    ensure_no_symlink_components(destination_root)
    source = source_root.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    if source == destination:
        raise SafetyError("source and destination must be different paths")
    if destination in source.parents:
        raise SafetyError("destination cannot be an ancestor of source")
    if source in destination.parents:
        raise SafetyError("destination cannot be inside source")


def ensure_consolidation_roots(
    source_root: Path,
    destination_root: Path,
    *,
    allow_destination_inside_source: bool = False,
) -> None:
    ensure_no_symlink_components(source_root)
    ensure_no_symlink_components(destination_root)
    source = source_root.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    if source == destination:
        raise SafetyError("source and destination must be different paths")
    if source in destination.parents and not allow_destination_inside_source:
        raise SafetyError("destination cannot be inside source")


def ensure_same_filesystem(source: Path, destination_root: Path) -> None:
    ensure_no_symlink_components(source)
    ensure_no_symlink_components(destination_root)
    source_device = absolute_lexical_path(source).stat().st_dev
    destination_device = absolute_lexical_path(destination_root).stat().st_dev
    if source_device != destination_device:
        raise SafetyError("move is only allowed when source and destination are on the same filesystem")


def ensure_archive_destination(destination: Path, archive_root: Path) -> None:
    ensure_no_symlink_components(destination)
    ensure_no_symlink_components(archive_root)
    destination_resolved = absolute_lexical_path(destination)
    archive_resolved = absolute_lexical_path(archive_root)
    if destination_resolved != archive_resolved and archive_resolved not in destination_resolved.parents:
        raise SafetyError("destination must be inside archive_root")


def ensure_no_overwrite(destination: Path) -> None:
    if os.path.lexists(destination):
        raise SafetyError(f"refusing to overwrite existing archive file: {destination}")


def absolute_lexical_path(path: Path) -> Path:
    expanded = path.expanduser()
    if ".." in expanded.parts:
        raise SafetyError(f"parent traversal is not an authorized file path: {path}")
    return Path(os.path.abspath(expanded))


def ensure_no_symlink_components(path: Path) -> None:
    """Inspect the selected spelling before resolution erases symlinks."""
    absolute = absolute_lexical_path(path)
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:]):
        current /= part
        try:
            observed = current.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(observed.st_mode):
            raise SafetyError(f"symlink path component is not authorized: {current}")
        if index < len(absolute.parts) - 2 and not stat.S_ISDIR(observed.st_mode):
            raise SafetyError(f"non-directory path component: {current}")


def open_directory(path: Path) -> int:
    """Pin a directory without resolving any symlink component."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise SafetyError("descriptor-relative no-follow filesystem access is unsupported")
    absolute = absolute_lexical_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if sys.platform == "darwin":
        # macOS SDK sys/fcntl.h: O_NOFOLLOW_ANY. The kernel checks every
        # component without needing read handles to unrelated ancestors.
        # XNU vn_open_auth rejects combining O_NOFOLLOW_ANY and O_NOFOLLOW.
        return os.open(absolute, (flags & ~os.O_NOFOLLOW) | 0x20000000)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def require_directory_path(path: Path, descriptor: int) -> None:
    ensure_no_symlink_components(path)
    observed = path.lstat()
    pinned = os.fstat(descriptor)
    if (observed.st_dev, observed.st_ino) != (pinned.st_dev, pinned.st_ino):
        raise SafetyError(f"directory changed during operation: {path}")
