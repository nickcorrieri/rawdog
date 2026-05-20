# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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

CAMERA_CAPTURE_EXTENSIONS = RAW_EXTENSIONS | CAMERA_VIDEO_EXTENSIONS


def is_raw_file(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTENSIONS


def is_camera_capture_file(path: Path) -> bool:
    return path.suffix.lower() in CAMERA_CAPTURE_EXTENSIONS


def capture_time_fallback(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
