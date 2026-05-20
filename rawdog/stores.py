# Author: Nicholas Corrieri

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rawdog.models import Store, StoreCreate, StoreFile, StoreFileStatus, StoreKind

STORE_DIR = ".rawdog"
STORE_JSON = "store.json"
STORE_DB = "store.sqlite"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def store_dir(root_path: Path) -> Path:
    return root_path / STORE_DIR


def store_json_path(root_path: Path) -> Path:
    return store_dir(root_path) / STORE_JSON


def store_db_path(root_path: Path) -> Path:
    return store_dir(root_path) / STORE_DB


def create_or_update_store(connection: sqlite3.Connection, payload: StoreCreate) -> Store:
    root_path = payload.root_path.expanduser().resolve()
    existing_row = connection.execute(
        "SELECT store_id, name FROM stores WHERE root_path = ?",
        (str(root_path),),
    ).fetchone()
    store_id = (
        existing_row["store_id"]
        if existing_row
        else _read_store_id(root_path) or f"{payload.store_kind.value}_{uuid.uuid4().hex[:12]}"
    )
    now = _now()
    _write_store_identity(root_path, store_id, payload.name, payload.store_kind, now)
    _initialize_store_db(root_path)
    connection.execute(
        """
        INSERT INTO stores (store_id, name, store_kind, root_path, created_at, updated_at, last_seen_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(store_id) DO UPDATE SET
            name = excluded.name,
            store_kind = excluded.store_kind,
            root_path = excluded.root_path,
            updated_at = excluded.updated_at,
            last_seen_at = excluded.last_seen_at,
            notes = excluded.notes
        """,
        (
            store_id,
            payload.name,
            payload.store_kind.value,
            str(root_path),
            now,
            now,
            now,
            payload.notes,
        ),
    )
    row = connection.execute("SELECT * FROM stores WHERE store_id = ?", (store_id,)).fetchone()
    return row_to_store(row)


def list_stores(connection: sqlite3.Connection, store_kind: StoreKind | None = None) -> list[Store]:
    order = """
        ORDER BY
            CASE WHEN lower(name) = 'primary' THEN 0 ELSE 1 END,
            COALESCE(last_used_at, updated_at) DESC,
            name ASC
    """
    if store_kind:
        rows = connection.execute(
            f"SELECT * FROM stores WHERE store_kind = ? {order}",
            (store_kind.value,),
        ).fetchall()
    else:
        rows = connection.execute(f"SELECT * FROM stores {order}").fetchall()
    return [row_to_store(row) for row in rows]


def get_store_by_name(
    connection: sqlite3.Connection,
    name: str,
    store_kind: StoreKind | None = None,
) -> Store | None:
    if store_kind:
        row = connection.execute(
            "SELECT * FROM stores WHERE name = ? AND store_kind = ?",
            (name, store_kind.value),
        ).fetchone()
    else:
        row = connection.execute("SELECT * FROM stores WHERE name = ?", (name,)).fetchone()
    return row_to_store(row) if row else None


def find_store_for_path(
    connection: sqlite3.Connection,
    path: Path,
    store_kind: StoreKind | None = None,
) -> Store | None:
    resolved = path.expanduser().resolve()
    stores = sorted(
        list_stores(connection, store_kind=store_kind),
        key=lambda store: len(store.root_path.parts),
        reverse=True,
    )
    for store in stores:
        if resolved == store.root_path or store.root_path in resolved.parents:
            return store
    return None


def mark_store_used(connection: sqlite3.Connection, store_id: str) -> Store:
    now = _now()
    connection.execute(
        """
        UPDATE stores
        SET last_used_at = ?,
            last_seen_at = ?,
            updated_at = ?,
            use_count = use_count + 1
        WHERE store_id = ?
        """,
        (now, now, now, store_id),
    )
    row = connection.execute("SELECT * FROM stores WHERE store_id = ?", (store_id,)).fetchone()
    return row_to_store(row)


def record_store_file(
    store: Store,
    *,
    store_path: Path,
    size_bytes: int,
    original_source_path: Path | None = None,
    execution_plan_id: int | None = None,
    execution_row_id: int | None = None,
    status: StoreFileStatus = StoreFileStatus.PRESENT,
) -> StoreFile:
    _initialize_store_db(store.root_path)
    resolved = store_path.expanduser().resolve()
    relative = resolved.relative_to(store.root_path)
    now = _now()
    with sqlite3.connect(store_db_path(store.root_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO store_files (
                store_id, store_path, relative_path, original_source_path, size_bytes, status,
                execution_plan_id, execution_row_id, created_at, updated_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(store_path) DO UPDATE SET
                relative_path = excluded.relative_path,
                original_source_path = excluded.original_source_path,
                size_bytes = excluded.size_bytes,
                status = excluded.status,
                execution_plan_id = excluded.execution_plan_id,
                execution_row_id = excluded.execution_row_id,
                updated_at = excluded.updated_at,
                last_seen_at = excluded.last_seen_at
            """,
            (
                store.store_id,
                str(resolved),
                str(relative),
                str(original_source_path.expanduser().resolve()) if original_source_path else None,
                size_bytes,
                status.value,
                execution_plan_id,
                execution_row_id,
                now,
                now,
                now,
            ),
        )
        row = connection.execute(
            "SELECT * FROM store_files WHERE store_path = ?",
            (str(resolved),),
        ).fetchone()
    return row_to_store_file(row)


def list_store_files_by_original_source(store: Store) -> dict[Path, StoreFile]:
    path = store_db_path(store.root_path)
    if not path.exists():
        return {}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM store_files WHERE original_source_path IS NOT NULL"
        ).fetchall()
    return {Path(row["original_source_path"]): row_to_store_file(row) for row in rows}


def row_to_store(row: sqlite3.Row) -> Store:
    return Store(
        store_id=row["store_id"],
        name=row["name"],
        store_kind=StoreKind(row["store_kind"]),
        root_path=Path(row["root_path"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
        use_count=row["use_count"],
        notes=row["notes"],
    )


def row_to_store_file(row: sqlite3.Row) -> StoreFile:
    return StoreFile(
        store_file_id=row["store_file_id"],
        store_id=row["store_id"],
        store_path=Path(row["store_path"]),
        relative_path=Path(row["relative_path"]),
        original_source_path=Path(row["original_source_path"]) if row["original_source_path"] else None,
        size_bytes=row["size_bytes"],
        status=StoreFileStatus(row["status"]),
        execution_plan_id=row["execution_plan_id"],
        execution_row_id=row["execution_row_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
    )


def _read_store_id(root_path: Path) -> str | None:
    path = store_json_path(root_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    store_id = payload.get("store_id")
    return str(store_id) if store_id else None


def _write_store_identity(
    root_path: Path,
    store_id: str,
    name: str,
    store_kind: StoreKind,
    created_at: str,
) -> None:
    path = store_json_path(root_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "store_id": store_id,
        "name": name,
        "store_kind": store_kind.value,
        "created_at": created_at,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _initialize_store_db(root_path: Path) -> None:
    path = store_db_path(root_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS store_files (
                store_file_id INTEGER PRIMARY KEY,
                store_id TEXT NOT NULL,
                store_path TEXT NOT NULL UNIQUE,
                relative_path TEXT NOT NULL,
                original_source_path TEXT,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                execution_plan_id INTEGER,
                execution_row_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS store_files_relative_path
            ON store_files(relative_path);

            CREATE INDEX IF NOT EXISTS store_files_original_source
            ON store_files(original_source_path);
            """
        )
