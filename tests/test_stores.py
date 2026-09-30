# Author: Nicholas Corrieri

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import rawdog.stores as stores_module
from rawdog.db import initialize, session
from rawdog.inventory import scan_raw_files
from rawdog.models import StoreCreate, StoreKind
from rawdog.safety import SafetyError
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


@pytest.mark.parametrize("replacement", [b"new-data", b"different-length", b"old-data"],
                         ids=["equal-size-replacement", "changed-size", "unchanged-observation"])
def test_quick_catalog_clears_prior_full_evidence(tmp_path: Path, replacement: bytes) -> None:
    database = tmp_path / "app.sqlite"
    root = tmp_path / "yard"
    root.mkdir()
    media = root / "IMG_0001.CR3"
    media.write_bytes(b"old-data")
    initialize(database)
    with session(database) as connection:
        store = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=root, store_kind=StoreKind.YARD))
    observed_date = datetime(2024, 5, 20, tzinfo=UTC)
    full_entry = StoreMediaCatalogEntry(media, 8, observed_date, "media",
                                         hashlib.sha256(b"old-data").hexdigest(), "old-id")
    upsert_store_media_catalog(store, [full_entry], full=True)
    media.write_bytes(replacement)
    # Even a caller-supplied old digest/identifier cannot renew verification in quick mode.
    quick_entry = StoreMediaCatalogEntry(media, len(replacement), observed_date, "filesystem",
                                          full_entry.sha256, full_entry.media_identifier)
    result = upsert_store_media_catalog(store, [quick_entry], full=False)
    status = store_media_catalog_status(store, scan_raw_files(root))
    with sqlite3.connect(store_db_path(root)) as connection:
        row = connection.execute(
            "SELECT size_bytes, sha256, media_identifier, full_cataloged_at, quick_cataloged_at "
            "FROM media_catalog").fetchone()
    assert row[:4] == (len(replacement), None, None, None)
    assert row[4] is not None
    assert result.quick_cataloged == 1
    assert result.full_cataloged == 0
    assert status.quick_cataloged_files == 1
    assert status.full_cataloged_files == 0
    assert media.read_bytes() == replacement


def test_quick_catalog_insert_discards_supplied_hash_evidence(tmp_path: Path) -> None:
    database = tmp_path / "app.sqlite"
    root = tmp_path / "yard"
    root.mkdir()
    media = root / "IMG_0001.JPG"
    media.write_bytes(b"synthetic")
    initialize(database)
    with session(database) as connection:
        store = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=root, store_kind=StoreKind.YARD))
    entry = StoreMediaCatalogEntry(media, 9, datetime(2024, 5, 20, tzinfo=UTC), "filesystem",
                                  hashlib.sha256(b"synthetic").hexdigest(), "supplied-id")
    result = upsert_store_media_catalog(store, [entry], full=False)
    with sqlite3.connect(store_db_path(root)) as connection:
        row = connection.execute(
            "SELECT sha256, media_identifier, full_cataloged_at FROM media_catalog").fetchone()
    assert row == (None, None, None)
    assert result.full_cataloged == 0


@pytest.mark.parametrize("digest", [None, ""])
def test_full_catalog_without_hash_cannot_claim_full_verification(tmp_path: Path, digest: str | None) -> None:
    database = tmp_path / "app.sqlite"
    root = tmp_path / "yard"
    root.mkdir()
    media = root / "IMG_0001.JPG"
    media.write_bytes(b"synthetic")
    initialize(database)
    with session(database) as connection:
        store = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=root, store_kind=StoreKind.YARD))
    entry = StoreMediaCatalogEntry(media, 9, datetime(2024, 5, 20, tzinfo=UTC), "filesystem", digest)
    result = upsert_store_media_catalog(store, [entry], full=True)
    status = store_media_catalog_status(store, scan_raw_files(root))
    with sqlite3.connect(store_db_path(root)) as connection:
        row = connection.execute("SELECT sha256, full_cataloged_at FROM media_catalog").fetchone()
    assert row == (None, None)
    assert result.full_cataloged == 0
    assert status.full_cataloged_files == 0


@pytest.mark.parametrize("original_available", [True, False], ids=["live-original", "offline-original"])
def test_copied_portable_identity_preserves_original_and_clone(tmp_path: Path, original_available: bool) -> None:
    database = tmp_path / "app.sqlite"
    original_root = tmp_path / "original"
    original_root.mkdir()
    media = original_root / "IMG_0001.CR3"
    media.write_bytes(b"synthetic-original")
    initialize(database)
    with session(database) as connection:
        original = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=original_root, store_kind=StoreKind.DEN))
        registrations_before = [tuple(row) for row in connection.execute("SELECT * FROM stores")]
    clone = tmp_path / "backup"
    shutil.copytree(original_root, clone)
    clone_identity = store_json_path(clone).read_bytes()
    clone_catalog = store_db_path(clone).read_bytes()
    saved_original = original_root
    if not original_available:
        saved_original = tmp_path / "offline-original"
        original_root.rename(saved_original)
    original_identity = store_json_path(saved_original).read_bytes()
    original_catalog = store_db_path(saved_original).read_bytes()

    with session(database) as connection:
        with pytest.raises(SafetyError, match="copied store or an unproven relocation"):
            create_or_update_store(
                connection, StoreCreate(name="backup", root_path=clone, store_kind=StoreKind.DEN))
        registrations_after = [tuple(row) for row in connection.execute("SELECT * FROM stores")]
        registered = list_stores(connection)
    assert registrations_after == registrations_before
    assert len(registered) == 1
    assert registered[0].store_id == original.store_id
    assert registered[0].root_path == original_root
    assert store_json_path(saved_original).read_bytes() == original_identity
    assert store_db_path(saved_original).read_bytes() == original_catalog
    assert store_json_path(clone).read_bytes() == clone_identity
    assert store_db_path(clone).read_bytes() == clone_catalog
    assert (saved_original / media.name).read_bytes() == b"synthetic-original"
    assert (clone / media.name).read_bytes() == b"synthetic-original"


def test_portable_store_relinks_into_fresh_app_database(tmp_path: Path) -> None:
    root = tmp_path / "original"
    root.mkdir()
    first_database, fresh_database = tmp_path / "first.sqlite", tmp_path / "fresh.sqlite"
    initialize(first_database)
    initialize(fresh_database)
    with session(first_database) as connection:
        original = create_or_update_store(
            connection, StoreCreate(name="original", root_path=root, store_kind=StoreKind.YARD))
    with session(fresh_database) as connection:
        relinked = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=root, store_kind=StoreKind.YARD))
    assert relinked.store_id == original.store_id
    assert relinked.name == original.name
    assert relinked.root_path == root


def test_relocation_requires_explicit_forget_then_portable_relink(tmp_path: Path) -> None:
    database = tmp_path / "app.sqlite"
    old_root, moved_root = tmp_path / "old", tmp_path / "moved"
    old_root.mkdir()
    initialize(database)
    with session(database) as connection:
        original = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=old_root, store_kind=StoreKind.YARD))
    old_root.rename(moved_root)
    portable_before = store_json_path(moved_root).read_bytes()
    with session(database) as connection:
        with pytest.raises(SafetyError, match="unproven relocation"):
            create_or_update_store(
                connection, StoreCreate(name="primary", root_path=moved_root, store_kind=StoreKind.YARD))
        assert store_json_path(moved_root).read_bytes() == portable_before
        assert list_stores(connection)[0].root_path == old_root
        removed = remove_store_registration(connection, original.store_id, StoreKind.YARD)
        relinked = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=moved_root, store_kind=StoreKind.YARD))
    assert removed is not None
    assert relinked.store_id == original.store_id
    assert relinked.root_path == moved_root


def test_clone_registration_rechecks_identity_if_original_registered_after_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_root, clone = tmp_path / "original", tmp_path / "clone"
    original_root.mkdir()
    initial_database, database = tmp_path / "initial.sqlite", tmp_path / "app.sqlite"
    initialize(initial_database)
    initialize(database)
    with session(initial_database) as connection:
        original = create_or_update_store(
            connection, StoreCreate(name="primary", root_path=original_root, store_kind=StoreKind.DEN))
    shutil.copytree(original_root, clone)
    clone_identity = store_json_path(clone).read_bytes()
    clone_catalog = store_db_path(clone).read_bytes()
    available_name = stores_module._available_name
    injected = False

    def register_original_before_clone_write(connection, *arguments):
        nonlocal injected
        if not injected:
            injected = True
            # Force the real database interleaving after clone's identity lookup
            # and before its write; do not fake the result of the guarded upsert.
            create_or_update_store(
                connection,
                StoreCreate(name="primary", root_path=original_root, store_kind=StoreKind.DEN))
        return available_name(connection, *arguments)

    monkeypatch.setattr(stores_module, "_available_name", register_original_before_clone_write)
    with session(database) as connection:
        with pytest.raises(SafetyError, match="changed concurrently"):
            create_or_update_store(
                connection, StoreCreate(name="backup", root_path=clone, store_kind=StoreKind.DEN))
        registered = list_stores(connection)
    assert injected
    assert len(registered) == 1
    assert registered[0].store_id == original.store_id
    assert registered[0].root_path == original_root
    assert store_json_path(clone).read_bytes() == clone_identity
    assert store_db_path(clone).read_bytes() == clone_catalog
