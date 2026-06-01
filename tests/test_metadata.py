# Author: Nicholas Corrieri

import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from rawdog import metadata
from rawdog.metadata import CAMERA_CAPTURE_EXTENSIONS, capture_time_fallback


def test_capture_time_fallback_is_utc_aware(tmp_path: Path) -> None:
    raw = tmp_path / "IMG_0001.CR3"
    raw.write_bytes(b"raw")

    captured_at = capture_time_fallback(raw)

    assert captured_at.tzinfo == UTC


def test_camera_capture_extensions_include_jpeg() -> None:
    assert ".jpg" in CAMERA_CAPTURE_EXTENSIONS
    assert ".jpeg" in CAMERA_CAPTURE_EXTENSIONS


def test_capture_time_uses_cr3_datetime_original_before_file_mtime(
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

    captured_at = capture_time_fallback(raw)

    assert captured_at == datetime(2026, 5, 28, 13, 40, tzinfo=UTC)


def test_capture_time_uses_create_date_when_datetime_original_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = tmp_path / "LS7A0002.CR3"
    raw.write_bytes(b"recovered cr3")
    monkeypatch.setattr(
        metadata,
        "_read_exiftool_tags_for_paths",
        lambda paths: {raw: {"CreateDate": "2026:05:28 13:41:02.99-05:00"}},
    )

    captured_at = capture_time_fallback(raw)

    assert captured_at == datetime(
        2026,
        5,
        28,
        13,
        41,
        2,
        990000,
        tzinfo=timezone(-timedelta(hours=5)),
    )


def test_capture_time_falls_back_to_filesystem_when_media_date_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = tmp_path / "LS7A0003.CR3"
    raw.write_bytes(b"recovered cr3")
    filesystem_ts = datetime(2026, 5, 28, 13, 40, tzinfo=UTC).timestamp()
    os.utime(raw, (filesystem_ts, filesystem_ts))
    monkeypatch.setattr(metadata, "_read_exiftool_tags_for_paths", lambda paths: {})

    captured_at = capture_time_fallback(raw)

    assert captured_at == datetime(2026, 5, 28, 13, 40, tzinfo=UTC)


def test_media_unique_ids_accepts_progress_callback(tmp_path: Path, monkeypatch) -> None:
    raw = tmp_path / "LS7A0004.CR3"
    raw.write_bytes(b"recovered cr3")
    progress_calls: list[tuple[Path, int, int]] = []

    def on_progress(path: Path, completed: int, total: int) -> None:
        progress_calls.append((path, completed, total))

    def fake_read(paths, **kwargs):
        assert kwargs["tags"] == metadata.EXIF_UNIQUE_ID_TAGS
        assert kwargs["on_progress"] is on_progress
        kwargs["on_progress"](raw, 1, 1)
        return {raw: {"ImageUniqueID": "ABCDEF1234567890"}}

    monkeypatch.setattr(metadata, "_read_exiftool_tags_for_paths", fake_read)

    unique_ids = metadata.media_unique_ids([raw], on_progress=on_progress)

    assert unique_ids == {raw: "abcdef1234567890"}
    assert progress_calls == [(raw, 1, 1)]
