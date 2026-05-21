# Author: Nicholas Corrieri

import os
from datetime import UTC, datetime
from pathlib import Path

from rawdog.den import build_den_plan, score_items, summarize_by_year
from rawdog.inventory import scan_raw_files
from rawdog.metadata import capture_time_fallback
from rawdog.models import DenLayoutMode, DenTransferAction


def test_build_den_plan_for_date_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(source, destination, layout_mode=DenLayoutMode.DATE)

    assert plan.files_to_copy == 1
    assert plan.bytes_to_copy == 3
    assert plan.files_to_transfer == 1
    assert plan.bytes_to_transfer == 3
    assert plan.rows[0].destination_path.name == "IMG_0001.CR3"
    assert plan.destination_folder == destination


def test_build_den_plan_can_plan_move(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(source, destination, transfer_action=DenTransferAction.MOVE)

    assert plan.transfer_action == DenTransferAction.MOVE
    assert plan.files_to_transfer == 1


def test_den_preserves_source_structure_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "2019" / "Family_Trip" / "IMG_0001.CR3"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(source, destination)

    assert plan.rows[0].destination_path == destination / "2019" / "Family_Trip" / "IMG_0001.CR3"


def test_den_can_preserve_structure_but_normalize_date_folders(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "Trips" / "05.16.2026" / "IMG_0001.CR3"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(source, destination, layout_mode=DenLayoutMode.PRESERVE_DATES)

    assert plan.rows[0].destination_path == destination / "Trips" / "20260516" / "IMG_0001.CR3"


def test_den_preserve_dates_routes_selected_camera_folder_by_date(tmp_path: Path) -> None:
    source = tmp_path / "102EOSR7"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(
        source,
        destination,
        layout_mode=DenLayoutMode.PRESERVE_DATES,
        folder_template="YYYY/YYYYMMDD",
    )

    assert plan.rows[0].destination_path.parent.parent == destination / "2026"
    assert plan.rows[0].destination_path.name == "IMG_0001.CR3"
    assert "102EOSR7" not in plan.rows[0].destination_path.parts


def test_den_date_layout_drops_dcim_camera_folder_wrappers(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "DCIM" / "100CANON" / "IMG_0001.CR3"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")
    captured_ts = datetime(2023, 10, 15, tzinfo=UTC).timestamp()
    os.utime(raw, (captured_ts, captured_ts))

    plan = build_den_plan(
        source,
        destination,
        layout_mode=DenLayoutMode.DATE,
        folder_template="YYYY/YYYYMMDD",
    )

    assert plan.rows[0].destination_path.name == "IMG_0001.CR3"
    assert "DCIM" not in plan.rows[0].destination_path.parts
    assert "100CANON" not in plan.rows[0].destination_path.parts


def test_den_preserve_dates_keeps_project_prefix_but_drops_camera_wrappers(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "Wedding_Smith" / "DCIM" / "100NIKON" / "IMG_0001.NEF"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(
        source,
        destination,
        layout_mode=DenLayoutMode.PRESERVE_DATES,
        folder_template="YYYY/YYYYMMDD",
    )

    assert plan.rows[0].destination_path.name == "IMG_0001.NEF"
    assert plan.rows[0].destination_path.parts[: len(destination.parts) + 1] == (
        *destination.parts,
        "Wedding_Smith",
    )
    assert "DCIM" not in plan.rows[0].destination_path.parts
    assert "100NIKON" not in plan.rows[0].destination_path.parts


def test_den_preserve_dates_does_not_duplicate_year_prefix_for_camera_dump(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "2023" / "100CANON" / "IMG_0001.CR3"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")
    captured_ts = datetime(2023, 10, 15, tzinfo=UTC).timestamp()
    os.utime(raw, (captured_ts, captured_ts))

    plan = build_den_plan(
        source,
        destination,
        layout_mode=DenLayoutMode.PRESERVE_DATES,
        folder_template="YYYY/YYYY-MM",
    )

    assert plan.rows[0].destination_path == destination / "2023" / "2023-10" / "IMG_0001.CR3"
    assert destination / "2023" / "2023" not in plan.rows[0].destination_path.parents


def test_den_project_dates_groups_project_by_file_date(tmp_path: Path) -> None:
    source = tmp_path / "102EOSR7"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")
    captured_at = capture_time_fallback(raw)

    plan = build_den_plan(
        source,
        destination,
        project_name="Soccer",
        layout_mode=DenLayoutMode.PROJECT_DATES,
        folder_template="YYYY/PROJECT-YYYYMM",
    )

    assert plan.destination_folder == destination
    assert plan.rows[0].destination_path == (
        destination / f"{captured_at.year:04d}" / f"Soccer-{captured_at:%Y%m}" / "IMG_0001.CR3"
    )


def test_den_project_dates_can_group_project_by_day(tmp_path: Path) -> None:
    source = tmp_path / "102EOSR7"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")
    captured_at = capture_time_fallback(raw)

    plan = build_den_plan(
        source,
        destination,
        project_name="Soccer",
        layout_mode=DenLayoutMode.PROJECT_DATES,
        folder_template="YYYY/PROJECT-YYYYMMDD",
    )

    assert plan.rows[0].destination_path == (
        destination / f"{captured_at.year:04d}" / f"Soccer-{captured_at:%Y%m%d}" / "IMG_0001.CR3"
    )


def test_den_can_scope_project_plan_by_capture_date(tmp_path: Path) -> None:
    source = tmp_path / "102EOSR7"
    destination = tmp_path / "archive"
    source.mkdir()
    destination.mkdir()
    january = source / "IMG_0001.CR3"
    february = source / "IMG_0002.CR3"
    january.write_bytes(b"jan")
    february.write_bytes(b"feb")
    jan_ts = datetime(2026, 1, 15, tzinfo=UTC).timestamp()
    feb_ts = datetime(2026, 2, 15, tzinfo=UTC).timestamp()
    os.utime(january, (jan_ts, jan_ts))
    os.utime(february, (feb_ts, feb_ts))

    plan = build_den_plan(
        source,
        destination,
        project_name="Soccer",
        layout_mode=DenLayoutMode.PROJECT_DATES,
        folder_template="YYYY/PROJECT-YYYYMM",
        start_date=datetime(2026, 2, 1, tzinfo=UTC).date(),
        end_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
    )

    assert len(plan.rows) == 1
    assert plan.rows[0].source_path == february
    assert "Soccer-202602" in plan.rows[0].destination_path.parts


def test_den_preserve_dates_keeps_date_folder_label_and_file_name(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "Trips" / "05.16.2026 Senior Photos" / "IMG_0042.CR2"
    raw.parent.mkdir(parents=True)
    destination.mkdir()
    raw.write_bytes(b"raw")

    plan = build_den_plan(source, destination, layout_mode=DenLayoutMode.PRESERVE_DATES)

    assert plan.rows[0].destination_path == (
        destination / "Trips" / "20260516_Senior Photos" / "IMG_0042.CR2"
    )


def test_den_excludes_destination_when_it_is_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "drive"
    destination = source / "Photo_Library"
    old_raw = source / "OldMess" / "IMG_0001.CR3"
    archive_raw = destination / "IMG_0002.CR3"
    old_raw.parent.mkdir(parents=True)
    archive_raw.parent.mkdir(parents=True)
    old_raw.write_bytes(b"raw")
    archive_raw.write_bytes(b"archive")

    plan = build_den_plan(source, destination, exclude_roots=[destination])

    assert len(plan.rows) == 1
    assert plan.rows[0].source_path == old_raw
    assert plan.excluded_roots == [destination.resolve()]


def test_den_limit_creates_small_review_plan(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    source.mkdir()
    destination.mkdir()
    (source / "IMG_0001.CR3").write_bytes(b"raw")
    (source / "IMG_0002.CR3").write_bytes(b"raw")

    plan = build_den_plan(source, destination, limit=1)

    assert len(plan.rows) == 1
    assert plan.limited_to == 1


def test_den_summary_by_year(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "archive"
    raw = source / "IMG_0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw.write_bytes(b"raw")
    plan = build_den_plan(source, destination)

    summary = summarize_by_year(plan.rows)

    assert summary[0]["files_to_copy"] == 1


def test_score_items_reports_empty_source() -> None:
    score = score_items([])

    assert score.score == 0
    assert score.notes == ["No RAW or camera video files found."]


def test_score_items_counts_raw_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "IMG_0001.CR3").write_bytes(b"raw")

    score = score_items(scan_raw_files(source))

    assert score.file_count == 1
    assert score.score == 100
