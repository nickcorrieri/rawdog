# Author: Nicholas Corrieri

from __future__ import annotations

from pathlib import Path


def connected_roots(candidates: list[Path]) -> list[Path]:
    return [path.expanduser().resolve() for path in candidates if path.expanduser().exists()]
