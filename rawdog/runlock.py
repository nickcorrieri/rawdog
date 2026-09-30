# Author: Nicholas Corrieri

from __future__ import annotations

import json
import os
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rawdog.safety import SafetyError, absolute_lexical_path, ensure_no_symlink_components

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
    token: str = ""
    lock_roots: tuple[Path, ...] = ()


def active_run_path(database_path: Path) -> Path:
    _reject_symlinks(database_path)
    return absolute_lexical_path(database_path).parent / ACTIVE_RUN_FILE


def read_active_run(database_path: Path) -> ActiveRun | None:
    path = active_run_path(database_path)
    return _read_marker(path)


def _read_marker(path: Path) -> ActiveRun | None:
    _reject_symlinks(path)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
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
        token=str(data.get("token") or ""),
        lock_roots=tuple(Path(root) for root in data.get("lock_roots", [])),
    )


def active_run_is_alive(run: ActiveRun) -> bool:
    try:
        os.kill(run.pid, 0)
    except PermissionError:
        return True
    except ProcessLookupError:
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
        details.append(
            "If no RAWDOG copy/move is running, clear it with: rawdog plans active-clear --force"
        )
    else:
        details.append(
            "This command is blocked until that active run finishes or the marker is cleared."
        )
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
    lock_roots: tuple[Path, ...] = (),
) -> ActiveRun:
    _reject_symlinks(database_path.expanduser())
    roots = lock_roots or ((destination_root,) if destination_root and write_lock else ())
    for root in roots:
        _reject_symlinks(root.expanduser())
    roots = tuple(sorted({absolute_lexical_path(root) for root in roots}, key=str))
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
        token=uuid.uuid4().hex,
        lock_roots=roots,
    )
    path = active_run_path(database_path)
    marker_paths = [path, *(_store_lock_path(root) for root in roots)]
    data = json.dumps(
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
            "token": run.token,
            "lock_roots": [str(root) for root in roots],
        },
        indent=2,
    ).encode()
    acquired: list[Path] = []
    try:
        for marker in marker_paths:
            with _marker_guard(marker):
                if marker.exists() or marker.is_symlink():
                    try:
                        existing = _read_marker(marker)
                    except (OSError, ValueError, KeyError):
                        existing = None
                    if existing:
                        raise ActiveRunError(
                            _active_run_error_message(
                                existing,
                                stale=not active_run_is_alive(existing),
                            )
                        )
                    raise ActiveRunError(f"Active-run marker is incomplete or unreadable: {marker}")
                _publish_marker(marker, data, run.token)
                acquired.append(marker)
    except BaseException:
        released = True
        for marker in reversed(acquired[1:]):
            if not _remove_owned_marker(marker, run.token):
                released = False
        # Recovery needs the app marker to identify any store lock left behind.
        if acquired and released:
            _remove_owned_marker(path, run.token)
        raise
    return run


def _reject_symlinks(path: Path) -> None:
    try:
        ensure_no_symlink_components(path)
    except SafetyError as exc:
        raise ActiveRunError(f"Active-run path is not authorized: {exc}") from exc


def _store_lock_path(root: Path) -> Path:
    return root / ".rawdog" / ACTIVE_RUN_FILE


@contextmanager
def _marker_guard(path: Path):
    """Serialize publication and removal on a stable guard that is never unlinked."""
    _reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlinks(path)
    guard = path.with_name(path.name + ".guard")
    fd = os.open(guard, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ActiveRunError(f"Active-run guard is not a regular file: {guard}")
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ActiveRunError(f"Active-run marker is being changed: {path}") from exc
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ActiveRunError(f"Active-run marker is being changed: {path}") from exc
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _publish_marker(path: Path, data: bytes, token: str) -> None:
    temporary = path.with_name(f".{path.name}.{token}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Only complete durable metadata is published; no existing lock is replaced.
        os.link(temporary, path, follow_symlinks=False)
    finally:
        try:
            current = temporary.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                temporary.unlink()
        except OSError:
            # A cleanup error must not turn a published owned lock into an
            # untracked acquisition. Preserve its app recovery evidence.
            pass


def _remove_owned_marker(path: Path, token: str) -> bool:
    try:
        with _marker_guard(path):
            run = _read_marker(path)
            if run is None or run.token != token:
                return False
            path.unlink()
            return True
    except (OSError, ValueError, KeyError, ActiveRunError):
        return False


def finish_active_run(database_path: Path, *, plan_id: int, token: str) -> None:
    try:
        run = read_active_run(database_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return
    if run and run.token == token and run.plan_id == plan_id and run.pid == os.getpid():
        released = True
        for root in run.lock_roots:
            marker = _store_lock_path(root)
            _reject_symlinks(marker)
            if marker.exists() and not _remove_owned_marker(marker, token):
                released = False
        if released:
            _remove_owned_marker(active_run_path(database_path), token)


def clear_active_run(database_path: Path) -> bool:
    path = active_run_path(database_path)
    with _marker_guard(path):
        try:
            run = _read_marker(path)
        except (ValueError, KeyError):
            # Historical unreadable metadata cannot identify any store locks.
            path.unlink(missing_ok=True)
            return True
    if run is None:
        return False
    for root in run.lock_roots:
        if run.token:
            marker = _store_lock_path(root)
            _reject_symlinks(marker)
            if marker.exists() and not _remove_owned_marker(marker, run.token):
                raise ActiveRunError(
                    f"Store lock not released; app recovery evidence retained: {marker}"
                )
    if run.token:
        return _remove_owned_marker(path, run.token)
    with _marker_guard(path):
        current = _read_marker(path)
        if current != run:
            return False
        path.unlink()
        return True
