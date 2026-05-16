# Author: Nicholas Corrieri

from __future__ import annotations

from pathlib import Path


def same_name_and_size(source: Path, destination: Path) -> bool:
    return source.name == destination.name and source.stat().st_size == destination.stat().st_size
