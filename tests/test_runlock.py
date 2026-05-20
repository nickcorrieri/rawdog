# Author: Nicholas Corrieri

import json
import os
from pathlib import Path

import pytest

from rawdog.runlock import (
    ActiveRunError,
    active_run_is_alive,
    active_run_path,
    begin_active_run,
    clear_active_run,
    finish_active_run,
    read_active_run,
)


def test_active_run_marker_blocks_while_process_is_alive(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"

    run = begin_active_run(database, plan_id=42, what="copy RAW/camera video files")

    assert run.plan_id == 42
    assert run.pid == os.getpid()
    assert read_active_run(database) == run
    assert active_run_is_alive(run)
    with pytest.raises(ActiveRunError, match="already marked active"):
        begin_active_run(database, plan_id=43, what="another plan")

    finish_active_run(database, plan_id=42)

    assert read_active_run(database) is None


def test_active_run_marker_requires_force_clear_when_stale(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    path = active_run_path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "plan_id": 7,
                "pid": 999_999_999,
                "started_at": "2026-05-20T00:00:00+00:00",
                "what": "old run",
            }
        )
    )

    with pytest.raises(ActiveRunError, match="Stale active-run marker"):
        begin_active_run(database, plan_id=8, what="new run")

    assert clear_active_run(database)
    assert read_active_run(database) is None
