# Author: Nicholas Corrieri

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rawdog.db import initialize, session
from rawdog.execution import (
    add_execution_plan_rows,
    create_execution_plan,
    delete_execution_plan,
    list_execution_plan_rows,
    list_execution_plans_for_prune,
)
from rawdog.models import (
    DenTransferAction,
    ExecutionPlanCreate,
    ExecutionPlanRowCreate,
    ExecutionPlanStatus,
)


def test_create_execution_plan_with_rows(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="copy RAW files into a RAWDOG destination",
                subject=f"{tmp_path / 'source'} -> {tmp_path / 'archive'}",
                expected_result="one file should be copied",
                source_root=tmp_path / "source",
                destination_root=tmp_path / "archive",
            ),
        )
        add_execution_plan_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=tmp_path / "source" / "IMG_0001.CR3",
                    destination_path=tmp_path / "archive" / "IMG_0001.CR3",
                    size_bytes=3,
                    transfer_action=DenTransferAction.COPY,
                    status="plan_copy",
                )
            ],
        )

    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)

    assert plan.status == ExecutionPlanStatus.PLANNED
    assert rows[0].status == "plan_copy"
    assert rows[0].transfer_action == DenTransferAction.COPY


def test_prune_candidates_keep_newest_and_skip_started(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        old_plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="old dry run",
                subject="source -> archive",
                expected_result="old",
            ),
        )
        started_plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="started",
                subject="source -> archive",
                expected_result="started",
            ),
        )
        newest_plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="newest",
                subject="source -> archive",
                expected_result="newest",
            ),
        )
        old_updated = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        connection.execute(
            "UPDATE execution_plans SET updated_at = ? WHERE plan_id = ?",
            (old_updated, old_plan.plan_id),
        )
        connection.execute(
            "UPDATE execution_plans SET status = ? WHERE plan_id = ?",
            (ExecutionPlanStatus.STARTED.value, started_plan.plan_id),
        )

    with session(database) as connection:
        candidates = list_execution_plans_for_prune(connection, keep=1)

    assert [plan.plan_id for plan in candidates] == [old_plan.plan_id]
    assert newest_plan.plan_id not in [plan.plan_id for plan in candidates]


def test_delete_execution_plan_cascades_rows(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="dry run",
                subject="source -> archive",
                expected_result="one row",
            ),
        )
        add_execution_plan_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=tmp_path / "source" / "IMG_0001.CR3",
                    destination_path=tmp_path / "archive" / "IMG_0001.CR3",
                    size_bytes=3,
                    transfer_action=DenTransferAction.COPY,
                    status="plan_copy",
                )
            ],
        )
        delete_execution_plan(connection, plan.plan_id)

    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)

    assert rows == []
