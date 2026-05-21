# Author: Nicholas Corrieri

from pathlib import Path

from rawdog import cli
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.models import OrganizationMode, StoreCreate, StoreKind
from rawdog.stores import create_or_update_store, record_store_file


def test_junkyard_writes_jpeg_report_only_after_den_file_validation(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    yard_root = tmp_path / "yard"
    den_root = tmp_path / "den"
    yard_file = yard_root / "IMG_0001.JPG"
    den_file = den_root / "2026" / "IMG_0001.JPG"
    yard_file.parent.mkdir(parents=True)
    den_file.parent.mkdir(parents=True)
    yard_file.write_bytes(b"jpeg")
    den_file.write_bytes(b"jpeg")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, working_root=yard_root, archive_root=den_root, database_path=database)
    with session(database) as connection:
        create_or_update_store(connection, StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD))
        den = create_or_update_store(connection, StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN))
    record_store_file(den, store_path=den_file, original_source_path=yard_file, size_bytes=4)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    notices: list[str] = []
    monkeypatch.setattr(cli, "_print_notice", lambda text, **kwargs: notices.append(text))

    cli._run_junkyard(
        yard_name="primary",
        den_name="primary",
        before=None,
        validate_first=False,
        hash_check=False,
        yes=True,
    )

    reports = sorted((database.parent / "reports").glob("junkyard-candidates-*.tsv"))
    assert len(reports) == 1
    assert str(yard_file.resolve()) in reports[0].read_text(encoding="utf-8")
    assert str(den_file.resolve()) in reports[0].read_text(encoding="utf-8")
    assert any("validated on disk by path + exact size" in notice for notice in notices)


def test_junkyard_excludes_missing_den_file(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    yard_root = tmp_path / "yard"
    den_root = tmp_path / "den"
    yard_file = yard_root / "IMG_0001.JPG"
    den_file = den_root / "2026" / "IMG_0001.JPG"
    yard_file.parent.mkdir(parents=True)
    den_file.parent.mkdir(parents=True)
    yard_file.write_bytes(b"jpeg")
    den_file.write_bytes(b"jpeg")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, working_root=yard_root, archive_root=den_root, database_path=database)
    with session(database) as connection:
        create_or_update_store(connection, StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD))
        den = create_or_update_store(connection, StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN))
    record_store_file(den, store_path=den_file, original_source_path=yard_file, size_bytes=4)
    den_file.unlink()
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))

    cli._run_junkyard(
        yard_name="primary",
        den_name="primary",
        before=None,
        validate_first=False,
        hash_check=False,
        yes=True,
    )

    assert not list((database.parent / "reports").glob("junkyard-candidates-*.tsv"))

