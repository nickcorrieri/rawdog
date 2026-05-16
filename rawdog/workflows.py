# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rawdog.models import ConsolidationWorkflow, ConsolidationWorkflowCreate, DenLayoutMode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_or_update_workflow(
    connection: sqlite3.Connection,
    payload: ConsolidationWorkflowCreate,
) -> ConsolidationWorkflow:
    now = _now()
    connection.execute(
        """
        INSERT INTO consolidation_workflows (
            name, source_root, destination_root, layout_mode, folder_template,
            project_id, created_at, updated_at, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            source_root = excluded.source_root,
            destination_root = excluded.destination_root,
            layout_mode = excluded.layout_mode,
            folder_template = excluded.folder_template,
            project_id = excluded.project_id,
            updated_at = excluded.updated_at,
            notes = excluded.notes
        """,
        (
            payload.name,
            str(payload.source_root),
            str(payload.destination_root),
            payload.layout_mode.value,
            payload.folder_template,
            payload.project_id,
            now,
            now,
            payload.notes,
        ),
    )
    row = connection.execute(
        "SELECT * FROM consolidation_workflows WHERE name = ?",
        (payload.name,),
    ).fetchone()
    return row_to_workflow(row)


def get_workflow_by_name(
    connection: sqlite3.Connection,
    name: str,
) -> ConsolidationWorkflow | None:
    row = connection.execute(
        "SELECT * FROM consolidation_workflows WHERE name = ?",
        (name,),
    ).fetchone()
    return row_to_workflow(row) if row else None


def list_workflows(connection: sqlite3.Connection) -> list[ConsolidationWorkflow]:
    rows = connection.execute(
        """
        SELECT * FROM consolidation_workflows
        ORDER BY COALESCE(last_committed_at, last_planned_at, updated_at, created_at) DESC, name ASC
        """
    ).fetchall()
    return [row_to_workflow(row) for row in rows]


def mark_workflow_planned(connection: sqlite3.Connection, workflow_id: int) -> None:
    connection.execute(
        "UPDATE consolidation_workflows SET last_planned_at = ?, updated_at = ? WHERE workflow_id = ?",
        (_now(), _now(), workflow_id),
    )


def mark_workflow_committed(connection: sqlite3.Connection, workflow_id: int) -> None:
    connection.execute(
        "UPDATE consolidation_workflows SET last_committed_at = ?, updated_at = ? WHERE workflow_id = ?",
        (_now(), _now(), workflow_id),
    )


def row_to_workflow(row: sqlite3.Row) -> ConsolidationWorkflow:
    return ConsolidationWorkflow(
        workflow_id=row["workflow_id"],
        name=row["name"],
        source_root=Path(row["source_root"]),
        destination_root=Path(row["destination_root"]),
        layout_mode=DenLayoutMode(row["layout_mode"]),
        folder_template=row["folder_template"],
        project_id=row["project_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_planned_at=datetime.fromisoformat(row["last_planned_at"]) if row["last_planned_at"] else None,
        last_committed_at=(
            datetime.fromisoformat(row["last_committed_at"]) if row["last_committed_at"] else None
        ),
        notes=row["notes"],
    )
