# Author: Nicholas Corrieri

from pathlib import Path

import pytest

from rawdog.safety import (
    SafetyError,
    ensure_archive_destination,
    ensure_consolidation_roots,
    ensure_distinct_roots,
    ensure_import_roots,
    reject_dangerous_arguments,
)


def test_rejects_destructive_arguments() -> None:
    with pytest.raises(SafetyError):
        reject_dangerous_arguments(["breed", "--delete"])


def test_rejects_destructive_arguments_with_values() -> None:
    with pytest.raises(SafetyError):
        reject_dangerous_arguments(["breed", "--delete=true"])


def test_distinct_roots_required(tmp_path: Path) -> None:
    with pytest.raises(SafetyError):
        ensure_distinct_roots(tmp_path, tmp_path)


def test_archive_destination_must_be_inside_archive_root(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    outside = tmp_path / "outside" / "file.nef"
    with pytest.raises(SafetyError):
        ensure_archive_destination(outside, archive)


def test_import_destination_cannot_be_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = source / "working"
    source.mkdir()

    with pytest.raises(SafetyError):
        ensure_import_roots(source, destination)


def test_consolidation_allows_destination_as_source_parent(tmp_path: Path) -> None:
    destination = tmp_path / "archive"
    source = destination / "OldMess"
    source.mkdir(parents=True)

    ensure_consolidation_roots(source, destination)


def test_consolidation_destination_cannot_be_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = source / "archive"
    source.mkdir()

    with pytest.raises(SafetyError):
        ensure_consolidation_roots(source, destination)
