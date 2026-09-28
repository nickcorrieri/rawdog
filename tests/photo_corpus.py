"""Small generated media fixtures. This module never opens a user library.

Run: .venv/bin/python tests/photo_corpus.py
Outputs a fresh temporary corpus, its expected manifest, and read-only observations.
JPEGs decode; vendor RAWs are metadata containers, not camera sensor/decoder samples.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import struct
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Original 8x8 solid-colour images generated locally from synthetic BMP pixels.
# No downloaded or user photographs. Strip the encoder's EXIF before adding ours.
_JPEG = (
    "/9j/4AAQSkZJRgABAQAASABIAAD/4QCARXhpZgAATU0AKgAAAAgABAEaAAUAAAABAAAAPgEbAAUAAAAB"
    "AAAARgEoAAMAAAABAAIAAIdpAAQAAAABAAAATgAAAAAAAABIAAAAAQAAAEgAAAABAAOgAQADAAAAAQAB"
    "AACgAgAEAAAAAQAAAAigAwAEAAAAAQAAAAgAAAAA/+0AOFBob3Rvc2hvcCAzLjAAOEJJTQQEAAAAAAAA"
    "OEJJTQQlAAAAAAAQ1B2M2Y8AsgTpgAmY7PhCfv/AABEIAAgACAMBIgACEQEDEQH/xAAfAAABBQEBAQEB"
    "AQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMDAgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEU"
    "MoGRoQgjQrHBFVLR8CQzYnKCCQoWFxgZGiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2Rl"
    "ZmdoaWpzdHV2d3h5eoOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK"
    "0tPU1dbX2Nna4eLj5OXm5+jp6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEBAAAAAAAAAQIDBAUGBwgJ"
    "Cgv/xAC1EQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEK"
    "FiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SF"
    "hoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery"
    "8/T19vf4+fr/2wBDAAICAgICAgMCAgMFAwMDBQYFBQUFBggGBgYGBggKCAgICAgICgoKCgoKCgoMDAwM"
    "DAwODg4ODg8PDw8PDw8PDw//2wBDAQICAgQEBAcEBAcQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE"
    "BAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/3QAEAAH/2gAMAwEAAhEDEQA/AMOiiiv4nP8ARg//2Q=="
)

FORMATS = {
    "jpg": ("JPEG", "Synthetic JPEG"),
    "jpeg": ("JPEG", "Synthetic JPEG"),
    "CR2": ("Canon", "Synthetic CR2"),
    "CR3": ("Canon", "Synthetic CR3"),
    "NEF": ("NIKON CORPORATION", "Synthetic NEF"),
    "ARW": ("SONY", "Synthetic ARW"),
}

SHOT = "2024-05-20T10:30:00.125000-05:00"
UTC_SHOT = "2024-05-20T15:30:00.125000+00:00"
FS_SHOT = "2024-05-20T15:30:00+00:00"

# Expected answers are literal seed data, not calculated by RAWdog's planner.
# "approved" is fixture input: plausibility alone cannot establish historical truth.
CASES = [
    dict(id="filesystem_plausible", shot=None, mtime=FS_SHOT, birth=FS_SHOT,
         expected_shot=None, action="retain_filesystem_candidate", approved=False),
    dict(id="filesystem_owner_confirmed", shot=None, mtime=FS_SHOT, birth=FS_SHOT,
         expected_shot=FS_SHOT, action="propose_capture_metadata", approved=True),
    dict(id="filesystem_epoch", shot=None, mtime="1970-01-01T00:00:00+00:00",
         birth="1970-01-01T00:00:00+00:00", expected_shot=None, action="needs_owner_input", approved=False),
    dict(id="filesystem_future", shot=None, mtime="2099-01-01T00:00:00+00:00",
         birth="2099-01-01T00:00:00+00:00", expected_shot=None, action="needs_owner_input", approved=False),
    dict(id="filesystem_disagreement", shot=None, mtime="2025-08-01T00:00:00+00:00",
         birth=FS_SHOT, expected_shot=None, action="needs_owner_input", approved=False),
    dict(id="metadata_good_filesystem_wrong", shot=SHOT, mtime="2001-01-01T00:00:00+00:00",
         birth="2025-08-01T00:00:00+00:00", expected_shot=UTC_SHOT,
         action="propose_filesystem_timestamp_repair", approved=True),
    dict(id="metadata_suspect", shot="2000-01-01T00:00:00-05:00", mtime=FS_SHOT,
         birth=FS_SHOT, expected_shot=None, action="needs_owner_input", approved=False),
    dict(id="camera_slow_8h", shot="2024-05-20T02:30:00.125000-05:00", mtime=FS_SHOT,
         birth=FS_SHOT, delta="+8h", expected_shot=UTC_SHOT, action="apply_owner_delta", approved=True),
    dict(id="camera_fast_8h", shot="2024-05-20T18:30:00.125000-05:00", mtime=FS_SHOT,
         birth=FS_SHOT, delta="-8h", expected_shot=UTC_SHOT, action="apply_owner_delta", approved=True),
    dict(id="camera_slow_12d2h_may", shot="2024-05-08T08:30:00.125000-05:00", mtime=FS_SHOT,
         birth=FS_SHOT, delta="+12d2h", expected_shot=UTC_SHOT, action="apply_owner_delta", approved=True),
    dict(id="camera_slow_12d2h_july", shot="2024-07-08T08:30:00.125000-05:00",
         mtime="2024-07-20T15:30:00+00:00", birth="2024-07-20T15:30:00+00:00",
         delta="+12d2h", expected_shot="2024-07-20T15:30:00.125000+00:00",
         action="apply_owner_delta", approved=True),
    dict(id="camera_fast_12d2h", shot="2024-06-01T12:30:00.125000-05:00", mtime=FS_SHOT,
         birth=FS_SHOT, delta="-12d2h", expected_shot=UTC_SHOT, action="apply_owner_delta", approved=True),
    dict(id="camera_fixed_august_control", shot="2024-08-20T10:30:00.125000-05:00",
         mtime="2024-08-20T15:30:00+00:00", birth="2024-08-20T15:30:00+00:00",
         expected_shot="2024-08-20T15:30:00.125000+00:00", action="leave_unchanged", approved=True),
    dict(id="different_camera_control", shot=SHOT, mtime=FS_SHOT, birth=FS_SHOT,
         body="BODY-B", expected_shot=UTC_SHOT, action="leave_unchanged", approved=True),
    dict(id="metadata_timezone_unknown", shot="2024-05-20T10:30:00.125000", mtime=FS_SHOT,
         birth=FS_SHOT, expected_shot=None, action="needs_timezone", approved=False),
    dict(id="dst_first_0130", shot="2024-11-03T01:30:00-04:00",
         mtime="2024-11-03T05:30:00+00:00", birth="2024-11-03T05:30:00+00:00",
         expected_shot="2024-11-03T05:30:00+00:00", action="leave_unchanged", approved=True),
    dict(id="dst_second_0130", shot="2024-11-03T01:30:00-05:00",
         mtime="2024-11-03T06:30:00+00:00", birth="2024-11-03T06:30:00+00:00",
         expected_shot="2024-11-03T06:30:00+00:00", action="leave_unchanged", approved=True),
]


def _ascii(tag: int, value: str) -> tuple[int, int, int, bytes]:
    payload = value.encode("ascii") + b"\0"
    return tag, 2, len(payload), payload


def _number(tag: int, value: int, kind: int = 4) -> tuple[int, int, int, bytes]:
    return tag, kind, 1, struct.pack("<H" if kind == 3 else "<I", value)


def _ifd(entries: list[tuple], offset: int) -> bytes:
    entries = sorted(entries)
    extra = bytearray()
    directory = bytearray(struct.pack("<H", len(entries)))
    data_start = offset + 2 + 12 * len(entries) + 4
    for tag, kind, count, payload in entries:
        if len(payload) > 4:
            value = struct.pack("<I", data_start + len(extra))
            extra.extend(payload)
            extra.extend(b"\0" * (len(extra) % 2))
        else:
            value = payload.ljust(4, b"\0")
        directory.extend(struct.pack("<HHI", tag, kind, count) + value)
    return bytes(directory) + b"\0" * 4 + bytes(extra)


def _tiff(extension: str, shot: str | None, identity: str, body: str, variant: int) -> bytes:
    make, model = FORMATS[extension]
    header_size = 16 if extension == "CR2" else 8
    exif = []
    if shot:
        captured = datetime.fromisoformat(shot)
        exif = [
            (0x9000, 7, 4, b"0232"),
            _ascii(0x9003, captured.strftime("%Y:%m:%d %H:%M:%S")),
            _ascii(0x9004, captured.strftime("%Y:%m:%d %H:%M:%S")),
            _ascii(0xA420, identity), _ascii(0xA431, body),
        ]
        if captured.microsecond:
            exif += [_ascii(0x9291, f"{captured.microsecond:06d}"), _ascii(0x9292, f"{captured.microsecond:06d}")]
        if captured.tzinfo is not None:
            zone = captured.strftime("%z")
            exif += [_ascii(0x9011, zone[:3] + ":" + zone[3:]), _ascii(0x9012, zone[:3] + ":" + zone[3:])]
    entries = [
        _number(0x100, 8), _number(0x101, 8), _number(0x102, 8, 3),
        _number(0x103, 1, 3), _number(0x106, 1, 3),
        _ascii(0x10E, identity), _ascii(0x10F, make), _ascii(0x110, model),
        _number(0x111, 0), _number(0x115, 1, 3), _number(0x116, 8), _number(0x117, 64),
        _ascii(0x131, "RAWdog synthetic fixture"),
    ]
    if exif:
        entries.append(_number(0x8769, 0))
    exif_offset = header_size + len(_ifd(entries, header_size))
    exif_bytes = _ifd(exif, exif_offset) if exif else b""
    pixel_offset = exif_offset + len(exif_bytes)
    entries = [
        _number(tag, pixel_offset if tag == 0x111 else exif_offset)
        if tag in {0x111, 0x8769} else (tag, kind, count, value)
        for tag, kind, count, value in entries
    ]
    header = b"II*\0" + struct.pack("<I", header_size)
    if extension == "CR2":
        header += b"CR\x02\0" + struct.pack("<I", header_size)
    return header + _ifd(entries, header_size) + exif_bytes + bytes([40 if variant == 0 else 210]) * 64


def _box(kind: bytes, value: bytes) -> bytes:
    return struct.pack(">I", 8 + len(value)) + kind + value


def _jpeg(shot: str | None, identity: str, body: str, extension: str, variant: int) -> bytes:
    source = base64.b64decode(_JPEG)
    result = bytearray(source[:2])
    position = 2
    while source[position:position + 2] != b"\xff\xda":
        length = struct.unpack(">H", source[position + 2:position + 4])[0]
        end = position + 2 + length
        if source[position + 1] not in {0xE1, 0xED}:
            result.extend(source[position:end])
        position = end
    # Both scans encode a real 8x8 image and have the same length.
    scan = source[position:] if variant == 0 else bytes.fromhex("ffda000c03010002110311003f00f94e8a28aff4c0fe533fffd9")
    comment = identity.encode("ascii")
    result.extend(b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment)
    if shot:
        exif = b"Exif\0\0" + _tiff(extension, shot, identity, body, variant)
        result.extend(b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif)
    return bytes(result) + scan


def media_bytes(extension: str, shot: str | None, content_seed: str, body: str = "BODY-A", variant: int = 0) -> bytes:
    identity = hashlib.sha256(content_seed.encode("ascii")).hexdigest()[:32]
    if extension in {"jpg", "jpeg"}:
        return _jpeg(shot, identity, body, extension, variant)
    tiff = _tiff(extension, shot, identity, body, variant)
    if extension == "CR3":
        canon_uuid = bytes.fromhex("85c0b687820f11e08111f4ce462b6a48")
        tags = _box(b"CNCV", b"CanonCR3_001\0") + _box(b"CMT1", tiff)
        return _box(b"ftyp", b"crx \0\0\0\0crx isom") + _box(b"moov", _box(b"uuid", canon_uuid + tags))
    return tiff


def _set_birthtime(path: Path, value: float) -> bool:
    """Fixture-only setter; ctime is deliberately not confused with creation time."""
    if sys.platform != "darwin":
        return False

    class AttrList(ctypes.Structure):
        _fields_ = [("count", ctypes.c_ushort), ("reserved", ctypes.c_ushort)] + [
            (name, ctypes.c_uint) for name in ("common", "volume", "directory", "file", "fork")
        ]

    class Timespec(ctypes.Structure):
        _fields_ = [("seconds", ctypes.c_long), ("nanoseconds", ctypes.c_long)]

    attributes = AttrList(5, 0, 0x00000200, 0, 0, 0, 0)
    timestamp = Timespec(int(value), round((value % 1) * 1_000_000_000))
    libc = ctypes.CDLL("libc.dylib", use_errno=True)
    if libc.setattrlist(os.fsencode(path), ctypes.byref(attributes), ctypes.byref(timestamp), ctypes.sizeof(timestamp), 1):
        raise OSError(ctypes.get_errno(), "Unable to seed fixture creation time", str(path))
    return True


def build_corpus(parent: Path | None = None) -> tuple[Path, dict]:
    """Always creates a new owned directory below an OS temporary directory."""
    allowed = [Path(tempfile.gettempdir()).resolve(), Path("/private/tmp").resolve()]
    parent = (parent or Path(tempfile.gettempdir())).resolve()
    if not any(parent == root or parent.is_relative_to(root) for root in allowed):
        raise ValueError("Synthetic corpus output must be under an OS temporary directory")
    root = Path(tempfile.mkdtemp(prefix="rawdog-photo-corpus-", dir=parent)).resolve()
    (root / ".rawdog-synthetic-corpus").write_text("Generated test media only. Never a user library.\n")
    records = []

    def seed(case: dict, extension: str, *, role: str = "working", content_seed: str | None = None,
             duplicate_group: str | None = None, variant: int = 0) -> None:
        relative = Path("media") / case["id"] / extension / f"IMG_0001.{extension}"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = media_bytes(extension, case["shot"], content_seed or case["id"] + extension,
                              case.get("body", "BODY-A"), variant)
        with path.open("xb") as handle:
            handle.write(payload)
        mtime = datetime.fromisoformat(case["mtime"]).timestamp()
        birth = datetime.fromisoformat(case["birth"]).timestamp()
        os.utime(path, (mtime, mtime))
        birth_seeded = _set_birthtime(path, birth)
        records.append({
            **case, "path": str(relative), "format": extension, "role": role,
            "coverage": "decodable_jpeg" if extension in {"jpg", "jpeg"} else "synthetic_raw_metadata_container",
            "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "duplicate_group": duplicate_group, "birthtime_seeded": birth_seeded,
            "protection": "protected" if role in {"archive", "intentional_backup"} else "ordinary",
            "future_behavior_implemented": False,
        })

    for case in CASES:
        for extension in FORMATS:
            seed(case, extension)
    for index, role in enumerate(("working", "working", "archive", "intentional_backup")):
        case = dict(id=f"exact_duplicate_{index + 1}", shot=SHOT,
                    mtime=f"202{index + 1}-08-01T00:00:00+00:00", birth=f"202{index + 1}-08-02T00:00:00+00:00",
                    expected_shot=UTC_SHOT, action="preserve_protected_copy" if index > 1 else "review_exact_duplicate",
                    approved=True)
        for extension in FORMATS:
            seed(case, extension, role=role, content_seed="exact-copy-" + extension, duplicate_group="exact-copy-" + extension)
    for index in range(2):
        case = dict(id=f"filename_rollover_{index + 1}", shot=None, mtime=FS_SHOT,
                    birth=FS_SHOT, expected_shot=None, action="preserve_distinct_content", approved=False)
        for extension in FORMATS:
            seed(case, extension, variant=index)

    manifest = {"schema_version": 1, "synthetic": True, "as_of": "2026-09-28T00:00:00+00:00",
                "scope": "Test corpus only; expected actions are future product requirements.",
                "raw_limit": "Metadata parsing, scan, copy, and hash fixtures; no compressed camera sensor data or decoder validation.",
                "clock_correction_scope": {"body": "BODY-A", "selected_case_ids": [c["id"] for c in CASES if c.get("delta")],
                                           "exclude": ["camera_fixed_august_control", "different_camera_control"]},
                "files": records}
    (root / "expected.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return root, manifest


def inspect_corpus(root: Path, manifest: dict) -> dict:
    """Only read files named in this generated corpus, using RAWdog's real readers."""
    from rawdog.inventory import scan_raw_files
    from rawdog.metadata import has_media_metadata_reader, media_capture_times
    from rawdog.verifier import sha256_file

    if not (root / ".rawdog-synthetic-corpus").is_file():
        raise ValueError("Not a generated test corpus")
    paths = [item.path for item in scan_raw_files(root / "media")]
    embedded = media_capture_times(paths)
    groups = defaultdict(list)
    observations = []
    expected_by_path = {row["path"]: row for row in manifest["files"]}
    for path in paths:
        relative = str(path.relative_to(root))
        expected = expected_by_path[relative]
        digest = sha256_file(path)
        groups[digest].append(relative)
        stat = path.stat()
        birth = getattr(stat, "st_birthtime", None)
        captured = embedded.get(path)
        observations.append({
            "path": relative, "sha256_matches_seed": digest == expected["sha256"],
            "embedded_capture_at": captured.isoformat() if captured else None,
            "filesystem_modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            "filesystem_created_at": datetime.fromtimestamp(birth, UTC).isoformat() if birth is not None else None,
            "required_future_action": expected["action"],
        })
    return {"metadata_reader_available": has_media_metadata_reader(), "file_count": len(paths),
            "media_bytes": sum(path.stat().st_size for path in paths),
            "exact_duplicate_groups": [paths for paths in groups.values() if len(paths) > 1], "observations": observations}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if len(sys.argv) != 1:
        raise SystemExit("No input/output paths accepted. This generator always creates a fresh temporary corpus.")
    corpus_root, expected = build_corpus()
    observed = inspect_corpus(corpus_root, expected)
    (corpus_root / "observed.json").write_text(json.dumps(observed, indent=2) + "\n")
    print(json.dumps({"root": str(corpus_root), "files": observed["file_count"],
                      "media_bytes": observed["media_bytes"], "duplicate_groups": len(observed["exact_duplicate_groups"]),
                      "metadata_reader_available": observed["metadata_reader_available"]}, indent=2))
