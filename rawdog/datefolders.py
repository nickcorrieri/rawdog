# Author: Nicholas Corrieri

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateFolderMatch:
    original: str
    normalized: str


DATE_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})$"),
    re.compile(r"^(?P<year>\d{4})[._-](?P<month>\d{2})[._-](?P<day>\d{2})$"),
    re.compile(r"^(?P<month>\d{2})(?P<day>\d{2})(?P<year>\d{4})$"),
    re.compile(r"^(?P<month>\d{2})[._-](?P<day>\d{2})[._-](?P<year>\d{4})$"),
]


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
            return None
        return DateFolderMatch(original=value, normalized=parsed.strftime("%Y%m%d"))
    return None


def normalize_date_folder_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        match = normalize_date_folder_name(part)
        normalized.append(match.normalized if match else part)
    return tuple(normalized)
