# Author: Nicholas Corrieri

import json
import os
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rawdog import cli
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.execution import (
    add_execution_plan_rows,
    add_execution_plan_time_shift_rows,
    create_execution_plan,
    delete_execution_plan,
    get_execution_plan,
    list_execution_plan_rows,
    list_execution_plan_time_shift_rows,
    list_execution_plans_for_prune,
    update_execution_plan_time_shift_row,
)
from rawdog.models import (
    DateGroupMode,
    DenTransferAction,
    ExecutionPlanCreate,
    ExecutionPlanRowCreate,
    ExecutionPlanStatus,
    ExecutionPlanTimeShiftRowCreate,
    OrganizationMode,
)
from rawdog.safety import SafetyError
from rawdog.verifier import capture_file_version, set_ancillary_payloads


def _persist_synthetic_transfer(tmp_path, action=DenTransferAction.COPY, *, skip=False):
    source = tmp_path / "inputs" / "source" / "IMG_0001.CR3"
    destination = tmp_path / "outputs" / "archive" / source.name
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"reviewed")
    if skip:
        destination.write_bytes(b"reviewed")
    database = tmp_path / "state" / "rawdog.sqlite"
    initialize(database)
    with session(database) as connection:
        plan = create_execution_plan(connection, ExecutionPlanCreate(
            plan_kind="den", what="synthetic transfer", subject="reviewed fixture",
            expected_result="preserve reviewed identity", source_root=source.parent,
            destination_root=destination.parent,
        ))
        add_execution_plan_rows(connection, plan.plan_id, [ExecutionPlanRowCreate(
            source_path=source, destination_path=destination, size_bytes=8,
            transfer_action=action, status="skip_existing_same_name_size" if skip else "plan_copy",
        )])
        row = list_execution_plan_rows(connection, plan.plan_id)[0]
    return build_config(OrganizationMode.PROJECT, database_path=database), plan, row


def _replace_fixture_with_alias(tmp_path, selected, *, ancestor, broken):
    alias = selected.parent if ancestor else selected
    is_directory = alias.is_dir()
    retained = tmp_path / "retained-alias-object"
    alias.rename(retained)
    target = tmp_path / "missing-alias-target" if broken else retained
    alias.symlink_to(target, target_is_directory=is_directory)
    return alias, retained


@contextmanager
def _forbid_alias_reads(monkeypatch, alias):
    real_stat, real_lstat = os.stat, os.lstat
    real_resolve, real_open = Path.resolve, Path.open

    def check(path, *, follow):
        if isinstance(path, int):
            return
        selected = Path(os.fsdecode(path))
        if alias in selected.parents or (follow and selected == alias):
            raise AssertionError(f"metadata/read followed fixture alias: {selected}")

    def guarded_stat(path, *args, **kwargs):
        check(path, follow=kwargs.get("follow_symlinks", True))
        return real_stat(path, *args, **kwargs)

    def guarded_lstat(path, *args, **kwargs):
        check(path, follow=False)
        return real_lstat(path, *args, **kwargs)

    def guarded_resolve(path, *args, **kwargs):
        check(path, follow=True)
        return real_resolve(path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        check(path, follow=True)
        return real_open(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "stat", guarded_stat)
        scoped.setattr(os, "lstat", guarded_lstat)
        scoped.setattr(Path, "resolve", guarded_resolve)
        scoped.setattr(Path, "open", guarded_open)
        yield


@pytest.mark.parametrize("field", ["database", "source_root", "destination_root", "source_row", "destination_row"])
@pytest.mark.parametrize("ancestor", [False, True], ids=["leaf", "ancestor"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_execution_rejects_persisted_alias_before_space_or_lock_reads(tmp_path, monkeypatch, field, ancestor, broken):
    config, plan, row = _persist_synthetic_transfer(tmp_path)
    row.destination_path.write_bytes(b"foreign!")
    selected = {
        "database": config.database_path, "source_root": plan.source_root,
        "destination_root": plan.destination_root, "source_row": row.source_path,
        "destination_row": row.destination_path,
    }[field]
    alias, retained = _replace_fixture_with_alias(tmp_path, selected, ancestor=ancestor, broken=broken)

    def forbidden(*args, **kwargs):
        raise AssertionError("execution checked free space or acquired locks before path refusal")

    with monkeypatch.context() as scoped, _forbid_alias_reads(monkeypatch, alias):
        scoped.setattr(cli.shutil, "disk_usage", forbidden)
        scoped.setattr(cli, "begin_active_run", forbidden)
        with pytest.raises(SafetyError, match="symlink"):
            cli._execute_persisted_plan(config, plan.plan_id)

    def preserved(path):
        return retained / path.relative_to(alias) if path.is_relative_to(alias) else path

    assert preserved(row.source_path).read_bytes() == b"reviewed"
    assert preserved(row.destination_path).read_bytes() == b"foreign!"
    with session(preserved(config.database_path)) as connection:
        assert get_execution_plan(connection, plan.plan_id).status == ExecutionPlanStatus.PLANNED


@pytest.mark.parametrize("entry", ["lock-scope", "reflow"])
@pytest.mark.parametrize("ancestor", [False, True], ids=["leaf", "ancestor"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_execution_rejects_registered_root_before_resolution(tmp_path, monkeypatch, entry, ancestor, broken):
    from rawdog.models import StoreCreate, StoreKind
    from rawdog.stores import create_or_update_store

    config, plan, row = _persist_synthetic_transfer(tmp_path)
    root = tmp_path / "registered" / "store"
    root.mkdir(parents=True)
    with session(config.database_path) as connection:
        store = create_or_update_store(connection, StoreCreate(
            name="synthetic", root_path=root, store_kind=StoreKind.YARD,
        ))
    alias, _ = _replace_fixture_with_alias(tmp_path, root, ancestor=ancestor, broken=broken)

    def forbidden_space_probe(*args, **kwargs):
        raise AssertionError("free-space metadata was probed before registered-root refusal")

    with monkeypatch.context() as scoped, _forbid_alias_reads(monkeypatch, alias):
        scoped.setattr(cli.shutil, "disk_usage", forbidden_space_probe)
        with pytest.raises(SafetyError, match="symlink"):
            if entry == "lock-scope":
                cli._operation_lock_roots([row.source_path], [store], [plan.source_root])
            else:
                cli._run_store_reflow_plan(
                    config, plan.source_root, store_kind=StoreKind.YARD,
                    group_by=DateGroupMode.MONTH, keep_context=False,
                )
    assert row.source_path.read_bytes() == b"reviewed"


@pytest.mark.parametrize("field", ["source_path", "destination_path"])
@pytest.mark.parametrize("ancestor", [False, True], ids=["leaf", "ancestor"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_execution_audit_refuses_alias_before_metadata(tmp_path, monkeypatch, field, ancestor, broken):
    _, _, row = _persist_synthetic_transfer(tmp_path, skip=True)
    alias, _ = _replace_fixture_with_alias(tmp_path, getattr(row, field), ancestor=ancestor, broken=broken)
    with _forbid_alias_reads(monkeypatch, alias):
        assert cli._audit_execution_row(row, "copied") == "needs_identity_review"


@pytest.mark.parametrize("field", ["source_path", "destination_path"])
def test_move_recovery_rejects_alias_inserted_after_preflight(tmp_path, monkeypatch, field):
    config, plan, row = _persist_synthetic_transfer(tmp_path, DenTransferAction.MOVE)
    selected = getattr(row, field)
    foreign = tmp_path / "foreign.CR3"
    foreign.write_bytes(b"foreign!")
    retained = tmp_path / "retained-reviewed.CR3"
    actual = cli._expected_source_version
    arrivals = []
    with ExitStack() as stack:
        def insert_alias(execution_row):
            expected = actual(execution_row)
            assert not arrivals
            arrivals.append(True)
            if selected.exists():
                selected.rename(retained)
            selected.symlink_to(foreign)
            stack.enter_context(_forbid_alias_reads(monkeypatch, selected))
            return expected

        with monkeypatch.context() as scoped:
            scoped.setattr(cli, "_expected_source_version", insert_alias)
            result = cli._execute_persisted_plan(config, plan.plan_id)
    assert arrivals == [True]
    assert result.status == ExecutionPlanStatus.FAILED
    assert foreign.read_bytes() == b"foreign!"
    assert (retained if field == "source_path" else row.source_path).read_bytes() == b"reviewed"
    with session(config.database_path) as connection:
        failed = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert failed.status == "failed"
    assert "symlink" in failed.error


@pytest.mark.parametrize("action", [DenTransferAction.COPY, DenTransferAction.MOVE])
@pytest.mark.parametrize("at_handoff", [False, True], ids=["after-persistence", "primitive-entry"])
def test_persisted_execution_holds_changed_reviewed_source(tmp_path, monkeypatch, action, at_handoff):
    config, plan, row = _persist_synthetic_transfer(tmp_path, action)
    reviewed = json.loads(row.source_version)
    primitive_name = "append_only_move" if action == DenTransferAction.MOVE else "append_only_copy"
    actual = getattr(cli, primitive_name)
    arrivals = []

    def change_source():
        row.source_path.write_bytes(b"changed!")
        os.utime(row.source_path, ns=(row.source_path.stat().st_atime_ns, reviewed["mtime_ns"]))

    def checked_handoff(*args, **kwargs):
        arrivals.append(kwargs["expected_source_version"])
        if at_handoff:
            change_source()
        return actual(*args, **kwargs)

    if not at_handoff:
        change_source()
    monkeypatch.setattr(cli, primitive_name, checked_handoff)
    result = cli._execute_persisted_plan(config, plan.plan_id)
    assert arrivals == [reviewed]
    assert result.status == ExecutionPlanStatus.FAILED
    assert row.source_path.read_bytes() == b"changed!"
    assert not row.destination_path.exists()
    with session(config.database_path) as connection:
        failed = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert failed.source_version == row.source_version
    assert failed.status == "failed"
    assert "changed" in failed.error


def test_persisted_skip_rejects_equal_payload_replacement(tmp_path, monkeypatch):
    config, plan, row = _persist_synthetic_transfer(tmp_path, skip=True)
    retained = tmp_path / "retained-destination.CR3"
    row.destination_path.rename(retained)
    row.destination_path.write_bytes(b"reviewed")

    def forbidden(*args, **kwargs):
        raise AssertionError("stale skip attempted a transfer")

    monkeypatch.setattr(cli, "append_only_copy", forbidden)
    monkeypatch.setattr(cli, "append_only_move", forbidden)
    result = cli._execute_persisted_plan(config, plan.plan_id)
    assert result.status == ExecutionPlanStatus.NEEDS_REVIEW
    with session(config.database_path) as connection:
        audited = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert audited.audit_status == "needs_identity_review"
    assert audited.destination_version == row.destination_version
    assert row.source_path.read_bytes() == row.destination_path.read_bytes() == retained.read_bytes() == b"reviewed"


def test_failed_destination_audit_does_not_finish_persisted_plan(tmp_path, monkeypatch):
    config, plan, row = _persist_synthetic_transfer(tmp_path)
    actual = cli.append_only_copy

    def corrupt_after_copy(*args, **kwargs):
        status = actual(*args, **kwargs)
        assert status == "copied"
        row.destination_path.write_bytes(b"changed!")
        return status

    monkeypatch.setattr(cli, "append_only_copy", corrupt_after_copy)
    result = cli._execute_persisted_plan(config, plan.plan_id)
    assert result.status == ExecutionPlanStatus.NEEDS_REVIEW
    with session(config.database_path) as connection:
        audited = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert audited.status == "copied"
    assert audited.audit_status == "content_mismatch"
    assert row.source_path.read_bytes() == b"reviewed"
    assert row.destination_path.read_bytes() == b"changed!"


def _synthetic_reflow(tmp_path, monkeypatch):
    root = tmp_path / "reflow"
    source = root / "incoming" / "IMG_0001.CR3"
    destination = root / "2025" / "2025-04" / source.name
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"original")
    destination.write_bytes(b"original")
    captured = datetime(2025, 4, 12, tzinfo=UTC)
    item = cli.InventoryItem(
        path=source, relative_path=source.relative_to(root), size_bytes=8,
        mtime_ns=source.stat().st_mtime_ns,
    )
    monkeypatch.setattr(cli, "_load_or_scan_reflow_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli, "capture_times", lambda paths: {path: captured for path in paths})
    return root, source, destination


@pytest.mark.parametrize("difference", ["bytes", "ancillary", "none"])
def test_reflow_preview_requires_matching_payload_not_just_size(tmp_path, monkeypatch, difference):
    root, source, destination = _synthetic_reflow(tmp_path, monkeypatch)
    if difference == "bytes":
        destination.write_bytes(b"distinct")
    elif difference == "ancillary":
        descriptor = os.open(source, os.O_RDONLY)
        try:
            set_ancillary_payloads(descriptor, {"user.rawdog.synthetic": b"source-only payload"})
        finally:
            os.close(descriptor)
    source_before, destination_before = capture_file_version(source), capture_file_version(destination)
    plan = cli._build_den_reflow_plan(root, group_by=DateGroupMode.MONTH, keep_context=False, drop_context=set())
    assert len(plan.rows) == 1
    assert plan.rows[0].destination_path == destination
    assert plan.rows[0].status == ("skip_existing_same_name_size" if difference == "none" else "collision")
    assert capture_file_version(source) == source_before
    assert capture_file_version(destination) == destination_before


@pytest.mark.parametrize("field", ["source", "destination"])
@pytest.mark.parametrize("ancestor", [False, True], ids=["leaf", "ancestor"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_reflow_preview_rejects_saved_item_or_destination_alias(tmp_path, monkeypatch, field, ancestor, broken):
    root, source, destination = _synthetic_reflow(tmp_path, monkeypatch)
    selected = source if field == "source" else destination
    alias, _ = _replace_fixture_with_alias(tmp_path, selected, ancestor=ancestor, broken=broken)
    # Isolate reflow's destination gate from the chooser's independent refusal.
    monkeypatch.setattr(cli, "destination_path_for_filename_policy", lambda *args, **kwargs: destination)
    with _forbid_alias_reads(monkeypatch, alias):
        with pytest.raises(SafetyError, match="symlink"):
            cli._build_den_reflow_plan(root, group_by=DateGroupMode.MONTH, keep_context=False, drop_context=set())


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


def test_legacy_plan_migration_requires_new_review_before_execution(tmp_path: Path) -> None:
    database = tmp_path / "state" / "rawdog.sqlite"
    source = tmp_path / "source" / "IMG_0001.CR3"
    destination = tmp_path / "archive" / source.name
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_bytes(b"review me")
    initialize(database)
    with session(database) as connection:
        plan = create_execution_plan(connection, ExecutionPlanCreate(
            plan_kind="den", what="legacy copy", subject="synthetic migration",
            expected_result="hold legacy evidence", source_root=source.parent,
            destination_root=destination.parent,
        ))
        add_execution_plan_rows(connection, plan.plan_id, [ExecutionPlanRowCreate(
            source_path=source, destination_path=destination, size_bytes=9,
            transfer_action=DenTransferAction.COPY, status="plan_copy",
        )])
        connection.execute("ALTER TABLE execution_plan_rows DROP COLUMN source_version")
        connection.execute("ALTER TABLE execution_plan_rows DROP COLUMN destination_version")
    initialize(database)
    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].source_version is None
    assert rows[0].destination_version is None
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    result = cli._execute_persisted_plan(config, plan.plan_id)
    assert result.status == ExecutionPlanStatus.FAILED
    assert not destination.exists()
    assert source.read_bytes() == b"review me"
    with session(database) as connection:
        rows = list_execution_plan_rows(connection, plan.plan_id)
    assert "reviewed source identity" in rows[0].error


@pytest.mark.parametrize("completed", [False, True])
def test_move_recovery_and_reaudit_require_original_source_object(tmp_path: Path, completed: bool) -> None:
    database = tmp_path / "state" / "rawdog.sqlite"
    source = tmp_path / "source" / "IMG_0001.CR3"
    destination = tmp_path / "archive" / source.name
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_bytes(b"same bytes")
    initialize(database)
    with session(database) as connection:
        plan = create_execution_plan(connection, ExecutionPlanCreate(
            plan_kind="den", what="reviewed move", subject="synthetic identity",
            expected_result="only the reviewed source object counts", source_root=source.parent,
            destination_root=destination.parent,
        ))
        add_execution_plan_rows(connection, plan.plan_id, [ExecutionPlanRowCreate(
            source_path=source, destination_path=destination, size_bytes=10,
            transfer_action=DenTransferAction.MOVE, status="plan_copy",
        )])
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    if completed:
        assert cli._execute_persisted_plan(config, plan.plan_id).status == ExecutionPlanStatus.DONE
        destination.rename(tmp_path / "retained-reviewed-object")
    else:
        source.rename(tmp_path / "retained-reviewed-object")
    destination.write_bytes(b"same bytes")
    assert cli._execute_persisted_plan(config, plan.plan_id).status != ExecutionPlanStatus.DONE
    assert destination.read_bytes() == b"same bytes"
    assert (tmp_path / "retained-reviewed-object").read_bytes() == b"same bytes"


@pytest.mark.parametrize("registered", [False, True])
def test_overlapping_row_parents_lock_across_different_root_selections(tmp_path: Path, registered: bool) -> None:
    from rawdog.models import StoreCreate, StoreKind
    from rawdog.runlock import ActiveRunError, begin_active_run, finish_active_run
    from rawdog.stores import create_or_update_store

    broad = tmp_path / "library"
    narrow = broad / "shoot"
    narrow.mkdir(parents=True)
    source = narrow / "IMG_0001.CR3"
    source.write_bytes(b"raw")
    first_db, second_db = tmp_path / "app1" / "rawdog.sqlite", tmp_path / "app2" / "rawdog.sqlite"
    initialize(first_db)
    stores = []
    if registered:
        with session(first_db) as connection:
            stores = [create_or_update_store(connection, StoreCreate(
                name="synthetic", store_kind=StoreKind.YARD, root_path=broad,
            ))]
    first_roots = cli._operation_lock_roots([source], stores, [broad])
    second_roots = cli._operation_lock_roots([source], [], [narrow])
    first = begin_active_run(first_db, plan_id=1, what="broad", lock_roots=first_roots)
    try:
        with pytest.raises(ActiveRunError):
            begin_active_run(second_db, plan_id=2, what="narrow", lock_roots=second_roots)
    finally:
        finish_active_run(first_db, plan_id=1, token=first.token)
    second = begin_active_run(second_db, plan_id=2, what="narrow", lock_roots=second_roots)
    finish_active_run(second_db, plan_id=2, token=second.token)


def test_lock_scope_does_not_precreate_future_date_directories(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    destination = root / "2026" / "2026-05" / "IMG_0001.CR3"
    assert cli._operation_lock_roots([destination], [], [root]) == (root,)
    assert not destination.parent.exists()


def test_fetch_preview_reports_distinct_equal_size_destination_as_collision(tmp_path: Path) -> None:
    from rawdog.models import NamingConvention

    source = tmp_path / "source"
    destination = tmp_path / "archive"
    source.mkdir()
    destination.mkdir()
    (source / "IMG_0001.CR3").write_bytes(b"original")
    (destination / "IMG_0001.CR3").write_bytes(b"distinct")
    plan = cli._build_fetch_plan(source, destination, destination, NamingConvention.DDD)
    assert len(plan.rows) == 1
    assert plan.rows[0].status == "collision"


def test_interrupted_reviewed_inode_move_is_recovered_truthfully(tmp_path: Path) -> None:
    import json

    from rawdog.copier import append_only_move

    database = tmp_path / "state" / "rawdog.sqlite"
    source = tmp_path / "source" / "IMG_0001.CR3"
    destination = tmp_path / "archive" / source.name
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_bytes(b"reviewed")
    initialize(database)
    with session(database) as connection:
        plan = create_execution_plan(connection, ExecutionPlanCreate(
            plan_kind="den", what="move", subject="synthetic interrupted commit",
            expected_result="recover the reviewed object", source_root=source.parent,
            destination_root=destination.parent,
        ))
        add_execution_plan_rows(connection, plan.plan_id, [ExecutionPlanRowCreate(
            source_path=source, destination_path=destination, size_bytes=8,
            transfer_action=DenTransferAction.MOVE, status="plan_copy",
        )])
        row = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert append_only_move(source, destination, destination.parent,
                            expected_source_version=json.loads(row.source_version)) == "moved"
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    assert cli._execute_persisted_plan(config, plan.plan_id).status == ExecutionPlanStatus.DONE
    with session(database) as connection:
        row = list_execution_plan_rows(connection, plan.plan_id)[0]
    assert row.status == "moved"
    assert row.audit_status == "destination_verified"
    assert not source.exists()
    assert destination.read_bytes() == b"reviewed"


def test_execution_timestamps_new_date_folders_after_lock_acquisition(tmp_path: Path) -> None:
    from rawdog.models import NamingConvention

    database = tmp_path / "state" / "rawdog.sqlite"
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    folder = archive / "2025" / "202501"
    source.mkdir()
    archive.mkdir()
    (source / "IMG_0001.CR3").write_bytes(b"reviewed")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    plan = cli._build_fetch_plan(source, archive, folder, NamingConvention.DDD)
    persisted = cli._persist_fetch_execution_plan(config, plan)
    assert cli._execute_persisted_plan(config, persisted.plan_id).status == ExecutionPlanStatus.DONE
    expected = int(datetime(2025, 1, 1, 0, 0, 1).timestamp())
    assert int((archive / "2025").stat().st_mtime) == expected
    assert int(folder.stat().st_mtime) == expected
    assert (source / "IMG_0001.CR3").read_bytes() == b"reviewed"


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


def test_time_shift_rows_are_grouped_by_plan_and_track_status(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    source = tmp_path / "source" / "LS7A0001.CR3"
    destination = tmp_path / "yard" / "20260529-130000-00__LS7A0001.CR3"
    initialize(database)

    with session(database) as connection:
        plan = create_execution_plan(
            connection,
            ExecutionPlanCreate(
                plan_kind="yard-reflow",
                what="reflow yard files into normalized date/filename layout",
                subject=f"{tmp_path / 'source'} -> {tmp_path / 'yard'}",
                expected_result="one shifted file should be renamed",
            ),
        )
        add_execution_plan_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanRowCreate(
                    source_path=source,
                    destination_path=destination,
                    size_bytes=3,
                    transfer_action=DenTransferAction.MOVE,
                    status="plan_copy",
                )
            ],
        )
        execution_row = list_execution_plan_rows(connection, plan.plan_id)[0]
        add_execution_plan_time_shift_rows(
            connection,
            plan.plan_id,
            [
                ExecutionPlanTimeShiftRowCreate(
                    execution_row_id=execution_row.row_id,
                    source_path=source,
                    destination_path=destination,
                    original_capture_at=datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
                    shifted_capture_at=datetime(2026, 5, 29, 13, 0, tzinfo=UTC),
                    time_shift_seconds=3600,
                    basis="metadata_or_file_mtime",
                    status="plan_copy",
                )
            ],
        )
        update_execution_plan_time_shift_row(
            connection,
            execution_row.row_id,
            status="moved",
            audit_status="destination_verified",
        )

    with session(database) as connection:
        rows = list_execution_plan_time_shift_rows(connection, plan.plan_id)

    assert len(rows) == 1
    assert rows[0].plan_id == plan.plan_id
    assert rows[0].execution_row_id == execution_row.row_id
    assert rows[0].time_shift_seconds == 3600
    assert rows[0].status == "moved"
    assert rows[0].audit_status == "destination_verified"


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


def test_copy_plan_refuses_execution_when_destination_space_is_short(tmp_path: Path, monkeypatch) -> None:
    now = datetime.now(UTC)
    plan = cli.ExecutionPlan(
        plan_id=44,
        plan_kind="den",
        status=ExecutionPlanStatus.PLANNED,
        what="copy RAW files",
        subject=f"{tmp_path / 'source'} -> {tmp_path / 'den'}",
        expected_result="one file should be copied",
        execution_summary="Not started.",
        post_audit_summary="Not audited.",
        source_root=tmp_path / "source",
        destination_root=tmp_path / "den",
        created_at=now,
        updated_at=now,
    )
    rows = [
        cli.ExecutionPlanRow(
            row_id=1,
            plan_id=44,
            source_path=tmp_path / "source" / "one.CR3",
            destination_path=tmp_path / "den" / "one.CR3",
            size_bytes=100_000_000,
            transfer_action=DenTransferAction.COPY,
            status="plan_copy",
        )
    ]
    usage = type("Usage", (), {"free": 5_000_000})()
    monkeypatch.setattr(cli.shutil, "disk_usage", lambda path: usage)

    with pytest.raises(cli.typer.BadParameter, match="not have enough free space"):
        cli._ensure_copy_plan_has_free_space(plan, rows)


def test_database_write_space_guard_refuses_low_free_space(tmp_path: Path, monkeypatch) -> None:
    config = build_config(OrganizationMode.PROJECT, database_path=tmp_path / "rawdog.sqlite")
    usage = type("Usage", (), {"free": 5_000_000})()
    monkeypatch.setattr(cli.shutil, "disk_usage", lambda path: usage)

    with pytest.raises(cli.typer.BadParameter, match="database volume is too low"):
        cli._ensure_database_write_space(config)


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
