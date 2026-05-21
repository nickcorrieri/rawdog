# Author: Nicholas Corrieri

from datetime import UTC
from pathlib import Path

from rawdog.metadata import CAMERA_CAPTURE_EXTENSIONS, capture_time_fallback


def test_capture_time_fallback_is_utc_aware(tmp_path: Path) -> None:
    raw = tmp_path / "IMG_0001.CR3"
    raw.write_bytes(b"raw")

    captured_at = capture_time_fallback(raw)

    assert captured_at.tzinfo == UTC


def test_camera_capture_extensions_include_jpeg() -> None:
    assert ".jpg" in CAMERA_CAPTURE_EXTENSIONS
    assert ".jpeg" in CAMERA_CAPTURE_EXTENSIONS
