# Author: Nicholas Corrieri

import errno
import json
import os
from pathlib import Path

import pytest

from rawdog.db import connect
from rawdog.safety import (
    SafetyError,
    ensure_archive_destination,
    ensure_consolidation_roots,
    ensure_distinct_roots,
    ensure_import_roots,
    open_directory,
    reject_dangerous_arguments,
)
from rawdog.verifier import capture_file_version, require_file_version


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


def test_consolidation_can_explicitly_allow_destination_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = source / "archive"
    destination.mkdir(parents=True)

    ensure_consolidation_roots(source, destination, allow_destination_inside_source=True)


def test_migration_helper_rejects_unsafe_identifiers(tmp_path: Path) -> None:
    connection = connect(tmp_path / "rawdog.sqlite")
    try:
        with pytest.raises(ValueError):
            from rawdog.db import _add_column_if_missing

            _add_column_if_missing(connection, "projects;drop", "bad", "TEXT")
    finally:
        connection.close()


def test_file_version_is_json_safe_and_detects_same_size_restored_mtime(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    source.write_bytes(b"original")
    reviewed = capture_file_version(source)
    assert json.loads(json.dumps(reviewed)) == reviewed
    source.write_bytes(b"changed!")
    os.utime(source, ns=(source.stat().st_atime_ns, reviewed["mtime_ns"]))
    with pytest.raises(SafetyError, match="changed"):
        require_file_version(source, reviewed)
    assert source.read_bytes() == b"changed!"


def test_file_version_rejects_parent_symlink_before_reading(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    source = outside / "source.CR3"
    source.write_bytes(b"original")
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SafetyError, match="symlink"):
        capture_file_version(alias / source.name)
    assert source.read_bytes() == b"original"


def test_native_directory_open_pins_selected_directory(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    descriptor = open_directory(selected)
    try:
        pinned = os.fstat(descriptor)
        observed = selected.stat()
        assert (pinned.st_dev, pinned.st_ino) == (observed.st_dev, observed.st_ino)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("alias_kind", ["selected", "ancestor"])
def test_native_directory_open_rejects_symlinks_without_precheck(tmp_path: Path, alias_kind) -> None:
    outside = tmp_path / "outside"
    nested = outside / "nested"
    nested.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    selected = alias if alias_kind == "selected" else alias / "nested"
    with pytest.raises(OSError) as caught:
        open_directory(selected)
    assert caught.value.errno in {errno.ELOOP, errno.ENOTDIR}
    assert list(outside.iterdir()) == [nested]
