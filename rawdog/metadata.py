# Author: Nicholas Corrieri

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RAW_EXTENSIONS = {
    ".3fr",
    ".arw",
    ".cr2",
    ".cr3",
    ".dng",
    ".erf",
    ".fff",
    ".iiq",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rw2",
    ".rwl",
    ".sr2",
    ".srf",
    ".x3f",
}

CAMERA_VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".braw",
    ".crm",
    ".insv",
    ".m2ts",
    ".m4v",
    ".mod",
    ".mov",
    ".mp4",
    ".mts",
    ".mxf",
    ".r3d",
    ".tod",
}

CAMERA_JPEG_EXTENSIONS = {
    ".jpeg",
    ".jpg",
}

CAMERA_CAPTURE_EXTENSIONS = RAW_EXTENSIONS | CAMERA_VIDEO_EXTENSIONS | CAMERA_JPEG_EXTENSIONS

EXIF_CAPTURE_TAGS = (
    "SubSecDateTimeOriginal",
    "DateTimeOriginal",
    "SubSecCreateDate",
    "CreateDate",
    "CreationDate",
    "MediaCreateDate",
    "TrackCreateDate",
)

EXIF_DATETIME_RE = re.compile(
    r"^(?P<year>\d{4})[:-](?P<month>\d{2})[:-](?P<day>\d{2})[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.(?P<subsecond>\d+))?"
    r"(?:\s*(?P<tz>Z|[+-]\d{2}:?\d{2}|[A-Za-z_]+/[A-Za-z_]+))?"
)


def is_raw_file(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTENSIONS


def is_camera_capture_file(path: Path) -> bool:
    return path.suffix.lower() in CAMERA_CAPTURE_EXTENSIONS


def has_media_metadata_reader() -> bool:
    return shutil.which("exiftool") is not None


def media_capture_time(path: Path) -> datetime | None:
    """Return embedded camera capture time, when the asset exposes one."""
    return _capture_time_from_tags(_read_exiftool_tags(path))


def filesystem_capture_time(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def capture_time(path: Path) -> datetime:
    return media_capture_time(path) or filesystem_capture_time(path)


def capture_time_fallback(path: Path) -> datetime:
    return capture_time(path)


def capture_times(paths: list[Path] | tuple[Path, ...]) -> dict[Path, datetime]:
    media_times = media_capture_times(paths)
    return {path: media_times.get(path) or filesystem_capture_time(path) for path in paths}


def media_capture_times(paths: list[Path] | tuple[Path, ...]) -> dict[Path, datetime]:
    tags_by_path = _read_exiftool_tags_for_paths(paths)
    captured: dict[Path, datetime] = {}
    for path, tags in tags_by_path.items():
        captured_at = _capture_time_from_tags(tags)
        if captured_at is not None:
            captured[path] = captured_at
    return captured


def _capture_time_from_tags(tags: dict[str, object]) -> datetime | None:
    for tag in EXIF_CAPTURE_TAGS:
        captured_at = _parse_exif_datetime(tags.get(tag))
        if captured_at is not None:
            return captured_at
    return None


def _read_exiftool_tags(path: Path) -> dict[str, object]:
    return _read_exiftool_tags_for_paths((path,)).get(path, {})


def _read_exiftool_tags_for_paths(paths: list[Path] | tuple[Path, ...]) -> dict[Path, dict[str, object]]:
    if not paths or not has_media_metadata_reader():
        return {}
    requested = {_path_key(path): path for path in paths}
    tags_by_path: dict[Path, dict[str, object]] = {}
    for chunk in _chunks(tuple(paths), 100):
        try:
            result = subprocess.run(
                ["exiftool", "-json", *[f"-{tag}" for tag in EXIF_CAPTURE_TAGS], *[str(path) for path in chunk]],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if not result.stdout.strip():
            continue
        try:
            records = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            source_file = record.get("SourceFile")
            if not isinstance(source_file, str):
                continue
            path = requested.get(_path_key(Path(source_file)))
            if path is not None:
                tags_by_path[path] = record
    return tags_by_path


def _parse_exif_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.startswith("0000:00:00"):
        return None
    match = EXIF_DATETIME_RE.match(raw)
    if not match:
        return None
    parts = match.groupdict()
    try:
        microsecond = int((parts.get("subsecond") or "0").ljust(6, "0")[:6])
        captured_at = datetime(
            int(parts["year"]),
            int(parts["month"]),
            int(parts["day"]),
            int(parts["hour"]),
            int(parts["minute"]),
            int(parts["second"]),
            microsecond,
        )
    except ValueError:
        return None
    timezone = _parse_timezone(parts.get("tz"))
    return captured_at.replace(tzinfo=timezone or UTC)


def _parse_timezone(value: str | None):
    if not value:
        return None
    if value == "Z":
        return UTC
    if "/" in value:
        try:
            return ZoneInfo(value)
        except Exception:
            return None
    cleaned = value.replace(":", "")
    sign = 1 if cleaned[0] == "+" else -1
    try:
        hours = int(cleaned[1:3])
        minutes = int(cleaned[3:5])
    except ValueError:
        return None
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _chunks(paths: tuple[Path, ...], size: int):
    for index in range(0, len(paths), size):
        yield paths[index:index + size]


def _path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser())
