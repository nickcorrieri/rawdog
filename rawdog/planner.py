# Author: Nicholas Corrieri

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from rawdog.models import Project


class TemplateError(ValueError):
    pass


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
    project_name = slug_folder_name(project.name if project else "Date_Only")
    client_name = slug_folder_name(project.client_name if project and project.client_name else "No_Client")
    replacements = {
        "YYYY": f"{captured_at.year:04d}",
        "YYYYMMDD": captured_at.strftime("%Y%m%d"),
        "YYYY-MM-DD": captured_at.strftime("%Y-%m-%d"),
        "YYYY-MM": captured_at.strftime("%Y-%m"),
        "MM-Month": captured_at.strftime("%m-%B"),
        "PROJECT": project_name,
        "CLIENT": client_name,
    }
    rendered = template
    for token in sorted(replacements, key=len, reverse=True):
        rendered = rendered.replace(token, replacements[token])
    rendered_path = Path(rendered)
    if rendered_path.is_absolute() or any(part == ".." for part in rendered_path.parts):
        raise TemplateError("folder template must render to a relative path inside the destination")
    return rendered_path


def slug_folder_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("._-")
    return normalized or "Untitled"


def default_project_destination(
    destination_root: Path,
    project_name: str,
    earliest_capture_at: datetime,
    template: str = "YYYY/YYYYMMDD_PROJECT",
) -> Path:
    class _Project:
        name = project_name
        client_name = None

    return destination_root / render_folder_template(template, earliest_capture_at, _Project())


def default_date_only_destination(
    destination_root: Path,
    captured_at: datetime,
    template: str = "YYYY/YYYY-MM",
) -> Path:
    return destination_root / render_folder_template(template, captured_at)


def plan_append_only_copy(source_path: Path, destination_path: Path) -> PlannedCopy | None:
    if destination_path.exists():
        source_stat = source_path.stat()
        destination_stat = destination_path.stat()
        if source_stat.st_size == destination_stat.st_size:
            return None
        return None
    return PlannedCopy(source_path=source_path, destination_path=destination_path, reason="missing")
