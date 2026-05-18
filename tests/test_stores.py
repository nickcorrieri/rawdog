# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import StoreCreate, StoreKind
from rawdog.stores import (
    create_or_update_store,
    find_store_for_path,
    list_store_files_by_original_source,
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
