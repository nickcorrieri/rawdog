# Author: Nicholas Corrieri

import json
import sqlite3
from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import StoreCreate, StoreKind
from rawdog.stores import (
    create_or_update_store,
    find_store_for_path,
    list_store_files_by_original_source,
    list_stores,
    mark_store_used,
    record_store_file,
    store_db_path,
    store_json_path,
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
