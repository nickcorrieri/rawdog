# Author: Nicholas Corrieri

from rawdog.datefolders import normalize_date_folder_name, normalize_date_folder_parts


def test_normalize_date_folder_formats() -> None:
    assert normalize_date_folder_name("20260516").normalized == "20260516"
    assert normalize_date_folder_name("2026.05.16").normalized == "20260516"
    assert normalize_date_folder_name("05162026").normalized == "20260516"
    assert normalize_date_folder_name("05.16.2026").normalized == "20260516"


def test_normalize_date_folder_preserves_label() -> None:
    assert normalize_date_folder_name("2026.05.16 Senior Photos").normalized == (
        "20260516_Senior Photos"
    )
    assert normalize_date_folder_name("05-16-2026_Wedding_Smith").normalized == (
        "20260516_Wedding_Smith"
    )


def test_invalid_date_folder_returns_none() -> None:
    assert normalize_date_folder_name("20269999") is None


def test_normalize_date_folder_parts() -> None:
    assert normalize_date_folder_parts(("Trips", "05-16-2026")) == ("Trips", "20260516")
