# Author: Nicholas Corrieri

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ACTIVE_RUN_FILE = "active-run.json"


class ActiveRunError(RuntimeError):
    """Raised when a plan execution marker blocks a new run."""


@dataclass(frozen=True, kw_only=True)
class ActiveRun:
    plan_id: int
    pid: int
    started_at: datetime
    what: str
    plan_kind: str = ""
    subject: str = ""
    source_root: Path | None = None
    destination_root: Path | None = None
    store_kind: str = ""
    write_lock: bool = True


def active_run_path(database_path: Path) -> Path:
    return database_path.expanduser().resolve().parent / ACTIVE_RUN_FILE


def read_active_run(database_path: Path) -> ActiveRun | None:
    path = active_run_path(database_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    source_root = data.get("source_root")
    destination_root = data.get("destination_root")
    return ActiveRun(
        plan_id=int(data["plan_id"]),
        pid=int(data["pid"]),
        started_at=datetime.fromisoformat(data["started_at"]),
        what=str(data.get("what") or ""),
        plan_kind=str(data.get("plan_kind") or ""),
        subject=str(data.get("subject") or ""),
        source_root=Path(source_root) if source_root else None,
        destination_root=Path(destination_root) if destination_root else None,
        store_kind=str(data.get("store_kind") or ""),
        write_lock=bool(data.get("write_lock", True)),
    )


def active_run_is_alive(run: ActiveRun) -> bool:
    try:
        os.kill(run.pid, 0)
    except OSError:
        return False
    return True


def _active_run_error_message(run: ActiveRun, *, stale: bool = False) -> str:
    state = "Stale active-run marker found" if stale else "Plan is already marked active"
    details = [
        f"{state} for plan #{run.plan_id} ({run.plan_kind or 'unknown kind'}) by PID {run.pid}.",
        f"What: {run.what or 'unknown'}",
    ]
    if run.subject:
        details.append(f"Subject: {run.subject}")
    if run.source_root or run.destination_root:
        details.append(f"Path: {run.source_root or '?'} -> {run.destination_root or '?'}")
    if run.store_kind:
        details.append(f"Store kind: {run.store_kind}")
    details.append(f"Write lock: {'yes' if run.write_lock else 'no'}")
    if stale:
        details.append("If no RAWDOG copy/move is running, clear it with: rawdog plans active-clear --force")
    else:
        details.append("This command is blocked until that active run finishes or the marker is cleared.")
    return " ".join(details)


def begin_active_run(
    database_path: Path,
    *,
    plan_id: int,
    what: str,
    plan_kind: str = "",
    subject: str = "",
    source_root: Path | None = None,
    destination_root: Path | None = None,
    store_kind: str = "",
    write_lock: bool = True,
) -> ActiveRun:
    existing = read_active_run(database_path)
    if existing and active_run_is_alive(existing):
        raise ActiveRunError(_active_run_error_message(existing))
    if existing:
        raise ActiveRunError(_active_run_error_message(existing, stale=True))
    run = ActiveRun(
        plan_id=plan_id,
        pid=os.getpid(),
        started_at=datetime.now(UTC),
        what=what,
        plan_kind=plan_kind,
        subject=subject,
        source_root=source_root,
        destination_root=destination_root,
        store_kind=store_kind,
        write_lock=write_lock,
    )
    path = active_run_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(
            {
                "plan_id": run.plan_id,
                "pid": run.pid,
                "started_at": run.started_at.isoformat(),
                "what": run.what,
                "plan_kind": run.plan_kind,
                "subject": run.subject,
                "source_root": str(run.source_root) if run.source_root else None,
                "destination_root": str(run.destination_root) if run.destination_root else None,
                "store_kind": run.store_kind,
                "write_lock": run.write_lock,
            },
            indent=2,
        )
    )
    tmp_path.replace(path)
    return run


def finish_active_run(database_path: Path, *, plan_id: int) -> None:
    try:
        run = read_active_run(database_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return
    if run and run.plan_id == plan_id and run.pid == os.getpid():
        active_run_path(database_path).unlink(missing_ok=True)


def clear_active_run(database_path: Path) -> bool:
    path = active_run_path(database_path)
    if not path.exists():
        return False
    path.unlink()
    return True
