# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.execution import (
    add_execution_plan_rows,
    create_execution_plan,
    list_execution_plan_rows,
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
