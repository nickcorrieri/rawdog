# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.layout import analyze_source_layout


def _raw(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"raw")


def test_detects_camera_dump_layout(tmp_path: Path) -> None:
    _raw(tmp_path / "DCIM" / "100CANON" / "IMG_0001.CR3")
    _raw(tmp_path / "DCIM" / "100CANON" / "IMG_0002.CR3")

    analysis = analyze_source_layout(tmp_path)

    assert analysis.recommendation == "ddd"
    assert analysis.raw_dump_files == 2
    assert analysis.organized_files == 0


def test_camera_model_folder_is_not_project_layout(tmp_path: Path) -> None:
    _raw(tmp_path / "DCIM" / "102EOSR7" / "IMG_0001.CR3")
    _raw(tmp_path / "DCIM" / "102EOSR7" / "IMG_0002.CR3")

    analysis = analyze_source_layout(tmp_path)

    assert analysis.recommendation == "ddd"
    assert analysis.raw_dump_files == 2
    assert analysis.organized_files == 0


def test_selected_camera_model_folder_is_detected_as_raw_dump(tmp_path: Path) -> None:
    source = tmp_path / "102EOSR7"
    _raw(source / "IMG_0001.CR3")
    _raw(source / "IMG_0002.CR3")

    analysis = analyze_source_layout(source)

    assert analysis.recommendation == "ddd"
    assert analysis.raw_dump_files == 2
    assert analysis.organized_files == 0


def test_popular_camera_folder_conventions_are_not_project_layout(tmp_path: Path) -> None:
    camera_folders = [
        "100NIKON",
        "100_FUJI",
        "100MSDCF",
        "100GOPRO",
        "100OLYMP",
        "100_PANA",
        "100LEICA",
        "100MEDIA",
        "100APPLE",
        "100PENTX",
        "100RICOH",
        "100SIGMA",
        "102EOSR7",
    ]
    for folder in camera_folders:
        _raw(tmp_path / folder / f"IMG_{folder}.CR3")

    analysis = analyze_source_layout(tmp_path)

    assert analysis.recommendation == "ddd"
    assert analysis.raw_dump_files == len(camera_folders)
    assert analysis.organized_files == 0


def test_detects_existing_project_layout(tmp_path: Path) -> None:
    _raw(tmp_path / "2026" / "Wedding_Smith" / "IMG_0001.CR3")
    _raw(tmp_path / "2026" / "Wedding_Smith" / "IMG_0002.CR3")

    analysis = analyze_source_layout(tmp_path)

    assert analysis.recommendation == "keep-existing"
    assert analysis.organized_files == 2


def test_detects_mixed_layout_for_operator_review(tmp_path: Path) -> None:
    _raw(tmp_path / "DCIM" / "100CANON" / "IMG_0001.CR3")
    _raw(tmp_path / "Wedding_Smith" / "IMG_0002.CR3")

    analysis = analyze_source_layout(tmp_path)

    assert analysis.recommendation == "mixed-review"
    assert analysis.needs_operator_confirmation is True
