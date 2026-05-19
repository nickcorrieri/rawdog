# Author: Nicholas Corrieri

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 9


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
            profile_kind TEXT NOT NULL DEFAULT 'ingest',
            organization_mode TEXT NOT NULL,
            folder_template TEXT NOT NULL,
            naming_convention TEXT NOT NULL DEFAULT 'detect',
            collision_policy TEXT NOT NULL DEFAULT 'skip',
            verify_after_copy INTEGER NOT NULL DEFAULT 1,
            dry_run_default INTEGER NOT NULL DEFAULT 1,
            exclude_patterns_json TEXT NOT NULL DEFAULT '[]',
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

        CREATE TABLE IF NOT EXISTS consolidation_workflows (
            workflow_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            source_root TEXT NOT NULL,
            destination_root TEXT NOT NULL,
            layout_mode TEXT NOT NULL,
            transfer_action TEXT NOT NULL DEFAULT 'copy',
            folder_template TEXT,
            project_id INTEGER REFERENCES projects(project_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_planned_at TEXT,
            last_committed_at TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS plan_queues (
            queue_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS plan_queue_steps (
            step_id INTEGER PRIMARY KEY,
            queue_id INTEGER NOT NULL REFERENCES plan_queues(queue_id) ON DELETE CASCADE,
            step_order INTEGER NOT NULL,
            step_kind TEXT NOT NULL,
            source_root TEXT,
            destination_root TEXT,
            layout_mode TEXT,
            transfer_action TEXT,
            folder_template TEXT,
            project_name TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(queue_id, step_order)
        );

        CREATE TABLE IF NOT EXISTS execution_plans (
            plan_id INTEGER PRIMARY KEY,
            plan_kind TEXT NOT NULL,
            status TEXT NOT NULL,
            what TEXT NOT NULL,
            subject TEXT NOT NULL,
            expected_result TEXT NOT NULL,
            execution_summary TEXT NOT NULL DEFAULT '',
            post_audit_summary TEXT NOT NULL DEFAULT '',
            source_root TEXT,
            destination_root TEXT,
            queue_id INTEGER REFERENCES plan_queues(queue_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS execution_plan_rows (
            row_id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL REFERENCES execution_plans(plan_id) ON DELETE CASCADE,
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            transfer_action TEXT NOT NULL,
            status TEXT NOT NULL,
            audit_status TEXT,
            executed_at TEXT,
            audited_at TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS stores (
            store_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            store_kind TEXT NOT NULL,
            root_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            UNIQUE(store_kind, name)
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
        VALUES ('schema_version', '9')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="profile_kind",
        definition="TEXT NOT NULL DEFAULT 'ingest'",
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
        table="import_profiles",
        column="naming_convention",
        definition="TEXT NOT NULL DEFAULT 'detect'",
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="collision_policy",
        definition="TEXT NOT NULL DEFAULT 'skip'",
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="verify_after_copy",
        definition="INTEGER NOT NULL DEFAULT 1",
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="dry_run_default",
        definition="INTEGER NOT NULL DEFAULT 1",
    )
    _add_column_if_missing(
        connection,
        table="import_profiles",
        column="exclude_patterns_json",
        definition="TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        connection,
        table="consolidation_workflows",
        column="transfer_action",
        definition="TEXT NOT NULL DEFAULT 'copy'",
    )
    _add_column_if_missing(
        connection,
        table="imports",
        column="profile_id",
        definition="INTEGER REFERENCES import_profiles(profile_id)",
    )
    _add_column_if_missing(
        connection,
        table="stores",
        column="last_used_at",
        definition="TEXT",
    )
    _add_column_if_missing(
        connection,
        table="stores",
        column="use_count",
        definition="INTEGER NOT NULL DEFAULT 0",
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
    _validate_sql_identifier(table)
    _validate_sql_identifier(column)
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _validate_sql_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe SQL identifier: {value}")


def initialize(database_path: Path) -> None:
    with session(database_path) as connection:
        migrate(connection)
