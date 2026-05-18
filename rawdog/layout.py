# Author: Nicholas Corrieri

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rawdog.inventory import InventoryItem, scan_raw_files

CAMERA_DUMP_PARTS = {
    "dcim",
    "private",
    "misc",
    "canon",
    "nikon",
    "sony",
    "fujifilm",
    "fuji",
    "gopro",
    "100canon",
    "101canon",
    "100eos",
    "101eos",
    "100msdcf",
}
CAMERA_DUMP_FOLDER_RE = re.compile(
    r"^(\d{3}(canon|eos|eosr\d*|msdcf|nikon|sony|fuji|fujif|gopro)|"
    r"\d{3}[a-z0-9]{3,}|"
    r"(eosr\d+|nikon|sony|canon|fujifilm|fuji|gopro))$",
    re.IGNORECASE,
)

CAMERA_FILENAME_RE = re.compile(
    r"^(img|dsc|dscf|dscn|_dsc|r\d{3}|c\d{4}|mvi|gh\d|gopr|g\d{6})[_-]?\d+",
    re.IGNORECASE,
)
DATE_FOLDER_RE = re.compile(
    r"(^|[^0-9])("
    r"(19|20)\d{2}[-_. ]?\d{2}[-_. ]?\d{2}|"
    r"(19|20)\d{2}[-_. ]?\d{2}|"
    r"\d{2}[-_. ]?\d{2}[-_. ]?(19|20)\d{2}"
    r")($|[^0-9])"
)
PROJECT_WORD_RE = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class LayoutAnalysis:
    source_root: Path
    file_count: int
    raw_dump_files: int
    organized_files: int
    recommendation: str
    confidence: int
    signals: list[str] = field(default_factory=list)

    @property
    def needs_operator_confirmation(self) -> bool:
        return True


def analyze_source_layout(
    root: Path,
    *,
    exclude_roots: list[Path] | None = None,
    limit: int | None = None,
) -> LayoutAnalysis:
    items = scan_raw_files(root, exclude_roots=exclude_roots, limit=limit)
    if not items:
        return LayoutAnalysis(
            source_root=root,
            file_count=0,
            raw_dump_files=0,
            organized_files=0,
            recommendation="empty",
            confidence=100,
            signals=["No RAW files found."],
        )
    raw_dump_files = sum(1 for item in items if _looks_like_camera_dump(item))
    organized_files = sum(1 for item in items if _looks_organized(item))
    raw_ratio = raw_dump_files / len(items)
    organized_ratio = organized_files / len(items)
    folders = Counter(str(item.relative_path.parent) for item in items)
    signals: list[str] = [
        f"{len(items)} RAW files scanned.",
        f"{raw_dump_files} files look like camera-dump layout.",
        f"{organized_files} files look semi-organized.",
        f"{len(folders)} folders contain RAW files.",
    ]
    if folders:
        largest_folder_count = folders.most_common(1)[0][1]
        largest_ratio = largest_folder_count / len(items)
        if largest_ratio > 0.7:
            signals.append("Most files are concentrated in one folder.")
    if organized_ratio >= 0.55:
        return LayoutAnalysis(
            source_root=root,
            file_count=len(items),
            raw_dump_files=raw_dump_files,
            organized_files=organized_files,
            recommendation="keep-existing",
            confidence=min(95, 55 + round(organized_ratio * 40)),
            signals=signals,
        )
    if raw_ratio >= 0.55:
        return LayoutAnalysis(
            source_root=root,
            file_count=len(items),
            raw_dump_files=raw_dump_files,
            organized_files=organized_files,
            recommendation="ddd",
            confidence=min(95, 55 + round(raw_ratio * 40)),
            signals=signals,
        )
    return LayoutAnalysis(
        source_root=root,
        file_count=len(items),
        raw_dump_files=raw_dump_files,
        organized_files=organized_files,
        recommendation="mixed-review",
        confidence=50,
        signals=signals + ["Mixed layout needs operator review before copy."],
    )


def _looks_like_camera_dump(item: InventoryItem) -> bool:
    if any(_is_camera_dump_part(part) for part in item.relative_path.parts[:-1]):
        return True
    return bool(CAMERA_FILENAME_RE.match(item.path.stem)) and not _looks_organized(item)


def _looks_organized(item: InventoryItem) -> bool:
    folder_parts = item.relative_path.parts[:-1]
    for part in folder_parts:
        normalized = part.replace("-", " ").replace("_", " ").replace(".", " ")
        if DATE_FOLDER_RE.search(part):
            return True
        if PROJECT_WORD_RE.search(normalized) and not _is_camera_dump_part(part):
            return True
    return False


def _is_camera_dump_part(part: str) -> bool:
    normalized = part.lower()
    return normalized in CAMERA_DUMP_PARTS or bool(CAMERA_DUMP_FOLDER_RE.match(part))
