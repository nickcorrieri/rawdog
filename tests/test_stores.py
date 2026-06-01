# Author: Nicholas Corrieri

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rawdog.db import initialize, session
from rawdog.inventory import scan_raw_files
from rawdog.models import StoreCreate, StoreKind
from rawdog.stores import (
    StoreMediaCatalogEntry,
    create_or_update_store,
    find_store_for_path,
    list_store_files_by_original_source,
    list_stores,
    mark_store_used,
    rebuild_store_catalog,
    record_store_file,
    remove_store_registration,
    store_db_path,
    store_json_path,
    store_media_catalog_status,
    upsert_store_media_catalog,
)


def test_store_setup_writes_app_pointer_and_portable_store_files(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    root = tmp_path / "archive"
    root.mkdir()
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=root, store_kind=StoreKind.DEN),
        )
        found = find_store_for_path(connection, root / "2026" / "IMG_0001.CR3", StoreKind.DEN)

    assert found is not None
    assert found.store_id == store.store_id
    assert store_json_path(root).exists()
    assert store_db_path(root).exists()


def test_store_records_den_file_by_original_source(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    den_root = tmp_path / "archive"
    yard_root = tmp_path / "yard"
    den_file = den_root / "2026" / "IMG_0001.CR3"
    yard_file = yard_root / "IMG_0001.CR3"
    den_file.parent.mkdir(parents=True)
    yard_file.parent.mkdir(parents=True)
    den_file.write_bytes(b"raw")
    yard_file.write_bytes(b"raw")
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
    record_store_file(
        store,
        store_path=den_file,
        original_source_path=yard_file,
        size_bytes=3,
    )

    by_source = list_store_files_by_original_source(store)

    assert yard_file.resolve() in by_source
    assert by_source[yard_file.resolve()].store_path == den_file.resolve()


def test_rebuild_store_catalog_scans_disk_removes_stale_and_preserves_source_links(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    den_root = tmp_path / "archive"
    yard_root = tmp_path / "yard"
    kept_file = den_root / "2026" / "IMG_0001.CR3"
    new_file = den_root / "2026" / "IMG_0002.CR3"
    stale_file = den_root / "2026" / "IMG_0003.CR3"
    yard_file = yard_root / "IMG_0001.CR3"
    kept_file.parent.mkdir(parents=True)
    yard_file.parent.mkdir(parents=True)
    kept_file.write_bytes(b"raw1")
    new_file.write_bytes(b"raw2")
    stale_file.write_bytes(b"raw3")
    yard_file.write_bytes(b"raw1")
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
    record_store_file(store, store_path=kept_file, original_source_path=yard_file, size_bytes=4)
    record_store_file(store, store_path=stale_file, size_bytes=4)
    stale_file.unlink()

    result = rebuild_store_catalog(store, scan_raw_files(den_root), dry_run=False)
    by_source = list_store_files_by_original_source(store)

    assert result.scanned_files == 2
    assert result.old_rows == 2
    assert result.stale_rows_removed == 1
    assert result.source_links_preserved == 1
    assert yard_file.resolve() in by_source
    with sqlite3.connect(store_db_path(den_root)) as connection:
        rows = connection.execute("SELECT relative_path FROM store_files ORDER BY relative_path").fetchall()
    assert [row[0] for row in rows] == ["2026/IMG_0001.CR3", "2026/IMG_0002.CR3"]


def test_rebuild_store_catalog_can_rebuild_yard_catalog(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    yard_root = tmp_path / "yard"
    yard_file = yard_root / "Game" / "IMG_0001.JPG"
    yard_file.parent.mkdir(parents=True)
    yard_file.write_bytes(b"jpeg")
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD),
        )

    result = rebuild_store_catalog(store, scan_raw_files(yard_root), dry_run=False)

    assert result.scanned_files == 1
    with sqlite3.connect(store_db_path(yard_root)) as connection:
        rows = connection.execute("SELECT relative_path, size_bytes FROM store_files").fetchall()
    assert rows == [("Game/IMG_0001.JPG", 4)]


def test_store_media_catalog_tracks_quick_full_and_status(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    yard_root = tmp_path / "yard"
    raw_file = yard_root / "IMG_0001.CR3"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"raw")
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD),
        )
    entry = StoreMediaCatalogEntry(
        store_path=raw_file,
        size_bytes=3,
        date_created=datetime.fromtimestamp(raw_file.stat().st_mtime, tz=UTC),
        date_type="filesystem",
    )

    quick = upsert_store_media_catalog(store, [entry], full=False)
    status_after_quick = store_media_catalog_status(store, scan_raw_files(yard_root))
    full = upsert_store_media_catalog(
        store,
        [
            StoreMediaCatalogEntry(
                store_path=entry.store_path,
                size_bytes=entry.size_bytes,
                date_created=entry.date_created,
                date_type=entry.date_type,
                sha256="abc",
                media_identifier="abc12345",
            )
        ],
        full=True,
    )
    status_after_full = store_media_catalog_status(store, scan_raw_files(yard_root))

    assert quick.quick_cataloged == 1
    assert status_after_quick.quick_cataloged_files == 1
    assert status_after_quick.full_cataloged_files == 0
    assert full.full_cataloged == 1
    assert status_after_full.full_cataloged_files == 1
    with sqlite3.connect(store_db_path(yard_root)) as connection:
        rows = connection.execute(
            "SELECT file_name, size_bytes, date_type, sha256, media_identifier FROM media_catalog"
        ).fetchall()
    assert rows == [("IMG_0001.CR3", 3, "filesystem", "abc", "abc12345")]


def test_stores_track_last_used_and_keep_primary_first(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    primary_root = tmp_path / "primary"
    recent_root = tmp_path / "recent"
    primary_root.mkdir()
    recent_root.mkdir()
    initialize(database)

    with session(database) as connection:
        primary = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=primary_root, store_kind=StoreKind.DEN),
        )
        recent = create_or_update_store(
            connection,
            StoreCreate(name="recent", root_path=recent_root, store_kind=StoreKind.DEN),
        )
        mark_store_used(connection, recent.store_id)
        stores = list_stores(connection, StoreKind.DEN)

    assert stores[0].store_id == primary.store_id
    assert stores[1].store_id == recent.store_id
    assert stores[1].last_used_at is not None
    assert stores[1].use_count == 1


def test_store_setup_repairs_existing_root_kind_and_portable_metadata(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    root = tmp_path / "yard"
    root.mkdir()
    initialize(database)

    with session(database) as connection:
        den = create_or_update_store(
            connection,
            StoreCreate(name="RAW_YARD", root_path=root, store_kind=StoreKind.DEN),
        )
        repaired = create_or_update_store(
            connection,
            StoreCreate(name="RAW_YARD", root_path=root, store_kind=StoreKind.YARD),
        )
        yards = list_stores(connection, StoreKind.YARD)
        dens = list_stores(connection, StoreKind.DEN)

    portable = json.loads(store_json_path(root).read_text())

    assert repaired.store_id == den.store_id
    assert repaired.store_kind == StoreKind.YARD
    assert [store.root_path for store in yards] == [root.resolve()]
    assert dens == []
    assert portable["store_kind"] == "yard"


def test_store_setup_relinks_portable_store_without_duplicate_name_crash(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    first_root = tmp_path / "first-yard"
    second_root = tmp_path / "second-yard"
    first_root.mkdir()
    second_root.mkdir()
    initialize(database)

    with session(database) as connection:
        first = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=first_root, store_kind=StoreKind.YARD),
        )
        removed = remove_store_registration(connection, first.store_id, StoreKind.YARD)
        relinked = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=first_root, store_kind=StoreKind.YARD),
        )
        second = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=second_root, store_kind=StoreKind.YARD),
        )
        stores = list_stores(connection, StoreKind.YARD)

    assert removed is not None
    assert relinked.store_id == first.store_id
    assert relinked.name == "primary"
    assert second.name == "primary-2"
    assert [store.name for store in stores] == ["primary", "primary-2"]


def test_remove_store_registration_only_forgets_app_pointer(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    root = tmp_path / "archive"
    root.mkdir()
    initialize(database)

    with session(database) as connection:
        store = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=root, store_kind=StoreKind.DEN),
        )
        removed = remove_store_registration(connection, "primary", StoreKind.DEN)
        stores = list_stores(connection, StoreKind.DEN)

    assert removed is not None
    assert removed.store_id == store.store_id
    assert stores == []
    assert store_json_path(root).exists()


def test_store_migration_adds_usage_columns_to_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE stores (
                store_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                store_kind TEXT NOT NULL,
                root_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                notes TEXT,
                UNIQUE(store_kind, name)
            )
            """
        )

    initialize(database)

    with session(database) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(stores)")}

    assert "last_used_at" in columns
    assert "use_count" in columns
