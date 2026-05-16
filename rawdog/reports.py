# Author: Nicholas Corrieri

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def write_copy_size_estimate(path: Path, rows: Iterable[dict[str, object]]) -> Path:
    return write_csv(
        path,
        ["year", "files_to_copy", "total_bytes", "estimated_gb"],
        rows,
    )
