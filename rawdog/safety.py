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
    found = sorted(FORBIDDEN_ARGUMENTS.intersection(args))
    if found:
        joined = ", ".join(found)
        raise SafetyError(f"RAWDOG does not support destructive arguments: {joined}")


def ensure_distinct_roots(working_root: Path, archive_root: Path) -> None:
    working = working_root.expanduser().resolve()
    archive = archive_root.expanduser().resolve()
    if working == archive:
        raise SafetyError("working_root and archive_root must be different paths")


def ensure_archive_destination(destination: Path, archive_root: Path) -> None:
    destination_resolved = destination.expanduser().resolve()
    archive_resolved = archive_root.expanduser().resolve()
    if destination_resolved != archive_resolved and archive_resolved not in destination_resolved.parents:
        raise SafetyError("destination must be inside archive_root")


def ensure_no_overwrite(destination: Path) -> None:
    if destination.exists():
        raise SafetyError(f"refusing to overwrite existing archive file: {destination}")
