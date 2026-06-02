# Author: Nicholas Corrieri

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from rawdog.models import DestinationFilenamePolicy
from rawdog.planner import slug_folder_name

CAPTURE_PREFIX_RE = re.compile(r"^(?:19|20)\d{6}-\d{6}-\d{1,9}__")
IDENTITY_PREFIX_RE = re.compile(r"^(?:H[0-9a-fA-F]{8,16}|U[0-9a-fA-F]{8,32})__")
RAWDOG_TIMESTAMP_PREFIX_RE = re.compile(r"^((?:19|20)\d{6}-\d{6}-\d{1,9})__")
RAWDOG_TIMESTAMP_SUFFIX_RE = re.compile(r"__((?:19|20)\d{6}-\d{6}-\d{1,9})(?:__.*)?$")
CAPTURE_SUFFIX_RE = re.compile(
    r"("
    r"__(?:19|20)\d{6}-\d{6}-\d{1,9}(?:__[A-Za-z0-9][A-Za-z0-9._-]*)?(?:__\d+)?|"
    r"__(?:H[0-9a-fA-F]{8,16}|U[0-9a-fA-F]{8,32})(?:__\d+)?|"
    r"_(?:19|20)\d{6}(?:_\d{4}(?:\d{2})?)?(?:_[A-Za-z0-9][A-Za-z0-9._-]*)?(?:_\d+)?"
    r")$"
)


def destination_path_for_filename_policy(
    source_path: Path,
    destination_dir: Path,
    captured_at: datetime,
    *,
    policy: DestinationFilenamePolicy,
    reserved_destinations: set[Path],
    size_bytes: int,
) -> Path:
    if policy == DestinationFilenamePolicy.ORIGINAL:
        return destination_dir / source_path.name

    candidates = _policy_candidates(source_path, captured_at, policy)
    last_candidate = destination_dir / candidates[-1]
    for candidate_name in candidates:
        candidate = destination_dir / candidate_name
        if candidate in reserved_destinations:
            continue
        if not candidate.exists():
            return candidate
        if candidate.is_file() and candidate.stat().st_size == size_bytes:
            return candidate

    for index in range(2, 1000):
        candidate = last_candidate.with_name(f"{last_candidate.stem}__{index:02d}{last_candidate.suffix}")
        if candidate not in reserved_destinations and not candidate.exists():
            return candidate
    return last_candidate


def camera_identity_key(path: Path) -> str:
    return f"{strip_capture_suffix(path.stem)}{path.suffix.upper()}"


def strip_capture_suffix(stem: str) -> str:
    stripped = CAPTURE_PREFIX_RE.sub("", stem)
    stripped = IDENTITY_PREFIX_RE.sub("", stripped)
    stripped = CAPTURE_SUFFIX_RE.sub("", stripped).rstrip("_-. ")
    return stripped or stem


def filename_capture_time(path: Path) -> datetime | None:
    stem = path.stem
    match = RAWDOG_TIMESTAMP_PREFIX_RE.search(stem) or RAWDOG_TIMESTAMP_SUFFIX_RE.search(stem)
    if not match:
        return None
    value = match.group(1)
    try:
        base, subsecond = value.rsplit("-", 1)
        captured_at = datetime.strptime(base, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    if not subsecond.isdigit():
        return captured_at
    return captured_at.replace(microsecond=int(subsecond.ljust(6, "0")[:6]))


def _policy_candidates(source_path: Path, captured_at: datetime, policy: DestinationFilenamePolicy) -> list[str]:
    base = strip_capture_suffix(source_path.stem)
    suffix = source_path.suffix
    timestamp_part = captured_at.strftime("%Y%m%d-%H%M%S")
    subsecond_part = f"{captured_at.microsecond // 10_000:02d}"
    capture_key = f"{timestamp_part}-{subsecond_part}"
    if policy == DestinationFilenamePolicy.DATE_ORIGINAL:
        return _date_original_candidates(base, suffix, capture_key, source_path)
    if policy in {DestinationFilenamePolicy.DATE_SUFFIX, DestinationFilenamePolicy.ORIGINAL_DATE}:
        return _original_date_candidates(base, suffix, capture_key, source_path)
    if policy == DestinationFilenamePolicy.ORIGINAL_HASH:
        digest = _short_sha256(source_path)
        return [f"{base}__H{digest}{suffix}"]
    if policy == DestinationFilenamePolicy.ORIGINAL_UNIQUE_ID:
        marker = _short_unique_id_marker(source_path)
        return [f"{base}__{marker}{suffix}"]
    if policy == DestinationFilenamePolicy.UNIQUE_ID_ORIGINAL:
        marker = _short_unique_id_marker(source_path)
        return [f"{marker}__{base}{suffix}"]
    return [source_path.name]


def _date_original_candidates(base: str, suffix: str, capture_key: str, source_path: Path) -> list[str]:
    parent_part = slug_folder_name(source_path.parent.name)[:32]
    return [
        f"{capture_key}__{base}{suffix}",
        f"{capture_key}__{base}__{parent_part}{suffix}",
    ]


def _original_date_candidates(base: str, suffix: str, capture_key: str, source_path: Path) -> list[str]:
    parent_part = slug_folder_name(source_path.parent.name)[:32]
    return [
        f"{base}__{capture_key}{suffix}",
        f"{base}__{capture_key}__{parent_part}{suffix}",
    ]


def _short_sha256(path: Path, *, length: int = 12) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def _short_unique_id_marker(path: Path, *, length: int = 12) -> str:
    unique_id = _image_unique_id(path)
    if unique_id:
        return f"U{unique_id[:length]}"
    return f"H{_short_sha256(path, length=length)}"


def _image_unique_id(path: Path) -> str | None:
    if shutil.which("exiftool") is None:
        return None
    try:
        result = subprocess.run(
            ["exiftool", "-s3", "-ImageUniqueID", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
    if not value or not re.fullmatch(r"[0-9a-fA-F]{8,64}", value):
        return None
    return value.lower()
