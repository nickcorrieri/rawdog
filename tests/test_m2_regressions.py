"""Noncleanup M2 regression definitions; execution remains qualification-blocked.

No product imports or fixture writes occur until repository-local admission.
That admission is not runtime or OS isolation proof. See the packet mapping doc.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from m2_cases import CHANGED, FOREIGN, ORIGINAL, claim_repository_root, new_world, require_local_path


@pytest.fixture(scope="session")
def packet_root(request):
    # Do not request tmp_path/getbasetemp: pytest may create or clear an outside path.
    checkout = Path(__file__).absolute().parents[1]
    return claim_repository_root(checkout, request.config.getoption("basetemp"))


@pytest.fixture
def case(packet_root, monkeypatch):
    world = new_world(packet_root)
    import rawdog
    from rawdog import cli, copier, den, execution, models, runlock, stores
    from rawdog.config import build_config
    from rawdog.db import initialize, session

    checkout = Path(__file__).absolute().parents[1]
    imported = Path(rawdog.__file__).absolute()
    if imported != checkout / "rawdog" / "__init__.py":
        raise RuntimeError("Regression packet imported another checkout")
    require_local_path(imported)
    initialize(world.database)
    config = build_config(models.OrganizationMode.PROJECT, database_path=world.database)
    config_path = world.seed(
        "state/config.json", json.dumps(models.model_to_json_data(config)).encode("utf-8"),
    )
    monkeypatch.setattr(cli, "default_config_path", lambda: config_path)
    monkeypatch.setattr(cli, "default_database_path", lambda: world.database)
    return SimpleNamespace(world=world, cli=cli, copier=copier, den=den, execution=execution,
                           models=models, runlock=runlock, stores=stores, config=config,
                           session=session, monkeypatch=monkeypatch)


def persist(case, pairs=None, *, status="plan_copy", action="copy"):
    world = case.world
    pairs = pairs or [(world.source, world.keeper)]
    plan = case.den.DenPlan(
        source_root=world.source.parent, destination_root=world.keeper.parent,
        destination_folder=world.keeper.parent,
        transfer_action=case.models.DenTransferAction(action),
        rows=[case.den.DenPlanRow(source, keeper, 8, status) for source, keeper in pairs],
    )
    return case.cli._persist_den_execution_plan(case.config, plan)


def register(case, root, *, kind="den", name="primary"):
    with case.session(case.world.database) as connection:
        return case.stores.create_or_update_store(
            connection, case.models.StoreCreate(name=name, root_path=root,
                                                store_kind=case.models.StoreKind(kind)),
        )


def safety_refusal(case, action):
    """A specifically reported safety refusal is allowed; arbitrary crashes fail."""
    try:
        return action()
    except (case.cli.SafetyError, case.cli.typer.BadParameter, FileExistsError):
        return None


def test_copy_does_not_overwrite_concurrent_destination(case):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    arrivals = []

    def concurrent_arrival(_amount):
        if not arrivals:
            w.seed("archive/IMG_0001.CR3", FOREIGN)
            arrivals.append(True)

    safety_refusal(case, lambda: case.copier.append_only_copy(
        w.source, w.keeper, w.keeper.parent, progress_callback=concurrent_arrival,
    ))
    assert arrivals == [True], "Race injection must execute before publication"
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == FOREIGN


def test_move_does_not_overwrite_concurrent_destination(case):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    actual = case.copier._create_destination_parent
    arrivals = []

    def concurrent_arrival(destination, root):
        created = actual(destination, root)
        w.seed("archive/IMG_0001.CR3", FOREIGN)
        arrivals.append(True)
        return created

    case.monkeypatch.setattr(case.copier, "_create_destination_parent", concurrent_arrival)
    safety_refusal(case, lambda: case.copier.append_only_move(w.source, w.keeper, w.keeper.parent))
    assert arrivals == [True]
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == FOREIGN


@pytest.mark.parametrize("action", ["copy", "move"])
def test_transfer_rechecks_destination_parent_components(case, action):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    destination = w.keeper.parent / "bucket" / w.source.name
    actual = case.copier._create_destination_parent
    arrivals = []

    def replace_parent(path, root):
        created = actual(path, root)
        path.parent.rename(root / "retained-bucket")
        path.parent.symlink_to(w.root / "canary", target_is_directory=True)
        arrivals.append(True)
        return created

    case.monkeypatch.setattr(case.copier, "_create_destination_parent", replace_parent)
    primitive = case.copier.append_only_copy if action == "copy" else case.copier.append_only_move
    safety_refusal(case, lambda: primitive(w.source, destination, w.keeper.parent))
    assert arrivals == [True]
    assert w.source.read_bytes() == ORIGINAL
    assert not (w.root / "canary" / w.source.name).exists()


def test_copy_does_not_consume_unowned_matching_partial(case):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    partial = w.seed("archive/IMG_0001.CR3.partial")
    assert case.copier.append_only_copy(w.source, w.keeper, w.keeper.parent) == "skipped_existing_partial"
    assert partial.read_bytes() == ORIGINAL
    assert w.source.read_bytes() == ORIGINAL
    if w.keeper.exists():
        assert w.keeper.read_bytes() == ORIGINAL


def test_copy_failure_preserves_replaced_partial_owned_by_another_writer(case):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    foreign_partials = []

    def interrupted_copy(_source, partial, **kwargs):
        replacement = partial.with_name(partial.name + ".foreign")
        with replacement.open("xb") as handle:
            handle.write(FOREIGN)
        os.replace(replacement, partial)
        foreign_partials.append(partial)
        raise OSError("synthetic interruption after another writer replaced partial")

    case.monkeypatch.setattr(case.copier, "_copy2_with_progress", interrupted_copy)
    with pytest.raises(OSError, match="synthetic interruption"):
        case.copier.append_only_copy(w.source, w.keeper, w.keeper.parent)
    assert len(foreign_partials) == 1
    assert foreign_partials[0].read_bytes() == FOREIGN
    assert w.source.read_bytes() == ORIGINAL
    assert not w.keeper.exists()


@pytest.mark.parametrize("action", ["copy", "move"])
def test_equal_size_distinct_existing_destination_is_collision(case, action):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    w.seed("archive/IMG_0001.CR3", CHANGED)
    primitive = case.copier.append_only_copy if action == "copy" else case.copier.append_only_move
    assert primitive(w.source, w.keeper, w.keeper.parent) == "skipped_collision"
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == CHANGED


def test_planner_does_not_claim_distinct_equal_size_file_already_present(case, monkeypatch):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    w.seed("archive/IMG_0001.CR3", CHANGED)
    # Date parsing is outside this exact-content case; preserve layout needs no metadata.
    monkeypatch.setattr(case.den, "capture_times", lambda paths: {
        path: datetime(2024, 5, 20, tzinfo=UTC) for path in paths
    })
    planned = case.den.build_den_plan(w.source.parent, w.keeper.parent)
    assert len(planned.rows) == 1
    assert planned.rows[0].status == "collision"
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == CHANGED


def test_nonowner_finish_cannot_release_active_writer(case):
    w = case.world
    first = case.runlock.begin_active_run(w.database, plan_id=1, what="synthetic writer",
                                         destination_root=w.keeper.parent)
    case.runlock.finish_active_run(w.database, plan_id=999, token="not-the-owner")
    assert case.runlock.read_active_run(w.database) == first
    with pytest.raises(case.runlock.ActiveRunError):
        case.runlock.begin_active_run(w.database, plan_id=2, what="competitor",
                                     destination_root=w.keeper.parent)
    case.runlock.finish_active_run(w.database, plan_id=1, token=first.token)


def test_same_plan_and_pid_without_owner_token_cannot_release_writer(case):
    w = case.world
    first = case.runlock.begin_active_run(w.database, plan_id=1, what="synthetic writer",
                                         destination_root=w.keeper.parent)
    # Matching plan and PID do not grant token ownership.
    case.runlock.finish_active_run(w.database, plan_id=1, token="not-the-owner")
    assert case.runlock.read_active_run(w.database) == first
    case.runlock.finish_active_run(w.database, plan_id=1, token=first.token)


@pytest.mark.parametrize("action", ["copy", "move"])
@pytest.mark.parametrize("mutation", ["same-size", "same-size-same-mtime", "larger", "removed"])
def test_reviewed_source_changes_are_held_before_transfer(case, action, mutation):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    plan = persist(case, action=action)
    reviewed_stat = w.source.stat()
    if mutation == "removed":
        w.source.unlink()
    else:
        w.source.write_bytes(CHANGED if mutation.startswith("same-size") else b"changed-longer")
        if mutation == "same-size-same-mtime":
            os.utime(w.source, ns=(reviewed_stat.st_atime_ns, reviewed_stat.st_mtime_ns))
    finished = case.cli._execute_persisted_plan(case.config, plan.plan_id)
    assert finished.status.value in {"needs_review", "failed"}
    assert not w.keeper.exists()
    if mutation != "removed":
        assert w.source.read_bytes() == (CHANGED if mutation.startswith("same-size") else b"changed-longer")
    with case.session(w.database) as connection:
        rows = case.execution.list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].audit_status != "destination_verified"


@pytest.mark.parametrize("status", ["skip_existing_same_name_size", "skipped_existing_same_name_size"])
@pytest.mark.parametrize("mutation", ["removed", "same-size"])
def test_skipped_destination_requires_fresh_evidence(case, status, mutation):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    w.seed("archive/IMG_0001.CR3")
    plan = persist(case, status=status)
    if mutation == "removed":
        w.keeper.unlink()
    else:
        w.keeper.write_bytes(CHANGED)
    finished = case.cli._execute_persisted_plan(case.config, plan.plan_id)
    assert finished.status.value in {"needs_review", "failed"}
    assert w.source.read_bytes() == ORIGINAL
    if mutation == "same-size":
        assert w.keeper.read_bytes() == CHANGED
    else:
        assert not w.keeper.exists(), "A reviewed skip cannot silently become a copy"
    with case.session(w.database) as connection:
        rows = case.execution.list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].audit_status not in {"destination_verified", "not_applicable"}


@pytest.mark.parametrize("bad_payload", [b"size-mismatch", CHANGED], ids=["size", "equal-size-bytes"])
def test_failed_required_post_audit_blocks_done(case, bad_payload):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    plan = persist(case)

    def faulty_transfer(source, destination, root, **kwargs):
        w.seed("archive/IMG_0001.CR3", bad_payload)
        return "copied"

    # Fault injection isolates audit aggregation from pre-transfer source guards.
    case.monkeypatch.setattr(case.cli, "append_only_copy", faulty_transfer)
    finished = case.cli._execute_persisted_plan(case.config, plan.plan_id)
    assert finished.status.value in {"needs_review", "failed"}
    assert "Review items: 0" not in finished.post_audit_summary
    with case.session(w.database) as connection:
        rows = case.execution.list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].audit_status != "destination_verified"
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == bad_payload


def test_resumed_completed_row_does_not_trust_equal_size_destination(case):
    w = case.world
    w.seed("working/IMG_0001.CR3")
    plan = persist(case)
    assert case.cli._execute_persisted_plan(case.config, plan.plan_id).status.value == "done"
    w.keeper.write_bytes(CHANGED)
    finished = case.cli._execute_persisted_plan(case.config, plan.plan_id)
    assert finished.status.value in {"needs_review", "failed"}
    assert w.source.read_bytes() == ORIGINAL
    assert w.keeper.read_bytes() == CHANGED


@pytest.mark.parametrize("replacement", [CHANGED, b"different-size"], ids=["same-size", "new-size"])
def test_quick_catalog_invalidates_previous_full_hash(case, replacement):
    w = case.world
    w.seed("archive/IMG_0001.CR3")
    store = register(case, w.keeper.parent)
    date = datetime(2024, 5, 20, tzinfo=UTC)
    entry = case.stores.StoreMediaCatalogEntry(w.keeper, 8, date, "filesystem",
                                               hashlib.sha256(ORIGINAL).hexdigest())
    case.stores.upsert_store_media_catalog(store, [entry], full=True)
    w.keeper.write_bytes(replacement)
    quick = case.stores.StoreMediaCatalogEntry(w.keeper, len(replacement), date, "filesystem")
    case.stores.upsert_store_media_catalog(store, [quick], full=False)
    with case.session(case.stores.store_db_path(store.root_path)) as connection:
        row = connection.execute("SELECT sha256, full_cataloged_at FROM media_catalog").fetchone()
    assert row["sha256"] is None
    assert row["full_cataloged_at"] is None
    from rawdog.inventory import scan_raw_files
    status = case.stores.store_media_catalog_status(store, scan_raw_files(store.root_path))
    assert status.full_cataloged_files == 0
    assert w.keeper.read_bytes() == replacement


def test_copied_store_identity_does_not_replace_live_original(case):
    w = case.world
    w.seed("archive/IMG_0001.CR3")
    original = register(case, w.keeper.parent)
    clone = w.root / "backup" / "clone"
    shutil.copytree(original.root_path, clone)
    safety_refusal(case, lambda: register(case, clone, name="backup"))
    with case.session(w.database) as connection:
        registrations = case.stores.list_stores(connection)
    kept = [store for store in registrations if store.store_id == original.store_id]
    assert len(kept) == 1
    assert kept[0].root_path == original.root_path
    assert w.keeper.read_bytes() == ORIGINAL
    assert (clone / w.keeper.name).read_bytes() == ORIGINAL
    # Ambiguous clone may be rejected or separately registered; never relink live original.
    clone_registrations = [store for store in registrations if store.root_path == clone]
    assert all(store.store_id != original.store_id for store in clone_registrations)
