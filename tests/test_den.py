# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.den import build_den_plan, score_items, summarize_by_year
from rawdog.inventory import scan_raw_files
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
    assert score.notes == ["No RAW files found."]


def test_score_items_counts_raw_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "IMG_0001.CR3").write_bytes(b"raw")

    score = score_items(scan_raw_files(source))

    assert score.file_count == 1
    assert score.score == 100
