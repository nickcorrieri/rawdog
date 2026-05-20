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


def active_run_path(database_path: Path) -> Path:
    return database_path.expanduser().resolve().parent / ACTIVE_RUN_FILE


def read_active_run(database_path: Path) -> ActiveRun | None:
    path = active_run_path(database_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return ActiveRun(
        plan_id=int(data["plan_id"]),
        pid=int(data["pid"]),
        started_at=datetime.fromisoformat(data["started_at"]),
        what=str(data.get("what") or ""),
    )


def active_run_is_alive(run: ActiveRun) -> bool:
    try:
        os.kill(run.pid, 0)
    except OSError:
        return False
    return True


def begin_active_run(database_path: Path, *, plan_id: int, what: str) -> ActiveRun:
    existing = read_active_run(database_path)
    if existing and active_run_is_alive(existing):
        raise ActiveRunError(
            f"Plan #{existing.plan_id} is already marked active by PID {existing.pid}. "
            "Avoid upgrades, disconnects, or another copy/move until it finishes."
        )
    if existing:
        raise ActiveRunError(
            f"Stale active-run marker found for plan #{existing.plan_id} from PID {existing.pid}. "
            "If no RAWDOG copy/move is running, clear it with: rawdog plans active-clear --force"
        )
    run = ActiveRun(
        plan_id=plan_id,
        pid=os.getpid(),
        started_at=datetime.now(UTC),
        what=what,
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
