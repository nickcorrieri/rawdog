# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rawdog.models import (
    DenLayoutMode,
    DenTransferAction,
    PlanQueue,
    PlanQueueCreate,
    PlanQueueStep,
    PlanQueueStepCreate,
    PlanStepKind,
)

SAFE_STEP_KINDS = {PlanStepKind.SNIFF, PlanStepKind.SCORE, PlanStepKind.DEN}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_or_update_queue(connection: sqlite3.Connection, payload: PlanQueueCreate) -> PlanQueue:
    now = _now()
    connection.execute(
        """
        INSERT INTO plan_queues (name, created_at, updated_at, status, notes)
        VALUES (?, ?, ?, 'planned', ?)
        ON CONFLICT(name) DO UPDATE SET
            updated_at = excluded.updated_at,
            notes = excluded.notes
        """,
        (payload.name, now, now, payload.notes),
    )
    row = connection.execute("SELECT * FROM plan_queues WHERE name = ?", (payload.name,)).fetchone()
    return row_to_queue(row)


def add_queue_step(connection: sqlite3.Connection, payload: PlanQueueStepCreate) -> PlanQueueStep:
    if payload.step_kind not in SAFE_STEP_KINDS:
        raise ValueError(f"unsafe queued step kind: {payload.step_kind}")
    if payload.step_kind == PlanStepKind.DEN and payload.transfer_action not in {
        DenTransferAction.COPY,
        DenTransferAction.MOVE,
    }:
        raise ValueError("den queue steps must be copy or same-filesystem move")
    now = _now()
    connection.execute(
        """
        INSERT INTO plan_queue_steps (
            queue_id, step_order, step_kind, source_root, destination_root, layout_mode,
            transfer_action, folder_template, project_name, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
        ON CONFLICT(queue_id, step_order) DO UPDATE SET
            step_kind = excluded.step_kind,
            source_root = excluded.source_root,
            destination_root = excluded.destination_root,
            layout_mode = excluded.layout_mode,
            transfer_action = excluded.transfer_action,
            folder_template = excluded.folder_template,
            project_name = excluded.project_name,
            updated_at = excluded.updated_at
        """,
        (
            payload.queue_id,
            payload.step_order,
            payload.step_kind.value,
            str(payload.source_root) if payload.source_root else None,
            str(payload.destination_root) if payload.destination_root else None,
            payload.layout_mode.value if payload.layout_mode else None,
            payload.transfer_action.value if payload.transfer_action else None,
            payload.folder_template,
            payload.project_name,
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT * FROM plan_queue_steps WHERE queue_id = ? AND step_order = ?",
        (payload.queue_id, payload.step_order),
    ).fetchone()
    return row_to_step(row)


def get_queue_by_name(connection: sqlite3.Connection, name: str) -> PlanQueue | None:
    row = connection.execute("SELECT * FROM plan_queues WHERE name = ?", (name,)).fetchone()
    return row_to_queue(row) if row else None


def list_queues(connection: sqlite3.Connection) -> list[PlanQueue]:
    rows = connection.execute(
        "SELECT * FROM plan_queues ORDER BY updated_at DESC, name ASC"
    ).fetchall()
    return [row_to_queue(row) for row in rows]


def list_queue_steps(connection: sqlite3.Connection, queue_id: int) -> list[PlanQueueStep]:
    rows = connection.execute(
        "SELECT * FROM plan_queue_steps WHERE queue_id = ? ORDER BY step_order ASC",
        (queue_id,),
    ).fetchall()
    return [row_to_step(row) for row in rows]


def row_to_queue(row: sqlite3.Row) -> PlanQueue:
    return PlanQueue(
        queue_id=row["queue_id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        status=row["status"],
        notes=row["notes"],
    )


def row_to_step(row: sqlite3.Row) -> PlanQueueStep:
    return PlanQueueStep(
        step_id=row["step_id"],
        queue_id=row["queue_id"],
        step_order=row["step_order"],
        step_kind=PlanStepKind(row["step_kind"]),
        source_root=Path(row["source_root"]) if row["source_root"] else None,
        destination_root=Path(row["destination_root"]) if row["destination_root"] else None,
        layout_mode=DenLayoutMode(row["layout_mode"]) if row["layout_mode"] else None,
        transfer_action=DenTransferAction(row["transfer_action"]) if row["transfer_action"] else None,
        folder_template=row["folder_template"],
        project_name=row["project_name"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
