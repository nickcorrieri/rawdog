# Author: Nicholas Corrieri

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rawdog.models import (
    PlanningJob,
    PlanningJobCreate,
    PlanningJobItem,
    PlanningJobItemCreate,
    PlanningJobStatus,
    StoreKind,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_planning_job(
    connection: sqlite3.Connection,
    payload: PlanningJobCreate,
) -> PlanningJob:
    now = _now()
    connection.execute(
        """
        INSERT INTO planning_jobs (
            job_kind, status, phase, subject, root_path, store_kind, options_json,
            message, created_at, updated_at, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.job_kind,
            PlanningJobStatus.RUNNING.value,
            payload.phase,
            payload.subject,
            str(payload.root_path),
            payload.store_kind.value,
            payload.options_json,
            payload.message,
            now,
            now,
            now,
        ),
    )
    row = connection.execute("SELECT * FROM planning_jobs WHERE planning_job_id = last_insert_rowid()").fetchone()
    return row_to_planning_job(row)


def get_planning_job(connection: sqlite3.Connection, planning_job_id: int) -> PlanningJob | None:
    row = connection.execute(
        "SELECT * FROM planning_jobs WHERE planning_job_id = ?",
        (planning_job_id,),
    ).fetchone()
    return row_to_planning_job(row) if row else None


def get_latest_planning_job(connection: sqlite3.Connection) -> PlanningJob | None:
    row = connection.execute(
        "SELECT * FROM planning_jobs ORDER BY updated_at DESC, planning_job_id DESC LIMIT 1"
    ).fetchone()
    return row_to_planning_job(row) if row else None


def update_planning_job(
    connection: sqlite3.Connection,
    planning_job_id: int,
    *,
    status: PlanningJobStatus | None = None,
    phase: str | None = None,
    total_files: int | None = None,
    total_bytes: int | None = None,
    completed_files: int | None = None,
    total_batches: int | None = None,
    completed_batches: int | None = None,
    current_path: Path | str | None = None,
    execution_plan_id: int | None = None,
    message: str | None = None,
    complete: bool = False,
) -> None:
    current_path_text = str(current_path) if current_path is not None else None
    now = _now()
    connection.execute(
        """
        UPDATE planning_jobs
        SET status = COALESCE(?, status),
            phase = COALESCE(?, phase),
            total_files = COALESCE(?, total_files),
            total_bytes = COALESCE(?, total_bytes),
            completed_files = COALESCE(?, completed_files),
            total_batches = COALESCE(?, total_batches),
            completed_batches = COALESCE(?, completed_batches),
            current_path = COALESCE(?, current_path),
            execution_plan_id = COALESCE(?, execution_plan_id),
            message = COALESCE(?, message),
            updated_at = ?,
            completed_at = CASE WHEN ? THEN ? ELSE completed_at END
        WHERE planning_job_id = ?
        """,
        (
            status.value if status else None,
            phase,
            total_files,
            total_bytes,
            completed_files,
            total_batches,
            completed_batches,
            current_path_text,
            execution_plan_id,
            message,
            now,
            1 if complete else 0,
            now,
            planning_job_id,
        ),
    )


def restart_planning_job(connection: sqlite3.Connection, planning_job_id: int) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE planning_jobs
        SET status = ?, phase = 'scan', completed_files = 0, completed_batches = 0,
            current_path = NULL, message = ?, updated_at = ?, started_at = COALESCE(started_at, ?),
            completed_at = NULL
        WHERE planning_job_id = ?
        """,
        (
            PlanningJobStatus.RUNNING.value,
            "Planning job resumed.",
            now,
            now,
            planning_job_id,
        ),
    )


def replace_planning_job_items(
    connection: sqlite3.Connection,
    planning_job_id: int,
    items: list[PlanningJobItemCreate],
) -> None:
    now = _now()
    connection.execute("DELETE FROM planning_job_items WHERE planning_job_id = ?", (planning_job_id,))
    connection.executemany(
        """
        INSERT INTO planning_job_items (
            planning_job_id, source_path, relative_path, size_bytes, mtime_ns, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                planning_job_id,
                str(item.source_path),
                str(item.relative_path),
                item.size_bytes,
                item.mtime_ns,
                now,
            )
            for item in items
        ],
    )


def update_planning_job_item_capture(
    connection: sqlite3.Connection,
    planning_job_id: int,
    source_path: Path,
    captured_at: datetime,
    *,
    basis: str,
) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE planning_job_items
        SET captured_at = ?, capture_basis = ?, updated_at = ?
        WHERE planning_job_id = ? AND source_path = ?
        """,
        (
            captured_at.isoformat(),
            basis,
            now,
            planning_job_id,
            str(source_path),
        ),
    )


def list_planning_job_items(
    connection: sqlite3.Connection,
    planning_job_id: int,
) -> list[PlanningJobItem]:
    rows = connection.execute(
        """
        SELECT * FROM planning_job_items
        WHERE planning_job_id = ?
        ORDER BY planning_job_item_id ASC
        """,
        (planning_job_id,),
    ).fetchall()
    return [row_to_planning_job_item(row) for row in rows]


def row_to_planning_job(row: sqlite3.Row) -> PlanningJob:
    return PlanningJob(
        planning_job_id=row["planning_job_id"],
        job_kind=row["job_kind"],
        status=PlanningJobStatus(row["status"]),
        phase=row["phase"],
        subject=row["subject"],
        root_path=Path(row["root_path"]),
        store_kind=StoreKind(row["store_kind"]),
        options_json=row["options_json"],
        total_files=row["total_files"],
        total_bytes=row["total_bytes"],
        completed_files=row["completed_files"],
        total_batches=row["total_batches"],
        completed_batches=row["completed_batches"],
        current_path=Path(row["current_path"]) if row["current_path"] else None,
        execution_plan_id=row["execution_plan_id"],
        message=row["message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def row_to_planning_job_item(row: sqlite3.Row) -> PlanningJobItem:
    return PlanningJobItem(
        planning_job_item_id=row["planning_job_item_id"],
        planning_job_id=row["planning_job_id"],
        source_path=Path(row["source_path"]),
        relative_path=Path(row["relative_path"]),
        size_bytes=row["size_bytes"],
        mtime_ns=row["mtime_ns"],
        captured_at=datetime.fromisoformat(row["captured_at"]) if row["captured_at"] else None,
        capture_basis=row["capture_basis"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
