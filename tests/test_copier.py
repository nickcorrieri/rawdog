# Author: Nicholas Corrieri

import errno
import os
from datetime import datetime
from pathlib import Path

import pytest

import rawdog.copier as copier
from rawdog.copier import append_only_copy, append_only_move
from rawdog.safety import SafetyError
from rawdog.verifier import capture_file_version, read_ancillary_payloads, set_ancillary_payloads


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
    assert not list(destination.parent.glob(".rawdog-*.partial"))


def test_append_only_copy_reports_progress_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"rawdata")
    destination.parent.mkdir()
    chunks: list[int] = []

    status = append_only_copy(
        source,
        destination,
        tmp_path / "archive",
        progress_callback=chunks.append,
    )

    assert status == "copied"
    assert sum(chunks) == len(b"rawdata")
    assert destination.read_bytes() == b"rawdata"


def test_append_only_copy_attempts_birthtime_preservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(copier, "_preserve_macos_birthtime", lambda src, dst, **kwargs: calls.append((src, dst)))

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "copied"
    assert len(calls) == 1
    assert calls[0][0] == source
    assert calls[0][1].parent == destination.parent
    assert calls[0][1].name.endswith(".partial")


def test_append_only_copy_timestamps_new_date_folders(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    archive = tmp_path / "archive"
    destination = archive / "2025" / "202501" / "source.CR3"
    source.write_bytes(b"raw")
    archive.mkdir()

    status = append_only_copy(source, destination, archive)

    assert status == "copied"
    expected = int(datetime(2025, 1, 1, 0, 0, 1).timestamp())
    assert int((archive / "2025").stat().st_mtime) == expected
    assert int((archive / "2025" / "202501").stat().st_mtime) == expected


def test_append_only_copy_does_not_retimestamp_existing_date_folder(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    archive = tmp_path / "archive"
    existing = archive / "2025"
    destination = existing / "202501" / "source.CR3"
    source.write_bytes(b"raw")
    existing.mkdir(parents=True)
    original_timestamp = datetime(2024, 1, 1, 0, 0, 1).timestamp()
    os.utime(existing, (original_timestamp, original_timestamp))

    status = append_only_copy(source, destination, archive)

    assert status == "copied"
    assert int(existing.stat().st_mtime) != int(datetime(2025, 1, 1, 0, 0, 1).timestamp())


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


def test_append_only_copy_retains_owned_partial_on_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    def fail_copy(source_path: Path, partial_path: Path, **kwargs) -> None:
        partial_path.write_bytes(b"partial")
        raise OSError("copy failed")

    monkeypatch.setattr(copier, "_copy2_with_progress", fail_copy)

    with pytest.raises(OSError):
        append_only_copy(source, destination, tmp_path / "archive")

    assert not destination.with_name(destination.name + ".partial").exists()
    partials = list(destination.parent.glob(".rawdog-*.partial"))
    assert len(partials) == 1
    assert partials[0].read_bytes() == b"partial"
    assert not destination.exists()


def test_append_only_copy_preserves_unowned_matching_partial(tmp_path: Path) -> None:
    source = tmp_path / "source.MP4"
    destination = tmp_path / "archive" / "source.MP4"
    source.write_bytes(b"video")
    destination.parent.mkdir()
    destination.with_name(destination.name + ".partial").write_bytes(b"video")

    status = append_only_copy(source, destination, tmp_path / "archive")

    assert status == "skipped_existing_partial"
    assert not destination.exists()
    assert destination.with_name(destination.name + ".partial").read_bytes() == b"video"


def test_append_only_copy_verifies_bytes_before_final_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.MP4"
    destination = tmp_path / "archive" / "source.MP4"
    source.write_bytes(b"video")
    destination.parent.mkdir()

    def corrupt_copy(source_path: Path, partial_path: Path, **kwargs) -> None:
        partial_path.write_bytes(b"corrupt")

    monkeypatch.setattr(copier, "_copy2_with_progress", corrupt_copy)

    with pytest.raises(SafetyError, match="did not verify"):
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


def test_move_rechecks_held_source_at_native_helper_entry(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.CR3"
    retained = tmp_path / "retained.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    reviewed = capture_file_version(source)
    actual = copier._rename_for_move
    arrivals = []

    def replace_source_at_entry(source_path, destination_path, **kwargs):
        source_path.rename(retained)
        source_path.write_bytes(b"foreign!")
        arrivals.append(True)
        return actual(source_path, destination_path, **kwargs)

    monkeypatch.setattr(copier, "_rename_for_move", replace_source_at_entry)
    with pytest.raises(SafetyError, match="changed"):
        append_only_move(source, destination, destination.parent, expected_source_version=reviewed)
    assert arrivals == [True]
    assert source.read_bytes() == b"foreign!"
    assert retained.read_bytes() == b"original"
    assert not destination.exists()


def test_append_only_move_explains_permission_denied_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / "source.CR3"
    source.write_bytes(b"raw")
    destination.parent.mkdir()

    def fail_rename(source_path: Path, destination_path: Path, **kwargs) -> None:
        raise PermissionError(1, "Operation not permitted", str(source_path), str(destination_path))

    monkeypatch.setattr(copier, "_rename_no_replace", fail_rename)

    with pytest.raises(SafetyError) as exc_info:
        append_only_move(source, destination, tmp_path / "archive")

    message = str(exc_info.value)
    assert "Filesystem refused MOVE rename" in message
    assert f"Source: {source}" in message
    assert f"Destination: {destination}" in message
    assert "Common causes:" in message
    assert "ls -lOe@" in message
    assert source.exists()
    assert not destination.exists()


def test_copy_refuses_source_change_during_progress_callback(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    reviewed = capture_file_version(source)

    def replace_source(_bytes):
        source.write_bytes(b"changed!")

    with pytest.raises(SafetyError, match="changed"):
        append_only_copy(source, destination, destination.parent,
                         progress_callback=replace_source, expected_source_version=reviewed)
    assert source.read_bytes() == b"changed!"
    assert not destination.exists()


@pytest.mark.parametrize("primitive", [append_only_copy, append_only_move])
def test_transfer_refuses_changed_reviewed_version(tmp_path: Path, primitive) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    reviewed = capture_file_version(source)
    source.write_bytes(b"changed!")
    os.utime(source, ns=(source.stat().st_atime_ns, reviewed["mtime_ns"]))
    with pytest.raises(SafetyError, match="changed"):
        primitive(source, destination, destination.parent, expected_source_version=reviewed)
    assert source.read_bytes() == b"changed!"
    assert not destination.exists()


def test_copy_preserves_synthetic_extended_payload(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    descriptor = os.open(source, os.O_RDONLY)
    try:
        set_ancillary_payloads(descriptor, {"user.rawdog.synthetic": b"opaque ancillary payload"})
    finally:
        os.close(descriptor)
    assert append_only_copy(source, destination, destination.parent) == "copied"
    assert source.read_bytes() == destination.read_bytes() == b"original"
    descriptor = os.open(destination, os.O_RDONLY)
    try:
        assert read_ancillary_payloads(descriptor)["user.rawdog.synthetic"] == b"opaque ancillary payload"
    finally:
        os.close(descriptor)


def test_identical_primary_bytes_with_different_ancillary_are_collision(tmp_path: Path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    destination.write_bytes(b"original")
    descriptor = os.open(source, os.O_RDONLY)
    try:
        set_ancillary_payloads(descriptor, {"user.rawdog.synthetic": b"unique source payload"})
    finally:
        os.close(descriptor)
    assert append_only_copy(source, destination, destination.parent) == "skipped_collision"
    descriptor = os.open(source, os.O_RDONLY)
    try:
        assert read_ancillary_payloads(descriptor)["user.rawdog.synthetic"] == b"unique source payload"
    finally:
        os.close(descriptor)
    assert source.read_bytes() == destination.read_bytes() == b"original"


def test_unqualified_native_transfer_fails_before_creating_partial(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    monkeypatch.setattr(copier.sys, "platform", "win32")
    with pytest.raises(SafetyError, match="not qualified"):
        append_only_copy(source, destination, destination.parent)
    assert source.read_bytes() == b"original"
    assert list(destination.parent.iterdir()) == []


def test_copy_native_entry_preserves_foreign_replacement_of_owned_partial(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    actual = copier._rename_no_replace
    replacements = []

    def replace_partial(partial, target, **kwargs):
        retained = partial.with_name(partial.name + ".retained")
        partial.rename(retained)
        partial.write_bytes(b"foreign!")
        replacements.append((partial, retained))
        return actual(partial, target, **kwargs)

    monkeypatch.setattr(copier, "_rename_no_replace", replace_partial)
    with pytest.raises(SafetyError, match="changed"):
        append_only_copy(source, destination, destination.parent)
    assert len(replacements) == 1
    partial, retained = replacements[0]
    assert partial.read_bytes() == b"foreign!"
    assert retained.read_bytes() == b"original"
    assert source.read_bytes() == b"original"
    assert not destination.exists()


@pytest.mark.parametrize("primitive", [append_only_copy, append_only_move], ids=["copy", "move"])
def test_transfer_preserves_competing_destination_at_native_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primitive,
) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "archive" / source.name
    source.write_bytes(b"original")
    destination.parent.mkdir()
    reviewed = capture_file_version(source)
    actual = copier._rename_no_replace
    publications = []
    competitor_versions = []

    def insert_competitor(publication_source, target, **kwargs):
        publications.append((publication_source, capture_file_version(publication_source)))
        with target.open("xb") as handle:
            handle.write(b"competitor")
        competitor_versions.append(capture_file_version(target))
        # Synchronize at helper entry and call the real native no-replace path.
        # This does not exercise an arbitrary concurrent writer/syscall race.
        return actual(publication_source, target, **kwargs)

    def forbid_replacing_fallback(*args, **kwargs):
        raise AssertionError("transfer attempted a replacing rename fallback")

    with monkeypatch.context() as scoped:
        scoped.setattr(copier, "_rename_no_replace", insert_competitor)
        scoped.setattr(os, "rename", forbid_replacing_fallback)
        scoped.setattr(os, "replace", forbid_replacing_fallback)
        with pytest.raises(OSError) as caught:
            primitive(source, destination, destination.parent, expected_source_version=reviewed)

    assert caught.value.errno == errno.EEXIST
    assert len(publications) == len(competitor_versions) == 1
    assert source.read_bytes() == b"original"
    assert capture_file_version(source) == reviewed
    assert destination.read_bytes() == b"competitor"
    assert capture_file_version(destination) == competitor_versions[0]
    publication_source, publication_version = publications[0]
    assert capture_file_version(publication_source) == publication_version
