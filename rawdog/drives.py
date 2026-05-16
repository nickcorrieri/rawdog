# Author: Nicholas Corrieri

from __future__ import annotations

from pathlib import Path


def connected_roots(candidates: list[Path]) -> list[Path]:
    return [path.expanduser().resolve() for path in candidates if path.expanduser().exists()]


def standard_path_choices() -> list[tuple[str, Path]]:
    home = Path.home()
    choices = [
        ("Documents", home / "Documents"),
        ("Desktop", home / "Desktop"),
        ("Downloads", home / "Downloads"),
    ]
    volumes = Path("/Volumes")
    if volumes.exists():
        for volume in sorted(path for path in volumes.iterdir() if path.is_dir()):
            choices.append((f"Volume: {volume.name}", volume))
    return choices


def parse_user_path(value: str) -> Path:
    return Path(value).expanduser()
