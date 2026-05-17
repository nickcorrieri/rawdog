# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.inventory import scan_raw_files
from rawdog.metadata import is_raw_file


def test_scan_raw_files_ignores_partial_artifacts(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.CR3").write_bytes(b"raw")
    (tmp_path / "IMG_0002.CR3.partial").write_bytes(b"partial")

    items = scan_raw_files(tmp_path)

    assert [item.path.name for item in items] == ["IMG_0001.CR3"]


def test_raw_extension_is_case_insensitive() -> None:
    assert is_raw_file(Path("IMG_0001.NEF"))
    assert is_raw_file(Path("IMG_0001.nef"))
    assert not is_raw_file(Path("IMG_0001.NEF.partial"))
