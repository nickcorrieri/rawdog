# Author: Nicholas Corrieri

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rawdog.models import Project


@dataclass(frozen=True)
class PlannedCopy:
    source_path: Path
    destination_path: Path
    reason: str
    project_id: int | None = None


def render_folder_template(
    template: str,
    captured_at: datetime,
    project: Project | None = None,
) -> Path:
    project_name = project.name if project else "Date_Only"
    client_name = project.client_name if project and project.client_name else "No_Client"
    replacements = {
        "YYYY": f"{captured_at.year:04d}",
        "YYYY-MM-DD": captured_at.strftime("%Y-%m-%d"),
        "YYYY-MM": captured_at.strftime("%Y-%m"),
        "MM-Month": captured_at.strftime("%m-%B"),
        "PROJECT": project_name,
        "CLIENT": client_name,
    }
    rendered = template
    for token in sorted(replacements, key=len, reverse=True):
        rendered = rendered.replace(token, replacements[token])
    return Path(rendered)


def plan_append_only_copy(source_path: Path, destination_path: Path) -> PlannedCopy | None:
    if destination_path.exists():
        source_stat = source_path.stat()
        destination_stat = destination_path.stat()
        if source_stat.st_size == destination_stat.st_size:
            return None
        return None
    return PlannedCopy(source_path=source_path, destination_path=destination_path, reason="missing")
