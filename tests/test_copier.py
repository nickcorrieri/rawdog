# Author: Nicholas Corrieri

import shutil
from pathlib import Path

import pytest

from rawdog.copier import append_only_copy, append_only_move
from rawdog.safety import SafetyError


def test_append_only_copy_dry_run_creates_no_files(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    status = append_only_copy(source, destination, tmp_path / "archive", dry_run=True)

    assert status == "planned"
    assert not destination.exists()


def test_append_only_copy_success_removes_partial(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "copied"
    assert destination.read_bytes() == b"raw"
    assert not destination.with_name(destination.name + ".partial").exists()


def test_append_only_copy_skips_same_name_and_size(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()
    destination.write_bytes(b"raw")

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "skipped_existing_same_name_size"


def test_append_only_copy_reports_collision(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()
    destination.write_bytes(b"different")

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "skipped_collision"


def test_append_only_copy_reports_existing_partial_for_review(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()
    destination.with_name(destination.name + ".partial").write_bytes(b"partial")

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "skipped_existing_partial"
    assert not destination.exists()


def test_append_only_copy_removes_current_partial_on_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    def fail_copy(source_path: Path, partial_path: Path) -> None:
        partial_path.write_bytes(b"partial")
        raise OSError("copy failed")

    monkeypatch.setattr(shutil, "copy2", fail_copy)

    with pytest.raises(OSError):
        append_only_copy(source, destination, tmp_path / "archive")

    assert not destination.with_name(destination.name + ".partial").exists()
    assert not destination.exists()


def test_append_only_copy_refuses_outside_archive_root(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "outside" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    with pytest.raises(SafetyError):
        append_only_copy(source, destination, tmp_path / "archive")


def test_append_only_move_renames_unique_file_same_filesystem(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    status = append_only_move(source, destination, tmp_path / "archive")

    assert status == "moved"
    assert not source.exists()
    assert destination.read_bytes() == b"raw"


def test_append_only_move_refuses_existing_collision(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()
    destination.write_bytes(b"different")

    status = append_only_move(source, destination, tmp_path / "archive")

    assert status == "skipped_collision"
    assert source.exists()
