"""Repository-local synthetic M2 fixtures; no product imports or subprocesses.

Admission only prevents accidental path/reuse mistakes. It does not qualify
Python startup, native code, OS isolation, or this packet for execution.
"""

from __future__ import annotations

import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

CANONICAL_CHECKOUT = Path("/Users/nick/Projects/rawdog")
CASE_PARENT = CANONICAL_CHECKOUT / "scripts" / ".repo-test-harness-state"
ORIGINAL = b"same0001"
CHANGED = b"diff0002"
FOREIGN = b"keeper99"


def require_local_path(path: Path, *, allow_missing: bool = False) -> Path:
    """Reject outside spellings before I/O; inspect only in-checkout components."""
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(CANONICAL_CHECKOUT):
        raise RuntimeError("M2 paths must be absolute descendants of the canonical checkout")
    current = CANONICAL_CHECKOUT
    components = [current]
    for part in path.relative_to(CANONICAL_CHECKOUT).parts:
        current = current / part
        components.append(current)
    for current in components:
        try:
            observed = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                return path
            raise
        if stat.S_ISLNK(observed.st_mode):
            raise RuntimeError(f"M2 fixture path contains a symlink: {current}")
        if current != path and not stat.S_ISDIR(observed.st_mode):
            raise RuntimeError(f"M2 fixture parent is not a directory: {current}")
    return path


def _require_directory(path: Path) -> None:
    require_local_path(path)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise RuntimeError(f"M2 fixture parent is not a directory: {path}")


def claim_repository_root(checkout: Path, basetemp: str | Path | None) -> Path:
    """Claim an unused root without asking pytest to create/clear its basetemp.

    Only a separately qualified runner may invoke this. A --basetemp argument
    supplies a path, never an isolation receipt or authorization to run tests.
    The parent must already have been admitted by that runner; no parent tree
    is created here and no previous run is reset or removed.
    """
    if checkout != CANONICAL_CHECKOUT or Path(__file__).absolute().parent != checkout / "tests":
        raise RuntimeError("M2 packet must come from the canonical checkout")
    if basetemp is None:
        raise RuntimeError("M2 requires an explicit fresh repository-local --basetemp")
    root = Path(basetemp)
    if root.parent != CASE_PARENT or not root.name.startswith("m2-") or root.name == "m2-":
        raise RuntimeError("M2 basetemp must be a new m2-NAME child of the repository harness state directory")
    _require_directory(CASE_PARENT)
    require_local_path(root, allow_missing=True)
    try:
        root.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RuntimeError("M2 refuses to reuse or clear an existing synthetic root") from exc
    return root


@dataclass(frozen=True)
class World:
    root: Path

    @property
    def source(self) -> Path:
        return self.root / "working" / "IMG_0001.CR3"

    @property
    def keeper(self) -> Path:
        return self.root / "archive" / "IMG_0001.CR3"

    @property
    def database(self) -> Path:
        return self.root / "state" / "app.sqlite"

    def seed(self, relative: str, payload: bytes = ORIGINAL) -> Path:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.name:
            raise ValueError("Synthetic seeds must be relative paths without parent traversal")
        current = self.root
        _require_directory(current)
        for part in relative_path.parent.parts:
            current = current / part
            require_local_path(current, allow_missing=True)
            try:
                current.mkdir()
            except FileExistsError:
                pass
            _require_directory(current)
        path = self.root / relative_path
        require_local_path(path, allow_missing=True)
        with path.open("xb") as handle:
            handle.write(payload)
        return path


def new_world(parent: Path) -> World:
    _require_directory(parent)
    root = parent / f"case-{uuid.uuid4().hex}"
    root.mkdir(mode=0o700)
    world = World(root)
    for name in ("working", "archive", "backup", "state", "canary"):
        (root / name).mkdir()
    world.seed(".rawdog-m2-synthetic", b"Fresh synthetic bytes only. Not isolation proof.\n")
    return world
