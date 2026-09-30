# Author: Nicholas Corrieri

from __future__ import annotations

from pathlib import Path

from rawdog.safety import ensure_no_symlink_components
from rawdog.verifier import verify_same_bytes


def same_name_and_size(source: Path, destination: Path) -> bool:
    ensure_no_symlink_components(source)
    ensure_no_symlink_components(destination)
    return source.name == destination.name and source.stat().st_size == destination.stat().st_size


def same_name_and_content(source: Path, destination: Path) -> bool:
    return source.name == destination.name and verify_same_bytes(source, destination)
