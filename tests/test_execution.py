# Author: Nicholas Corrieri

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rawdog import cli
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


def test_plan_review_filter_includes_failed_skipped_and_review_rows(tmp_path: Path) -> None:
    rows = [
        _row(1, "copied", "destination_verified"),
        _row(2, "failed", "not_audited", error="disk full"),
        _row(3, "skipped_existing_same_name_size", "not_applicable"),
        _row(4, "planned", "destination_missing"),
        _row(5, "planned", "needs_partial_review"),
    ]

    review_rows = [row for row in rows if cli._needs_plan_review(row)]

    assert [row.row_id for row in review_rows] == [2, 3, 4, 5]


def test_wings_command_builder_wraps_rawdog_subcommand() -> None:
    command = cli._build_wings_command(
        caffeinate_path="/usr/bin/caffeinate",
        rawdog_executable="/opt/homebrew/bin/rawdog",
        args=["plans", "resume", "10"],
        pid=None,
    )

    assert command == [
        "/usr/bin/caffeinate",
        "-dimsu",
        "/opt/homebrew/bin/rawdog",
        "plans",
        "resume",
        "10",
    ]


def test_wings_command_builder_can_attach_to_pid() -> None:
    command = cli._build_wings_command(
        caffeinate_path="/usr/bin/caffeinate",
        rawdog_executable="/opt/homebrew/bin/rawdog",
        args=[],
        pid=12345,
    )

    assert command == ["/usr/bin/caffeinate", "-dimsu", "-w", "12345"]


def _row(
    row_id: int,
    status: str,
    audit_status: str | None,
    *,
    error: str | None = None,
):
    return cli.ExecutionPlanRow(
        row_id=row_id,
        plan_id=10,
        source_path=Path(f"/source/{row_id}.CR3"),
        destination_path=Path(f"/dest/{row_id}.CR3"),
        size_bytes=3,
        transfer_action=DenTransferAction.COPY,
        status=status,
        audit_status=audit_status,
        error=error,
    )
