# Author: Nicholas Corrieri

from pathlib import Path

from rawdog import cli
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.models import OrganizationMode, StoreCreate, StoreFileStatus, StoreKind
from rawdog.stores import create_or_update_store, record_store_file, store_db_path


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
        source_root=None,
        den_name="primary",
        den_root=None,
        before=None,
        validate_first=False,
        hash_check=False,
        yes=True,
        prompt_cleanup=False,
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
        source_root=None,
        den_name="primary",
        den_root=None,
        before=None,
        validate_first=False,
        hash_check=False,
        yes=True,
        prompt_cleanup=False,
    )

    assert not list((database.parent / "reports").glob("junkyard-candidates-*.tsv"))


def test_junkyard_reports_unregistered_folder_by_unique_name_size(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    source_root = tmp_path / "folder"
    den_root = tmp_path / "den"
    source_file = source_root / "IMG_0001.JPG"
    den_file = den_root / "2026" / "IMG_0001.JPG"
    source_file.parent.mkdir(parents=True)
    den_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"jpeg")
    den_file.write_bytes(b"jpeg")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, archive_root=den_root, database_path=database)
    with session(database) as connection:
        create_or_update_store(connection, StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN))
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))

    cli._run_junkyard(
        yard_name=None,
        source_root=source_root,
        den_name="primary",
        den_root=None,
        before=None,
        validate_first=False,
        hash_check=False,
        yes=True,
        prompt_cleanup=False,
    )

    reports = sorted((database.parent / "reports").glob("junkyard-candidates-*.tsv"))
    assert len(reports) == 1
    report_text = reports[0].read_text(encoding="utf-8")
    assert f"# source_root\t{source_root.resolve()}" in report_text
    assert str(source_file.resolve()) in report_text
    assert str(den_file.resolve()) in report_text
    assert "unique-name-size" in report_text


def test_junkyard_scrap_marks_yard_catalog_row_deleted(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    yard_root = tmp_path / "yard"
    den_root = tmp_path / "den"
    yard_file = yard_root / "IMG_0001.JPG"
    den_file = den_root / "2026" / "IMG_0001.JPG"
    report = tmp_path / "junkyard.tsv"
    yard_file.parent.mkdir(parents=True)
    den_file.parent.mkdir(parents=True)
    yard_file.write_bytes(b"jpeg")
    den_file.write_bytes(b"jpeg")
    report.write_text(f"yard_path\tmatched_den_path\tsize_bytes\n{yard_file}\t{den_file}\t4\n", encoding="utf-8")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, working_root=yard_root, archive_root=den_root, database_path=database)
    with session(database) as connection:
        yard = create_or_update_store(connection, StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD))
        create_or_update_store(connection, StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN))
    record_store_file(yard, store_path=yard_file, size_bytes=4)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "SCRAP JUNKYARD REPORT")

    cli.junkyard_scrap(report=report, dry_run=False, hash_check=False)

    assert not yard_file.exists()
    with session(store_db_path(yard.root_path)) as connection:
        row = connection.execute("SELECT status FROM store_files WHERE store_path = ?", (str(yard_file.resolve()),)).fetchone()
    assert row["status"] == StoreFileStatus.DELETED.value


def test_junkyard_scrap_allows_unregistered_report_source_root(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    source_root = tmp_path / "folder"
    den_root = tmp_path / "den"
    source_file = source_root / "IMG_0001.JPG"
    den_file = den_root / "IMG_0001.JPG"
    report = tmp_path / "junkyard.tsv"
    source_file.parent.mkdir(parents=True)
    den_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"jpeg")
    den_file.write_bytes(b"jpeg")
    report.write_text(
        "\n".join(
            [
                "# rawdog_junkyard_report\t1",
                f"# source_root\t{source_root}",
                f"# den_root\t{den_root}",
                "source_path\tmatched_den_path\tsize_bytes\tmatch_method",
                f"{source_file}\t{den_file}\t4\tunique-name-size",
                "",
            ]
        ),
        encoding="utf-8",
    )
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "SCRAP JUNKYARD REPORT")

    cli.junkyard_scrap(report=report, dry_run=False, hash_check=False)

    assert not source_file.exists()
    assert den_file.exists()


def test_junkyard_scrap_can_confirm_each_file(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    source_root = tmp_path / "folder"
    den_root = tmp_path / "den"
    source_a = source_root / "IMG_0001.JPG"
    source_b = source_root / "IMG_0002.JPG"
    den_a = den_root / "IMG_0001.JPG"
    den_b = den_root / "IMG_0002.JPG"
    report = tmp_path / "junkyard.tsv"
    source_root.mkdir(parents=True)
    den_root.mkdir(parents=True)
    source_a.write_bytes(b"jpeg")
    source_b.write_bytes(b"raw2")
    den_a.write_bytes(b"jpeg")
    den_b.write_bytes(b"raw2")
    report.write_text(
        "\n".join(
            [
                "# rawdog_junkyard_report\t1",
                f"# source_root\t{source_root}",
                f"# den_root\t{den_root}",
                "source_path\tmatched_den_path\tsize_bytes\tmatch_method",
                f"{source_a}\t{den_a}\t4\tunique-name-size",
                f"{source_b}\t{den_b}\t4\tunique-name-size",
                "",
            ]
        ),
        encoding="utf-8",
    )
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    choices = iter([True, False])
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli, "_yes_no", lambda *args, **kwargs: next(choices))

    cli.junkyard_scrap(report=report, dry_run=False, hash_check=False, confirm_each=True)

    assert not source_a.exists()
    assert source_b.exists()
    assert den_a.exists()
    assert den_b.exists()
