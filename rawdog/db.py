# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 3


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def session(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            project_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            folder_slug TEXT UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            client_name TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            location TEXT,
            notes TEXT,
            preferred_folder_template TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            last_import_at TEXT
        );

        CREATE TABLE IF NOT EXISTS import_profiles (
            profile_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            source_root TEXT NOT NULL,
            destination_root TEXT NOT NULL,
            organization_mode TEXT NOT NULL,
            folder_template TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(project_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS imports (
            import_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            source_root TEXT NOT NULL,
            destination_root TEXT NOT NULL,
            mode TEXT NOT NULL,
            profile_id INTEGER REFERENCES import_profiles(profile_id),
            project_id INTEGER REFERENCES projects(project_id),
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
            file_id INTEGER PRIMARY KEY,
            absolute_path TEXT NOT NULL UNIQUE,
            relative_path TEXT NOT NULL,
            root_kind TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            sha256 TEXT,
            capture_at TEXT,
            camera_make TEXT,
            camera_model TEXT,
            project_id INTEGER REFERENCES projects(project_id),
            import_id INTEGER REFERENCES imports(import_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS copy_log (
            copy_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(project_id),
            import_id INTEGER REFERENCES imports(import_id),
            verify_status TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS anomalies (
            anomaly_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL,
            anomaly_type TEXT NOT NULL,
            source_path TEXT,
            destination_path TEXT,
            project_id INTEGER REFERENCES projects(project_id),
            summary TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}'
        );

        INSERT INTO schema_meta(key, value)
        VALUES ('schema_version', '3')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """
    )
    _add_column_if_missing(
        connection,
        table="projects",
        column="folder_slug",
        definition="TEXT",
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="project_id",
        definition="INTEGER REFERENCES projects(project_id)",
    )
    _add_column_if_missing(
        connection,
        table="imports",
        column="profile_id",
        definition="INTEGER REFERENCES import_profiles(profile_id)",
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS projects_folder_slug_unique "
        "ON projects(folder_slug) WHERE folder_slug IS NOT NULL"
    )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize(database_path: Path) -> None:
    with session(database_path) as connection:
        migrate(connection)
