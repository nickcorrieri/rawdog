# Author: Nicholas Corrieri

from datetime import UTC, datetime

from rawdog.filenames import destination_path_for_filename_policy, strip_capture_suffix
from rawdog.models import DestinationFilenamePolicy


def test_strip_capture_suffix_removes_leftover_separator_from_date_only_suffix() -> None:
    assert strip_capture_suffix("20250412-152329-84__7P1A0233__20250412") == "7P1A0233"


def test_date_original_policy_does_not_leave_trailing_separator_for_video_names(tmp_path) -> None:
    source = tmp_path / "20250412-152329-84__7P1A0233__20250412.MP4"
    source.write_bytes(b"video")
    captured_at = datetime(2025, 4, 12, 15, 23, 29, 840000, tzinfo=UTC)

    destination = destination_path_for_filename_policy(
        source,
        tmp_path / "dest",
        captured_at,
        policy=DestinationFilenamePolicy.DATE_ORIGINAL,
        reserved_destinations=set(),
        size_bytes=source.stat().st_size,
    )

    assert destination.name == "20250412-152329-84__7P1A0233.MP4"
