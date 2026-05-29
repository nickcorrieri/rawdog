# Author: Nicholas Corrieri

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rawdog import cli
from rawdog.config import build_config
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
    OrganizationMode,
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


def test_skipped_row_lines_show_full_source_and_destination() -> None:
    row = _row(3, "skipped_existing_same_name_size", "not_applicable")

    lines = cli._skipped_row_lines(row)

    assert "Reason: destination already has same name and size" in lines
    assert f"Source: {row.source_path}" in lines
    assert f"Destination: {row.destination_path}" in lines


def test_post_execution_reports_write_source_and_den_context(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "den"
    source.mkdir()
    destination.mkdir()
    now = datetime.now(UTC)
    plan = cli.ExecutionPlan(
        plan_id=33,
        plan_kind="den",
        status=ExecutionPlanStatus.FAILED,
        what="move RAW files",
        subject=f"{source} -> {destination}",
        expected_result="files should be in den",
        execution_summary="Transferred 1; skipped 1; failed 1.",
        post_audit_summary="Destination audit incomplete.",
        source_root=source,
        destination_root=destination,
        created_at=now,
        updated_at=now,
    )
    rows = [
        _row(1, "moved", "destination_verified"),
        _row(2, "skipped_existing_same_name_size", "not_applicable"),
        _row(3, "failed", "not_audited", error="Operation not permitted"),
    ]

    paths = cli._write_post_execution_reports(plan, rows)

    assert source / "RAWDOG_REPORTS" / "PLAN_33_skipped.txt" in paths
    assert destination / "RAWDOG_REPORTS" / "PLAN_33_failures.txt" in paths
    skipped_text = (source / "RAWDOG_REPORTS" / "PLAN_33_skipped.txt").read_text(encoding="utf-8")
    failure_text = (destination / "RAWDOG_REPORTS" / "PLAN_33_failures.txt").read_text(encoding="utf-8")
    assert "This report is not a delete instruction." in skipped_text
    assert "Operation not permitted" in failure_text


def test_force_move_duplicates_removes_only_sha_verified_sources(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    source_root = tmp_path / "source"
    destination_root = tmp_path / "den"
    source = source_root / "IMG_0001.CR3"
    destination = destination_root / "IMG_0001.CR3"
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"same bytes")
    destination.write_bytes(b"same bytes")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    with session(database) as connection:
        plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="move RAW files",
                subject=f"{source_root} -> {destination_root}",
                expected_result="source duplicate can be removed after hash verification",
                source_root=source_root,
                destination_root=destination_root,
            ),
        )
        add_execution_plan_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=source,
                    destination_path=destination,
                    size_bytes=len(b"same bytes"),
                    transfer_action=DenTransferAction.MOVE,
                    status="skipped_existing_same_name_size",
                )
            ],
        )
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: f"FORCE MOVE DUPLICATES PLAN {plan.plan_id}")

    cli.plans_force_move_duplicates(plan.plan_id, limit=10, dry_run=False, confirm_each=False)

    assert not source.exists()
    assert destination.read_bytes() == b"same bytes"
    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].status == "source_removed_verified_duplicate"
    assert rows[0].audit_status == "source_removed_after_sha256_match"


def test_force_move_duplicates_rejects_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    source_root = tmp_path / "source"
    destination_root = tmp_path / "den"
    source = source_root / "IMG_0001.CR3"
    destination = destination_root / "IMG_0001.CR3"
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"abcd")
    destination.write_bytes(b"wxyz")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    with session(database) as connection:
        plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="den",
                what="move RAW files",
                subject=f"{source_root} -> {destination_root}",
                expected_result="mismatches stay put",
                source_root=source_root,
                destination_root=destination_root,
            ),
        )
        add_execution_plan_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=source,
                    destination_path=destination,
                    size_bytes=4,
                    transfer_action=DenTransferAction.MOVE,
                    status="skipped_existing_same_name_size",
                )
            ],
        )
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))

    cli.plans_force_move_duplicates(plan.plan_id, limit=10, dry_run=False, confirm_each=False)

    assert source.exists()
    assert destination.exists()
    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].status == "skipped_existing_same_name_size"


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
