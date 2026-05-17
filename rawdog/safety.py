# Author: Nicholas Corrieri

from __future__ import annotations

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
    working = working_root.expanduser().resolve()
    archive = archive_root.expanduser().resolve()
    if working == archive:
        raise SafetyError("working_root and archive_root must be different paths")


def ensure_existing_directory(path: Path, label: str) -> None:
    resolved = path.expanduser()
    if not resolved.exists():
        raise SafetyError(f"{label} does not exist: {path}")
    if not resolved.is_dir():
        raise SafetyError(f"{label} must be a directory: {path}")


def ensure_import_roots(source_root: Path, destination_root: Path) -> None:
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
    source = source_root.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    if source == destination:
        raise SafetyError("source and destination must be different paths")
    if source in destination.parents and not allow_destination_inside_source:
        raise SafetyError("destination cannot be inside source")


def ensure_same_filesystem(source: Path, destination_root: Path) -> None:
    source_device = source.expanduser().resolve().stat().st_dev
    destination_device = destination_root.expanduser().resolve().stat().st_dev
    if source_device != destination_device:
        raise SafetyError("move is only allowed when source and destination are on the same filesystem")


def ensure_archive_destination(destination: Path, archive_root: Path) -> None:
    destination_resolved = destination.expanduser().resolve()
    archive_resolved = archive_root.expanduser().resolve()
    if destination_resolved != archive_resolved and archive_resolved not in destination_resolved.parents:
        raise SafetyError("destination must be inside archive_root")


def ensure_no_overwrite(destination: Path) -> None:
    if destination.exists():
        raise SafetyError(f"refusing to overwrite existing archive file: {destination}")
