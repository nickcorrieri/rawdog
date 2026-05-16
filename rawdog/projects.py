# Author: Nicholas Corrieri

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from rawdog.models import Project, ProjectCreate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(connection: sqlite3.Connection, payload: ProjectCreate) -> Project:
    now = _now()
    cursor = connection.execute(
        """
        INSERT INTO projects (
            name, created_at, updated_at, client_name, tags_json, location, notes,
            preferred_folder_template
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name,
            now,
            now,
            payload.client_name,
            json.dumps(payload.tags),
            payload.location,
            payload.notes,
            payload.preferred_folder_template,
        ),
    )
    row = connection.execute(
        "SELECT * FROM projects WHERE project_id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return row_to_project(row)


def list_projects(connection: sqlite3.Connection, include_archived: bool = False) -> list[Project]:
    query = "SELECT * FROM projects"
    params: tuple[object, ...] = ()
    if not include_archived:
        query += " WHERE archived = 0"
    query += " ORDER BY COALESCE(last_import_at, created_at) DESC, name ASC"
    return [row_to_project(row) for row in connection.execute(query, params).fetchall()]


def row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        project_id=row["project_id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        client_name=row["client_name"],
        tags=json.loads(row["tags_json"]),
        location=row["location"],
        notes=row["notes"],
        preferred_folder_template=row["preferred_folder_template"],
        archived=bool(row["archived"]),
        last_import_at=datetime.fromisoformat(row["last_import_at"]) if row["last_import_at"] else None,
    )
