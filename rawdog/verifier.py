# Author: Nicholas Corrieri

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

from rawdog.safety import (
    SafetyError,
    absolute_lexical_path,
    ensure_no_symlink_components,
    open_directory,
    require_directory_path,
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    return capture_file_version(path, chunk_size=chunk_size)["sha256"]


def verify_same_bytes(source: Path, destination: Path) -> bool:
    left = capture_file_version(source)
    right = capture_file_version(destination)
    require_file_version(source, left)
    require_file_version(destination, right)
    return (left["size"], left["sha256"], left["ancillary"]) == (
        right["size"], right["sha256"], right["ancillary"],
    )


@contextmanager
def open_regular_file(path: Path, *, require_path_after: bool = True):
    ensure_no_symlink_components(path)
    lexical = absolute_lexical_path(path)
    parent = open_directory(lexical.parent)
    descriptor = None
    try:
        descriptor = os.open(lexical.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SafetyError(f"not an accessible regular file: {path}")
        require_directory_path(lexical.parent, parent)
        yield descriptor
        if require_path_after:
            require_directory_path(lexical.parent, parent)
            current = os.stat(lexical.name, dir_fd=parent, follow_symlinks=False)
            pinned = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise SafetyError(f"file replaced while reading: {path}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _stat_version(observed: os.stat_result) -> dict:
    return {"size": observed.st_size, "mtime_ns": observed.st_mtime_ns,
            "ctime_ns": observed.st_ctime_ns, "dev": observed.st_dev, "ino": observed.st_ino}


def read_ancillary_payloads(descriptor: int) -> dict[str, bytes]:
    try:
        if sys.platform == "darwin":
            libc = ctypes.CDLL("libc.dylib", use_errno=True)
            listing = libc.flistxattr
            listing.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
            listing.restype = ctypes.c_ssize_t
            getter = libc.fgetxattr
            getter.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                               ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
            getter.restype = ctypes.c_ssize_t
            length = listing(descriptor, None, 0, 0)
            if length < 0:
                raise OSError(ctypes.get_errno(), "cannot enumerate ancillary payload")
            if not length:
                return {}
            names = ctypes.create_string_buffer(length)
            actual = listing(descriptor, names, length, 0)
            if actual != length:
                raise SafetyError("ancillary names changed while reading")
            payloads = {}
            for name in sorted(names.raw[:actual].rstrip(b"\0").split(b"\0")):
                size = getter(descriptor, name, None, 0, 0, 0)
                if size < 0:
                    raise OSError(ctypes.get_errno(), "cannot read ancillary payload")
                buffer = ctypes.create_string_buffer(max(size, 1))
                actual_size = getter(descriptor, name, buffer, size, 0, 0)
                if actual_size != size:
                    raise SafetyError("ancillary payload changed while reading")
                payloads[os.fsdecode(name)] = buffer.raw[:size]
            return payloads
        if hasattr(os, "listxattr") and hasattr(os, "getxattr"):
            return {name: os.getxattr(descriptor, name) for name in sorted(os.listxattr(descriptor))}
        raise SafetyError("ancillary payload identity is unsupported on this runtime")
    except OSError as exc:
        raise SafetyError(f"ancillary payload could not be verified: {exc}") from exc


def set_ancillary_payloads(descriptor: int, payloads: dict[str, bytes]) -> None:
    try:
        if sys.platform == "darwin":
            setter = ctypes.CDLL("libc.dylib", use_errno=True).fsetxattr
            setter.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                               ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
            setter.restype = ctypes.c_int
            for name, value in payloads.items():
                buffer = ctypes.create_string_buffer(value, max(len(value), 1))
                if setter(descriptor, os.fsencode(name), buffer, len(value), 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "cannot preserve ancillary payload")
        elif hasattr(os, "setxattr"):
            for name, value in payloads.items():
                os.setxattr(descriptor, name, value)
        elif payloads:
            raise SafetyError("ancillary preservation is unsupported on this runtime")
    except OSError as exc:
        raise SafetyError(f"ancillary payload could not be preserved: {exc}") from exc


def _ancillary_digests(descriptor: int) -> dict:
    return {name: hashlib.sha256(value).hexdigest()
            for name, value in read_ancillary_payloads(descriptor).items()}


def capture_open_file_version(descriptor: int, *, chunk_size: int = 1024 * 1024) -> dict:
    """Hash a held regular-file descriptor and detect mutation across the read."""
    before = _stat_version(os.fstat(descriptor))
    ancillary = _ancillary_digests(descriptor)
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    if chunk_size <= 0:
        raise ValueError("hash chunk size must be positive")
    while chunk := os.read(descriptor, chunk_size):
        digest.update(chunk)
    after = _stat_version(os.fstat(descriptor))
    if before != after or ancillary != _ancillary_digests(descriptor):
        raise SafetyError("file changed while its content identity was being read")
    return {**after, "sha256": digest.hexdigest(), "ancillary": ancillary}


def capture_file_version(path: Path, *, chunk_size: int = 1024 * 1024) -> dict:
    with open_regular_file(path) as descriptor:
        return capture_open_file_version(descriptor, chunk_size=chunk_size)


def require_file_version(path: Path, expected: dict) -> None:
    required = {"sha256", "size", "mtime_ns", "ctime_ns", "dev", "ino", "ancillary"}
    if not isinstance(expected, dict) or not required.issubset(expected):
        raise SafetyError(f"reviewed file version is missing required evidence: {path}")
    if capture_file_version(path) != expected:
        raise SafetyError(f"file changed since its reviewed version: {path}")
