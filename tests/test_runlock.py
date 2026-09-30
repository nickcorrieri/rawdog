# Author: Nicholas Corrieri

import json
import os
import threading
from pathlib import Path

import pytest

from rawdog import runlock
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

    run = begin_active_run(
        database,
        plan_id=42,
        what="copy RAW/camera video files",
        plan_kind="fetch",
        subject=f"{tmp_path / 'card'} -> {tmp_path / 'RAW_YARD'}",
        source_root=tmp_path / "card",
        destination_root=tmp_path / "RAW_YARD",
        store_kind="yard",
        write_lock=True,
    )

    assert run.plan_id == 42
    assert run.pid == os.getpid()
    assert read_active_run(database) == run
    assert run.plan_kind == "fetch"
    assert run.source_root == tmp_path / "card"
    assert run.destination_root == tmp_path / "RAW_YARD"
    assert run.store_kind == "yard"
    assert active_run_is_alive(run)
    with pytest.raises(ActiveRunError, match="This command is blocked"):
        begin_active_run(database, plan_id=43, what="another plan")

    finish_active_run(database, plan_id=42, token=run.token)

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


def test_store_lock_blocks_separate_app_databases_and_rolls_back(tmp_path: Path) -> None:
    first_database = tmp_path / "app1" / "rawdog.sqlite"
    second_database = tmp_path / "app2" / "rawdog.sqlite"
    store = tmp_path / "archive"
    first = begin_active_run(first_database, plan_id=1, what="first", destination_root=store)
    with pytest.raises(ActiveRunError):
        begin_active_run(second_database, plan_id=2, what="second", destination_root=store)
    assert read_active_run(second_database) is None
    assert read_active_run(first_database).token == first.token
    finish_active_run(first_database, plan_id=1, token=first.token)
    second = begin_active_run(second_database, plan_id=2, what="second", destination_root=store)
    finish_active_run(second_database, plan_id=2, token=second.token)


def test_old_owner_token_cannot_release_reacquired_lock(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    first = begin_active_run(database, plan_id=1, what="first")
    finish_active_run(database, plan_id=1, token=first.token)
    second = begin_active_run(database, plan_id=1, what="second")
    finish_active_run(database, plan_id=1, token=first.token)
    assert read_active_run(database).token == second.token
    finish_active_run(database, plan_id=1, token=second.token)


def test_symlink_lock_parent_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ActiveRunError, match="symlink"):
        begin_active_run(alias / "rawdog.sqlite", plan_id=1, what="invalid")
    assert not (outside / "active-run.json").exists()


def test_release_read_and_unlink_are_serialized_with_acquisition(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "rawdog.sqlite"
    first = begin_active_run(database, plan_id=1, what="first")
    entered = threading.Event()
    release = threading.Event()
    original_read = runlock._read_marker

    def paused_read(path):
        value = original_read(path)
        if threading.current_thread().name == "releasing":
            entered.set()
            assert release.wait(5)
        return value

    monkeypatch.setattr(runlock, "_read_marker", paused_read)
    owner = threading.Thread(
        target=runlock._remove_owned_marker,
        args=(active_run_path(database), first.token),
        name="releasing",
    )
    owner.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ActiveRunError):
            begin_active_run(database, plan_id=2, what="competing")
    finally:
        release.set()
        owner.join(5)
    assert not owner.is_alive()
    second = begin_active_run(database, plan_id=2, what="new owner")
    assert not runlock._remove_owned_marker(active_run_path(database), first.token)
    assert read_active_run(database).token == second.token
    finish_active_run(database, plan_id=2, token=second.token)


def test_interrupted_store_publication_leaves_no_torn_marker(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "app" / "rawdog.sqlite"
    store = tmp_path / "archive"
    original_link = runlock.os.link

    def interrupted_link(source, destination, **kwargs):
        assert json.loads(source.read_text())["token"]
        assert not destination.exists()
        if destination.parent == store / ".rawdog":
            raise OSError("interrupted before store marker publication")
        return original_link(source, destination, **kwargs)

    monkeypatch.setattr(runlock.os, "link", interrupted_link)
    with pytest.raises(OSError, match="interrupted"):
        begin_active_run(database, plan_id=1, what="first", destination_root=store)
    assert read_active_run(database) is None
    assert not (store / ".rawdog" / "active-run.json").exists()
    monkeypatch.setattr(runlock.os, "link", original_link)
    second = begin_active_run(database, plan_id=2, what="retry", destination_root=store)
    finish_active_run(database, plan_id=2, token=second.token)


def test_failed_store_release_retains_app_recovery_evidence(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "app" / "rawdog.sqlite"
    store = tmp_path / "archive"
    first = begin_active_run(database, plan_id=1, what="first", destination_root=store)
    original_remove = runlock._remove_owned_marker

    def refuse_store(path, token):
        return False if path.parent == store / ".rawdog" else original_remove(path, token)

    monkeypatch.setattr(runlock, "_remove_owned_marker", refuse_store)
    with pytest.raises(ActiveRunError, match="recovery evidence retained"):
        clear_active_run(database)
    assert read_active_run(database).token == first.token
    monkeypatch.setattr(runlock, "_remove_owned_marker", original_remove)
    finish_active_run(database, plan_id=1, token=first.token)


def test_published_store_marker_survives_temporary_cleanup_error(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "app" / "rawdog.sqlite"
    store = tmp_path / "archive"
    original_unlink = Path.unlink

    def refuse_temporary(path, *args, **kwargs):
        if path.parent == store / ".rawdog" and path.name.endswith(".tmp"):
            raise PermissionError("synthetic temporary cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_temporary)
    run = begin_active_run(database, plan_id=1, what="first", destination_root=store)
    assert read_active_run(database).token == run.token
    assert json.loads((store / ".rawdog" / "active-run.json").read_text())["token"] == run.token
    finish_active_run(database, plan_id=1, token=run.token)
    assert read_active_run(database) is None
    assert not (store / ".rawdog" / "active-run.json").exists()


def test_failed_partial_acquisition_rollback_retains_app_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "app" / "rawdog.sqlite"
    other_database = tmp_path / "other-app" / "rawdog.sqlite"
    first_store = tmp_path / "a-store"
    conflicting_store = tmp_path / "b-store"
    other = begin_active_run(other_database, plan_id=2, what="other", destination_root=conflicting_store)
    original_remove = runlock._remove_owned_marker

    def refuse_first_store(path, token):
        return False if path.parent == first_store / ".rawdog" else original_remove(path, token)

    monkeypatch.setattr(runlock, "_remove_owned_marker", refuse_first_store)
    with pytest.raises(ActiveRunError):
        begin_active_run(database, plan_id=1, what="partial", lock_roots=(first_store, conflicting_store))
    retained = read_active_run(database)
    assert retained is not None
    assert json.loads((first_store / ".rawdog" / "active-run.json").read_text())["token"] == retained.token
    assert read_active_run(other_database).token == other.token
    monkeypatch.setattr(runlock, "_remove_owned_marker", original_remove)
    finish_active_run(other_database, plan_id=2, token=other.token)
    assert clear_active_run(database)
    assert read_active_run(database) is None
    assert not (first_store / ".rawdog" / "active-run.json").exists()


@pytest.mark.parametrize("entry", ["path", "read", "begin"])
@pytest.mark.parametrize("ancestor", [False, True], ids=["leaf", "ancestor"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_active_run_entry_rejects_alias_before_resolving_or_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str, ancestor: bool, broken: bool,
) -> None:
    database = tmp_path / "state" / "rawdog.sqlite"
    database.parent.mkdir()
    database.write_bytes(b"synthetic database placeholder")
    alias = database.parent if ancestor else database
    retained = tmp_path / "retained"
    alias.rename(retained)
    alias.symlink_to(tmp_path / "missing-target" if broken else retained, target_is_directory=ancestor)
    real_stat, real_lstat = os.stat, os.lstat
    real_resolve, real_open = Path.resolve, Path.open

    def check(path, *, follow):
        if isinstance(path, int):
            return
        selected = Path(os.fsdecode(path))
        if alias in selected.parents or (follow and selected == alias):
            raise AssertionError("runlock followed an alias before rejection")

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
        with pytest.raises(ActiveRunError, match="symlink"):
            if entry == "path":
                active_run_path(database)
            elif entry == "read":
                read_active_run(database)
            else:
                begin_active_run(database, plan_id=1, what="invalid alias")

    preserved_database = retained / database.name if ancestor else retained
    assert preserved_database.read_bytes() == b"synthetic database placeholder"
    assert not (retained / "active-run.json" if ancestor else database.parent / "active-run.json").exists()


@pytest.mark.parametrize("release", ["finish", "clear"])
@pytest.mark.parametrize("broken", [False, True], ids=["live", "dangling"])
def test_lock_release_refuses_replaced_store_root_and_keeps_recovery(tmp_path: Path, monkeypatch, release, broken):
    database = tmp_path / "state" / "rawdog.sqlite"
    root = tmp_path / "store"
    owner = begin_active_run(database, plan_id=1, what="owned", lock_roots=(root,))
    app_before = active_run_path(database).read_bytes()
    store_before = (root / ".rawdog" / "active-run.json").read_bytes()
    retained = tmp_path / "retained-store"
    root.rename(retained)
    root.symlink_to(tmp_path / "missing-store" if broken else retained, target_is_directory=True)
    real_stat = os.stat

    def refuse_store_metadata(path, *args, **kwargs):
        if not isinstance(path, int):
            selected = Path(os.fsdecode(path))
            if root in selected.parents or (selected == root and kwargs.get("follow_symlinks", True)):
                raise AssertionError("release inspected a replaced store root before refusal")
        return real_stat(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "stat", refuse_store_metadata)
        with pytest.raises(ActiveRunError, match="symlink"):
            if release == "finish":
                finish_active_run(database, plan_id=1, token=owner.token)
            else:
                clear_active_run(database)
    assert active_run_path(database).read_bytes() == app_before
    assert (retained / ".rawdog" / "active-run.json").read_bytes() == store_before
