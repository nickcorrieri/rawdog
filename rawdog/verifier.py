# Author: Nicholas Corrieri

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_same_bytes(source: Path, destination: Path) -> bool:
    if source.stat().st_size != destination.stat().st_size:
        return False
    return sha256_file(source) == sha256_file(destination)
