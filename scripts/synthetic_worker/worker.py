"""Authored-only synthetic file capability; this module is NOT a sandbox.

The command-line entry always exits BLOCKED. Importing this module or running
its controls requires separate runtime qualification; see README.md.
"""

import hashlib
import os
import stat
import sys


_ADMITTED_SCRIPT = "/Users/nick/Projects/rawdog/scripts/synthetic_worker/worker.py"
_ADMITTED_CHECKOUT = "/Users/nick/Projects/rawdog"


class BoundaryError(ValueError):
    """A spelling, file type, ownership check, or operation was refused."""


def _absolute_parts(path):
    # Do not normalize, resolve, consult cwd, or invoke caller-defined __fspath__.
    if type(path) is not str or not path.startswith("/") or "\0" in path:
        raise BoundaryError("an absolute literal path is required")
    parts = path.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise BoundaryError("empty, dot, and parent components are refused")
    return tuple(parts)


def _script_ceiling():
    parts = _absolute_parts(__file__)
    if __file__ != _ADMITTED_SCRIPT:
        raise BoundaryError("worker script location is not admitted")
    return "/" + "/".join(parts[:-1])


def _directory_flags():
    if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")):
        raise BoundaryError("required no-follow descriptor primitives are unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _identity(info):
    return info.st_dev, info.st_ino


def _regular(info):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BoundaryError("only regular files with one link are admitted")
    return info


def _open_ceiling():
    # Anchor inside the canonical checkout; never inspect its outside ancestors.
    # These handles only admit the script location, not repository data access.
    flags = _directory_flags()
    fd = os.open(_ADMITTED_CHECKOUT, flags)
    try:
        for component in ("scripts", "synthetic_worker"):
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        _regular(os.stat("worker.py", dir_fd=fd, follow_symlinks=False))
        return fd
    except BaseException:
        os.close(fd)
        raise


class OwnedRun:
    """A fresh synthetic directory, with no attach/reuse/reset capability.

    Public methods admit absolute paths inside THIS run only. Constructor and
    underscored fields are implementation details, not an adversarial Python
    security boundary. There is no product/library I/O interception.
    """

    def __init__(self):
        raise BoundaryError("use OwnedRun.create()")

    @classmethod
    def create(cls, name=None):
        ceiling = _script_ceiling()
        if name is None:
            name = "run-" + os.urandom(16).hex()
        if (type(name) is not str or not name.startswith("run-") or
                not 5 <= len(name) <= 80 or
                any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in name)):
            raise BoundaryError("run name must be a single run-NAME component")
        flags = _directory_flags()
        # The canonical checkout and every in-repository script component are
        # opened without following links. Outside ancestors remain a launcher
        # qualification precondition, not an excuse for outside inspection.
        ceiling_fd = _open_ceiling()
        run_fd = None
        try:
            os.mkdir(name, mode=0o700, dir_fd=ceiling_fd)  # Exclusive; no exist_ok.
            created = os.stat(name, dir_fd=ceiling_fd, follow_symlinks=False)
            run_fd = os.open(name, flags, dir_fd=ceiling_fd)
            opened = os.fstat(run_fd)
            if (not stat.S_ISDIR(created.st_mode) or
                    _identity(created) != _identity(opened) or
                    opened.st_uid != os.geteuid() or opened.st_mode & 0o077):
                raise BoundaryError("fresh directory ownership changed")
            instance = object.__new__(cls)
            instance._ceiling_fd = ceiling_fd
            instance._fd = run_fd
            instance._name = name
            instance._identity = _identity(opened)
            instance._root = ceiling + "/" + name
            instance._root_parts = _absolute_parts(instance._root)
            instance._closed = False
            return instance
        except BaseException:
            if run_fd is not None:
                os.close(run_fd)
            os.close(ceiling_fd)
            # Never clean up an uncertain pathname after a failed claim.
            raise

    @property
    def root(self):
        return self._root

    def _parts(self, path, *, allow_root=False):
        parts = _absolute_parts(path)
        count = len(self._root_parts)
        if parts[:count] != self._root_parts:
            raise BoundaryError("path is outside this owned synthetic run")
        relative = parts[count:]
        if not relative and not allow_root:
            raise BoundaryError("the run root cannot be mutated as a file")
        return relative

    def _live(self):
        if self._closed:
            raise BoundaryError("run capability is closed")
        current = os.stat(self._name, dir_fd=self._ceiling_fd, follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or _identity(current) != self._identity:
            raise BoundaryError("run pathname was replaced")
        if _identity(os.fstat(self._fd)) != self._identity:
            raise BoundaryError("run descriptor was replaced")

    def _directory(self, parts):
        self._live()
        fd = os.dup(self._fd)
        try:
            for part in parts:
                next_fd = os.open(part, _directory_flags(), dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _file(self, parent_fd, name):
        before = _regular(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        if not hasattr(os, "O_NONBLOCK"):
            raise BoundaryError("nonblocking open is unavailable")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                     os.O_NONBLOCK, dir_fd=parent_fd)
        try:
            opened = _regular(os.fstat(fd))
            if _identity(before) != _identity(opened):
                raise BoundaryError("file changed while opening")
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _vacant(parent_fd, name):
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise BoundaryError("destination already exists, including a dangling link")

    @staticmethod
    def _write_all(fd, data):
        pending = memoryview(data)
        while pending:
            count = os.write(fd, pending)
            if count <= 0:
                raise OSError("short synthetic write")
            pending = pending[count:]

    def mkdir(self, path):
        parts = self._parts(path)
        parent = self._directory(parts[:-1])
        try:
            os.mkdir(parts[-1], mode=0o700, dir_fd=parent)
        finally:
            os.close(parent)

    def write_new(self, path, data):
        parts = self._parts(path)
        if type(data) is not bytes:
            raise BoundaryError("synthetic contents must be bytes")
        parent = self._directory(parts[:-1])
        fd = None
        try:
            fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
            _regular(os.fstat(fd))
            self._write_all(fd, data)
            _regular(os.fstat(fd))
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def read(self, path):
        parts = self._parts(path)
        parent = self._directory(parts[:-1])
        fd = None
        try:
            fd = self._file(parent, parts[-1])
            chunks = []
            while True:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            _regular(os.fstat(fd))
            return b"".join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def sha256(self, path):
        return hashlib.sha256(self.read(path)).hexdigest()

    def metadata(self, path):
        parts = self._parts(path, allow_root=True)
        if not parts:
            self._live()
            info = os.fstat(self._fd)
        else:
            parent = self._directory(parts[:-1])
            try:
                info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    _regular(info)
            finally:
                os.close(parent)
        return {"size": info.st_size, "mode": info.st_mode, "links": info.st_nlink}

    def list_dir(self, path):
        parts = self._parts(path, allow_root=True)
        fd = self._directory(parts)
        try:
            names = os.listdir(fd)
            for name in names:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    _regular(info)
            return sorted(names)
        finally:
            os.close(fd)

    def _copy_or_move(self, source, destination, *, move):
        # Both spellings MUST pass before even the source root/metadata is read.
        source_parts = self._parts(source)
        destination_parts = self._parts(destination)
        source_parent = self._directory(source_parts[:-1])
        destination_parent = source_fd = destination_fd = None
        try:
            destination_parent = self._directory(destination_parts[:-1])
            self._vacant(destination_parent, destination_parts[-1])
            source_fd = self._file(source_parent, source_parts[-1])
            destination_fd = os.open(destination_parts[-1], os.O_WRONLY |
                                     os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                                     os.O_CLOEXEC, 0o600, dir_fd=destination_parent)
            _regular(os.fstat(destination_fd))
            while True:
                chunk = os.read(source_fd, 64 * 1024)
                if not chunk:
                    break
                self._write_all(destination_fd, chunk)
            _regular(os.fstat(destination_fd))
            final_source = _regular(os.fstat(source_fd))
            if move:
                current = _regular(os.stat(source_parts[-1], dir_fd=source_parent,
                                           follow_symlinks=False))
                if _identity(current) != _identity(final_source):
                    raise BoundaryError("move source was replaced")
                os.unlink(source_parts[-1], dir_fd=source_parent)
        finally:
            for fd in (destination_fd, source_fd, destination_parent, source_parent):
                if fd is not None:
                    os.close(fd)

    def copy_file(self, source, destination):
        self._copy_or_move(source, destination, move=False)

    def move_file(self, source, destination):
        # New copy then source unlink; deliberately NOT an atomic rename.
        self._copy_or_move(source, destination, move=True)

    def delete_file(self, path):
        parts = self._parts(path)
        parent = self._directory(parts[:-1])
        try:
            _regular(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False))
            os.unlink(parts[-1], dir_fd=parent)
        finally:
            os.close(parent)

    def remove_empty_dir(self, path):
        parts = self._parts(path)
        parent = self._directory(parts[:-1])
        fd = None
        try:
            fd = os.open(parts[-1], _directory_flags(), dir_fd=parent)
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(current.st_mode) or _identity(current) != _identity(os.fstat(fd)):
                raise BoundaryError("directory was replaced")
            os.rmdir(parts[-1], dir_fd=parent)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def close(self):
        if not self._closed:
            self._closed = True
            os.close(self._fd)
            os.close(self._ceiling_fd)


def main():
    # No environment value, CLI option, receipt, or caller boolean opens this
    # gate. Adding a qualified execution path requires separately reviewed code.
    sys.stderr.write(
        "BLOCKED: Python/import/native runtime and OS containment are unqualified; "
        "named package approval is also required. No product or media work ran.\n"
    )
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
