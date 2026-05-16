# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rawdog.models import ImportProfile, ImportProfileCreate, OrganizationMode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_or_update_profile(
    connection: sqlite3.Connection,
    payload: ImportProfileCreate,
) -> ImportProfile:
    now = _now()
    connection.execute(
        """
        INSERT INTO import_profiles (
            name, source_root, destination_root, organization_mode, folder_template,
            project_id, created_at, updated_at, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            source_root = excluded.source_root,
            destination_root = excluded.destination_root,
            organization_mode = excluded.organization_mode,
            folder_template = excluded.folder_template,
            project_id = excluded.project_id,
            updated_at = excluded.updated_at,
            notes = excluded.notes
        """,
        (
            payload.name,
            str(payload.source_root),
            str(payload.destination_root),
            payload.organization_mode.value,
            payload.folder_template,
            payload.project_id,
            now,
            now,
            payload.notes,
        ),
    )
    row = connection.execute("SELECT * FROM import_profiles WHERE name = ?", (payload.name,)).fetchone()
    return row_to_profile(row)


def list_profiles(connection: sqlite3.Connection) -> list[ImportProfile]:
    rows = connection.execute(
        """
        SELECT * FROM import_profiles
        ORDER BY COALESCE(last_used_at, updated_at, created_at) DESC, name ASC
        """
    ).fetchall()
    return [row_to_profile(row) for row in rows]


def get_profile_by_name(connection: sqlite3.Connection, name: str) -> ImportProfile | None:
    row = connection.execute("SELECT * FROM import_profiles WHERE name = ?", (name,)).fetchone()
    return row_to_profile(row) if row else None


def get_last_profile(connection: sqlite3.Connection) -> ImportProfile | None:
    row = connection.execute(
        """
        SELECT * FROM import_profiles
        ORDER BY COALESCE(last_used_at, updated_at, created_at) DESC, name ASC
        LIMIT 1
        """
    ).fetchone()
    return row_to_profile(row) if row else None


def touch_profile(connection: sqlite3.Connection, profile_id: int) -> None:
    connection.execute(
        "UPDATE import_profiles SET last_used_at = ?, updated_at = ? WHERE profile_id = ?",
        (_now(), _now(), profile_id),
    )


def row_to_profile(row: sqlite3.Row) -> ImportProfile:
    return ImportProfile(
        profile_id=row["profile_id"],
        name=row["name"],
        source_root=Path(row["source_root"]),
        destination_root=Path(row["destination_root"]),
        organization_mode=OrganizationMode(row["organization_mode"]),
        folder_template=row["folder_template"],
        project_id=row["project_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
        notes=row["notes"],
    )
