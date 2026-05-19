# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rawdog.models import (
    DenTransferAction,
    ExecutionPlan,
    ExecutionPlanCreate,
    ExecutionPlanRow,
    ExecutionPlanRowCreate,
    ExecutionPlanStatus,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_execution_plan(
    connection: sqlite3.Connection,
    payload: ExecutionPlanCreate,
) -> ExecutionPlan:
    now = _now()
    connection.execute(
        """
        INSERT INTO execution_plans (
            plan_kind, status, what, subject, expected_result, execution_summary,
            post_audit_summary, source_root, destination_root, queue_id, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.plan_kind,
            ExecutionPlanStatus.PLANNED.value,
            payload.what,
            payload.subject,
            payload.expected_result,
            payload.execution_summary,
            payload.post_audit_summary,
            str(payload.source_root) if payload.source_root else None,
            str(payload.destination_root) if payload.destination_root else None,
            payload.queue_id,
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT * FROM execution_plans WHERE plan_id = last_insert_rowid()"
    ).fetchone()
    return row_to_plan(row)


def add_execution_plan_rows(
    connection: sqlite3.Connection,
    plan_id: int,
    rows: list[ExecutionPlanRowCreate],
) -> None:
    connection.executemany(
        """
        INSERT INTO execution_plan_rows (
            plan_id, source_path, destination_path, size_bytes, transfer_action, status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                plan_id,
                str(row.source_path),
                str(row.destination_path),
                row.size_bytes,
                row.transfer_action.value,
                row.status,
            )
            for row in rows
        ],
    )


def get_execution_plan(connection: sqlite3.Connection, plan_id: int) -> ExecutionPlan | None:
    row = connection.execute(
        "SELECT * FROM execution_plans WHERE plan_id = ?",
        (plan_id,),
    ).fetchone()
    return row_to_plan(row) if row else None


def get_latest_execution_plan(connection: sqlite3.Connection) -> ExecutionPlan | None:
    row = connection.execute(
        "SELECT * FROM execution_plans ORDER BY updated_at DESC, plan_id DESC LIMIT 1"
    ).fetchone()
    return row_to_plan(row) if row else None


def list_execution_plans(connection: sqlite3.Connection, limit: int = 10) -> list[ExecutionPlan]:
    rows = connection.execute(
        "SELECT * FROM execution_plans ORDER BY updated_at DESC, plan_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [row_to_plan(row) for row in rows]


def list_execution_plans_for_prune(
    connection: sqlite3.Connection,
    *,
    keep: int,
    before: datetime | None = None,
    include_done: bool = False,
) -> list[ExecutionPlan]:
    rows = connection.execute(
        "SELECT * FROM execution_plans ORDER BY updated_at DESC, plan_id DESC"
    ).fetchall()
    plans = [row_to_plan(row) for row in rows]
    protected_ids = {plan.plan_id for plan in plans[:keep]}
    allowed_statuses = {ExecutionPlanStatus.PLANNED}
    if include_done:
        allowed_statuses.add(ExecutionPlanStatus.DONE)
    prunable: list[ExecutionPlan] = []
    for plan in plans:
        if plan.plan_id in protected_ids:
            continue
        if plan.status not in allowed_statuses:
            continue
        if before is not None and plan.updated_at >= before:
            continue
        prunable.append(plan)
    return prunable


def delete_execution_plan(connection: sqlite3.Connection, plan_id: int) -> None:
    connection.execute("DELETE FROM execution_plans WHERE plan_id = ?", (plan_id,))


def list_execution_plan_rows(
    connection: sqlite3.Connection,
    plan_id: int,
) -> list[ExecutionPlanRow]:
    rows = connection.execute(
        "SELECT * FROM execution_plan_rows WHERE plan_id = ? ORDER BY row_id ASC",
        (plan_id,),
    ).fetchall()
    return [row_to_plan_row(row) for row in rows]


def mark_execution_plan_started(connection: sqlite3.Connection, plan_id: int) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE execution_plans
        SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
        WHERE plan_id = ?
        """,
        (ExecutionPlanStatus.STARTED.value, now, now, plan_id),
    )


def mark_execution_plan_finished(
    connection: sqlite3.Connection,
    plan_id: int,
    status: ExecutionPlanStatus,
    execution_summary: str,
    post_audit_summary: str,
) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE execution_plans
        SET status = ?, execution_summary = ?, post_audit_summary = ?,
            completed_at = ?, updated_at = ?
        WHERE plan_id = ?
        """,
        (status.value, execution_summary, post_audit_summary, now, now, plan_id),
    )


def update_execution_plan_row(
    connection: sqlite3.Connection,
    row_id: int,
    *,
    status: str,
    audit_status: str | None = None,
    error: str | None = None,
) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE execution_plan_rows
        SET status = ?, audit_status = ?, error = ?, executed_at = ?,
            audited_at = CASE WHEN ? IS NULL THEN audited_at ELSE ? END
        WHERE row_id = ?
        """,
        (status, audit_status, error, now, audit_status, now, row_id),
    )


def row_to_plan(row: sqlite3.Row) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=row["plan_id"],
        plan_kind=row["plan_kind"],
        status=ExecutionPlanStatus(row["status"]),
        what=row["what"],
        subject=row["subject"],
        expected_result=row["expected_result"],
        execution_summary=row["execution_summary"],
        post_audit_summary=row["post_audit_summary"],
        source_root=Path(row["source_root"]) if row["source_root"] else None,
        destination_root=Path(row["destination_root"]) if row["destination_root"] else None,
        queue_id=row["queue_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def row_to_plan_row(row: sqlite3.Row) -> ExecutionPlanRow:
    return ExecutionPlanRow(
        row_id=row["row_id"],
        plan_id=row["plan_id"],
        source_path=Path(row["source_path"]),
        destination_path=Path(row["destination_path"]),
        size_bytes=row["size_bytes"],
        transfer_action=DenTransferAction(row["transfer_action"]),
        status=row["status"],
        audit_status=row["audit_status"],
        executed_at=datetime.fromisoformat(row["executed_at"]) if row["executed_at"] else None,
        audited_at=datetime.fromisoformat(row["audited_at"]) if row["audited_at"] else None,
        error=row["error"],
    )
