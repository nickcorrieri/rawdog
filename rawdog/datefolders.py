# Author: Nicholas Corrieri

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class DateFolderMatch:
    original: str
    normalized: str


DATE_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<label>.*)$"),
    re.compile(
        r"^(?P<year>\d{4})[._-](?P<month>\d{2})[._-](?P<day>\d{2})(?P<label>.*)$"
    ),
    re.compile(r"^(?P<month>\d{2})(?P<day>\d{2})(?P<year>\d{4})(?P<label>.*)$"),
    re.compile(
        r"^(?P<month>\d{2})[._-](?P<day>\d{2})[._-](?P<year>\d{4})(?P<label>.*)$"
    ),
]

YEAR_MONTH_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<label>.*)$"),
    re.compile(r"^(?P<year>\d{4})[._-](?P<month>\d{2})(?P<label>.*)$"),
]

YEAR_PATTERN = re.compile(r"^(?P<year>\d{4})(?P<label>.*)$")


def normalize_date_folder_name(value: str) -> DateFolderMatch | None:
    for pattern in DATE_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        try:
            parsed = date(year, month, day)
        except ValueError:
            continue
        label = _normalize_label_suffix(match.group("label") or "")
        return DateFolderMatch(original=value, normalized=f"{parsed:%Y%m%d}{label}")
    return None


def date_folder_timestamp(value: str) -> float | None:
    parsed = _parse_date_folder_datetime(value)
    if parsed is None:
        return None
    return parsed.timestamp()


def _parse_date_folder_datetime(value: str) -> datetime | None:
    for pattern in DATE_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        parsed = _parse_datetime_parts(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
        if parsed is not None:
            return parsed
    for pattern in YEAR_MONTH_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        parsed = _parse_datetime_parts(int(match.group("year")), int(match.group("month")), 1)
        if parsed is not None:
            return parsed
    match = YEAR_PATTERN.match(value)
    if match:
        return _parse_datetime_parts(int(match.group("year")), 1, 1)
    return None


def _parse_datetime_parts(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day, 0, 0, 1)
    except ValueError:
        return None


def _normalize_label_suffix(value: str) -> str:
    if not value:
        return ""
    label = value.strip()
    label = re.sub(r"^[\s._-]+", "", label)
    if not label:
        return ""
    return f"_{label}"


def normalize_date_folder_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        match = normalize_date_folder_name(part)
        normalized.append(match.normalized if match else part)
    return tuple(normalized)
