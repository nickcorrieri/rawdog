# Author: Nicholas Corrieri

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from rawdog.models import Project, ProjectCreate
from rawdog.planner import slug_folder_name


class ProjectError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(connection: sqlite3.Connection, payload: ProjectCreate) -> Project:
    now = _now()
    folder_slug = slug_folder_name(payload.name)
    existing_name = get_project_by_name(connection, payload.name)
    if existing_name:
        raise ProjectError(f"project already exists: {payload.name}")
    existing_slug = get_project_by_slug(connection, folder_slug)
    if existing_slug and existing_slug.name != payload.name:
        raise ProjectError(
            f"project folder slug '{folder_slug}' is already used by project '{existing_slug.name}'"
        )
    cursor = connection.execute(
        """
        INSERT INTO projects (
            name, folder_slug, created_at, updated_at, client_name, tags_json, location, notes,
            preferred_folder_template
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name,
            folder_slug,
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


def get_project_by_name(connection: sqlite3.Connection, name: str) -> Project | None:
    row = connection.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return row_to_project(row) if row else None


def get_project_by_slug(connection: sqlite3.Connection, folder_slug: str) -> Project | None:
    row = connection.execute("SELECT * FROM projects WHERE folder_slug = ?", (folder_slug,)).fetchone()
    return row_to_project(row) if row else None


def row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        project_id=row["project_id"],
        name=row["name"],
        folder_slug=row["folder_slug"] or slug_folder_name(row["name"]),
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
