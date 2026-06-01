# Author: Nicholas Corrieri

import os
from datetime import UTC, datetime
from pathlib import Path

from rawdog import metadata
from rawdog.inventory import earliest_raw_capture_time, scan_raw_files
from rawdog.metadata import is_camera_capture_file, is_raw_file


def test_scan_raw_files_ignores_partial_artifacts(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "IMG_0002.CR3.partial").write_bytes(b"partial")

    items = scan_raw_files(tmp_path)

    assert [item.path.name for item in items] == ["IMG_0001.CR3"]


def test_raw_extension_is_case_insensitive() -> None:
    assert is_raw_file(Path("IMG_0001.NEF"))
    assert is_raw_file(Path("IMG_0001.nef"))
    assert not is_raw_file(Path("IMG_0001.NEF.partial"))


def test_camera_video_extensions_are_camera_capture_files() -> None:
    assert not is_raw_file(Path("MVI_0001.MP4"))
    assert is_camera_capture_file(Path("MVI_0001.MP4"))
    assert is_camera_capture_file(Path("C0001.MXF"))
    assert is_camera_capture_file(Path("PRIVATE/AVCHD/BDMV/STREAM/00001.MTS"))
    assert not is_camera_capture_file(Path("MVI_0001.MP4.partial"))


def test_camera_jpeg_extensions_are_camera_capture_files() -> None:
    assert not is_raw_file(Path("IMG_0001.JPG"))
    assert is_camera_capture_file(Path("IMG_0001.JPG"))
    assert is_camera_capture_file(Path("IMG_0001.jpeg"))
    assert not is_camera_capture_file(Path("IMG_0001.JPG.partial"))


def test_scan_raw_files_includes_camera_video_files(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "MVI_0001.MP4").write_bytes(b"movie")
    (tmp_path / "PRIVATE" / "AVCHD" / "BDMV" / "STREAM").mkdir(parents=True)
    (tmp_path / "PRIVATE" / "AVCHD" / "BDMV" / "STREAM" / "00001.MTS").write_bytes(b"avchd")

    items = scan_raw_files(tmp_path)

    assert [item.relative_path for item in items] == [
        Path("IMG_0001.CR3"),
        Path("MVI_0001.MP4"),
        Path("PRIVATE/AVCHD/BDMV/STREAM/00001.MTS"),
    ]


def test_scan_raw_files_includes_camera_jpeg_files(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "IMG_0001.JPG").write_bytes(b"jpeg")
    (tmp_path / "._IMG_0001.JPG").write_bytes(b"appledouble")

    items = scan_raw_files(tmp_path)

    assert [item.relative_path for item in items] == [
        Path("IMG_0001.CR3"),
        Path("IMG_0001.JPG"),
    ]


def test_scan_raw_files_excludes_destination_subtree(tmp_path: Path) -> None:
    (tmp_path / "Old" / "IMG_0001.CR3").parent.mkdir()
    (tmp_path / "Old" / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "Photo_Library" / "IMG_0002.CR3").parent.mkdir()
    (tmp_path / "Photo_Library" / "IMG_0002.CR3").write_bytes(b"archive")

    items = scan_raw_files(tmp_path, exclude_roots=[tmp_path / "Photo_Library"])

    assert [item.relative_path for item in items] == [Path("Old/IMG_0001.CR3")]


def test_scan_raw_files_can_limit_preview(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "IMG_0002.CR3").write_bytes(b"raw")

    items = scan_raw_files(tmp_path, limit=1)

    assert len(items) == 1


def test_scan_raw_files_reports_each_found_item(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "IMG_0002.JPG").write_bytes(b"jpeg")
    seen: list[Path] = []

    items = scan_raw_files(tmp_path, on_item=lambda item: seen.append(item.relative_path))

    assert [item.relative_path for item in items] == [
        Path("IMG_0001.CR3"),
        Path("IMG_0002.JPG"),
    ]
    assert seen == [Path("IMG_0001.CR3"), Path("IMG_0002.JPG")]


def test_earliest_raw_capture_time_prefers_media_capture_date_for_recovered_cr3(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = tmp_path / "LS7A0001.CR3"
    raw.write_bytes(b"recovered cr3")
    project_ts = datetime(2025, 4, 5, tzinfo=UTC).timestamp()
    os.utime(raw, (project_ts, project_ts))
    monkeypatch.setattr(
        metadata,
        "_read_exiftool_tags_for_paths",
        lambda paths: {raw: {"DateTimeOriginal": "2026:05:28 13:40:00"}},
    )

    captured_at = earliest_raw_capture_time(tmp_path)

    assert captured_at == datetime(2026, 5, 28, 13, 40, tzinfo=UTC)
