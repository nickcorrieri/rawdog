"""Patterned synthetic JPEG relations; no user-library arguments or installations.

Run .venv/bin/python tests/photo_variants.py to allocate a fresh temporary corpus.
"""

# Author: Nicholas Corrieri

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

SHOT_TAGS = {
    "DateTimeOriginal": "2024:05:20 10:30:00",
    "OffsetTimeOriginal": "-05:00",
    "SubSecTimeOriginal": "125",
}
CAPTURE_ISO = "2024-05-20T10:30:00.125000-05:00"
WIDTH, HEIGHT = 64, 48


def _pattern(control: bool = False) -> list[list[tuple[int, int, int]]]:
    palette = [(24, 40, 72), (232, 96, 32), (32, 184, 160), (248, 224, 96)]
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            # Asymmetric coloured blocks, diagonal, circle, and fine stripes.
            index = (x // 16 + y // 12) % 4 if control else (x // 24 + y // 20) % 4
            if (x - (48 if control else 15)) ** 2 + (y - 13) ** 2 < 70:
                index = 3
            if abs(x - y - (15 if control else 3)) < 3:
                index = 1
            colour = palette[index]
            if y > 34 and x < 28 and x % 4 < 2:
                colour = (240, 240, 240)
            row.append(colour)
        rows.append(row)
    return rows


def _bmp(rows: list[list[tuple[int, int, int]]]) -> bytes:
    height, width = len(rows), len(rows[0])
    stride = (width * 3 + 3) & ~3
    pixels = b"".join(
        b"".join(bytes((b, g, r)) for r, g, b in row).ljust(stride, b"\0")
        for row in reversed(rows)
    )
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return header + info + pixels


def _tiff(*, orientation: int = 1, description: str = "Patterned synthetic original") -> bytes:
    def ascii_entry(tag: int, value: str):
        payload = value.encode("ascii") + b"\0"
        return tag, 2, len(payload), payload

    def ifd(entries, offset):
        entries = sorted(entries)
        data_start = offset + 2 + 12 * len(entries) + 4
        directory = bytearray(struct.pack("<H", len(entries)))
        extra = bytearray()
        for tag, kind, count, payload in entries:
            if len(payload) > 4:
                value = struct.pack("<I", data_start + len(extra))
                extra.extend(payload)
                extra.extend(b"\0" * (len(extra) % 2))
            else:
                value = payload.ljust(4, b"\0")
            directory.extend(struct.pack("<HHI", tag, kind, count) + value)
        return bytes(directory) + b"\0" * 4 + bytes(extra)

    entries = [
        ascii_entry(0x010E, description),
        (0x0112, 3, 1, struct.pack("<H", orientation)),
        (0x8769, 4, 1, struct.pack("<I", 0)),
    ]
    exif_offset = 8 + len(ifd(entries, 8))
    entries[-1] = (0x8769, 4, 1, struct.pack("<I", exif_offset))
    exif = [
        (0x9000, 7, 4, b"0232"),
        ascii_entry(0x9003, SHOT_TAGS["DateTimeOriginal"]),
        ascii_entry(0x9011, SHOT_TAGS["OffsetTimeOriginal"]),
        ascii_entry(0x9291, SHOT_TAGS["SubSecTimeOriginal"]),
    ]
    return b"II*\0" + struct.pack("<I", 8) + ifd(entries, 8) + ifd(exif, exif_offset)


def _strip_app_metadata(data: bytes) -> bytes:
    """Keep JPEG coding segments and remove encoder's EXIF/Photoshop metadata."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("Expected a generated JPEG")
    output = bytearray(data[:2])
    position = 2
    while data[position:position + 2] != b"\xff\xda":
        length = struct.unpack(">H", data[position + 2:position + 4])[0]
        end = position + 2 + length
        if data[position + 1] not in {0xE1, 0xED}:
            output.extend(data[position:end])
        position = end
    return bytes(output) + data[position:]


def _with_exif(data: bytes, **kwargs) -> bytes:
    data = _strip_app_metadata(data)
    payload = b"Exif\0\0" + _tiff(**kwargs)
    return data[:2] + b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload + data[2:]


def _run_sips(sips: str, *args: str) -> None:
    subprocess.run([sips, *args], check=True, capture_output=True, timeout=30)


def build_variant_corpus() -> tuple[Path, dict]:
    """Create only new seed files under a newly allocated OS temporary directory."""
    sips = shutil.which("sips")
    if not sips:
        raise RuntimeError("Pattern generation requires existing macOS sips; nothing is installed")
    root = Path(tempfile.mkdtemp(prefix="rawdog-jpeg-variants-")).resolve()
    media, scratch = root / "media", root / "scratch"
    media.mkdir()
    scratch.mkdir()
    bitmap = scratch / "pattern.bmp"
    bitmap.write_bytes(_bmp(_pattern()))
    encoded = scratch / "pattern.jpg"
    _run_sips(sips, "-s", "format", "jpeg", "-s", "formatOptions", "90", str(bitmap), "--out", str(encoded))
    original = _with_exif(encoded.read_bytes())
    rows = []

    def add(identity, data, dimensions, relation, outcome, *, role="working", orientation=1,
            metadata="preserved_subset", basename="IMG_0001.jpg", mtime=1716219000):
        path = media / identity / basename
        path.parent.mkdir()
        path.write_bytes(data)
        os.utime(path, (mtime, mtime))
        rows.append({
            "id": identity, "path": str(path.relative_to(root)), "dimensions": list(dimensions),
            "rendered_dimensions": list(reversed(dimensions)) if orientation == 6 else list(dimensions),
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "mtime": mtime,
            "role": role, "orientation": orientation, "metadata": metadata,
            "capture_tags": SHOT_TAGS if metadata != "stripped" else {},
            "known_seed_relation": relation, "expected_read_only_outcome": outcome,
            "scan_authorizes_removal": False,
        })

    add("original", original, (64, 48), "reference", "reference", role="archive")
    add("exact_copy_working", original, (64, 48), "exact_bytes", "exact_present", mtime=946684800)
    add("exact_copy_backup", original, (64, 48), "exact_bytes", "exact_present_protected_backup",
        role="intentional_backup", mtime=1735689600)
    add("same_pixels_metadata_changed", _with_exif(original, description="Owner added a rating note"),
        (64, 48), "same_encoded_image_different_metadata", "same_pixels_metadata_review")
    add("exif_stripped", _strip_app_metadata(original), (64, 48),
        "same_encoded_image_metadata_removed", "same_pixels_metadata_review", metadata="stripped")

    for identity, args, dimensions, relation in [
        ("recompressed", [], (64, 48), "recompressed_derivative"),
        ("reduced_recompressed", ["-z", "24", "32"], (32, 24), "resized_recompressed_derivative"),
        ("upscaled_recompressed", ["-z", "96", "128"], (128, 96), "upscaled_recompressed_derivative"),
        ("crop", ["-c", "32", "48"], (48, 32), "cropped_derivative"),
        ("rotated_pixels", ["-r", "90"], (48, 64), "rotated_reencoded_derivative"),
    ]:
        output = scratch / f"{identity}.jpg"
        _run_sips(sips, *args, "-s", "format", "jpeg", "-s", "formatOptions", "45",
                  str(encoded), "--out", str(output))
        add(identity, _with_exif(output.read_bytes()), dimensions, relation, "visual_candidate_review")
        if identity == "upscaled_recompressed":
            rows[-1]["best_original_oracle"] = "derived_not_better_original_merely_because_larger"

    add("orientation_6", _with_exif(original, orientation=6), (64, 48),
        "same_encoded_image_orientation_changed", "orientation_candidate_review", orientation=6)
    control = scratch / "control.bmp"
    control.write_bytes(_bmp(_pattern(control=True)))
    control_jpeg = scratch / "control.jpg"
    _run_sips(sips, "-s", "format", "jpeg", "-s", "formatOptions", "90",
              str(control), "--out", str(control_jpeg))
    add("different_photo_same_palette", _with_exif(control_jpeg.read_bytes()), (64, 48),
        "different_photo_same_name_date_palette", "distinct_keep")
    add("original_jpeg_extension", original, (64, 48), "exact_bytes_different_extension",
        "exact_present", basename="IMG_0001.JPEG")

    manifest = {
        "schema": 1, "seed": "asymmetric-geometric-pattern-v1", "files": rows,
        "capture_iso": CAPTURE_ISO, "reference_id": "original",
        "media_bytes": sum(row["size"] for row in rows),
        "encoder": {"tool": "existing macOS sips", "version": subprocess.run(
            [sips, "--version"], check=True, capture_output=True, text=True).stdout.strip()},
        "preserved_exif_subset": list(SHOT_TAGS),
        "policy": "Read-only scan always keeps files. Visual candidates never authorize cleanup.",
        "provenance": "Locally generated pixels; generic derivatives, no named service pipeline claim.",
    }
    (root / "expected.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return root, manifest


def inspect_variant_corpus(root: Path, manifest: dict) -> dict:
    """Observe this freshly generated corpus through current read-only RAWdog paths."""
    from rawdog import metadata
    from rawdog.inventory import scan_raw_files
    from rawdog.verifier import sha256_file

    scanned = scan_raw_files(root / "media")
    expected = {row["path"]: row for row in manifest["files"]}
    observations = []
    for item in scanned:
        relative = str(item.path.relative_to(root))
        capture = metadata.media_capture_time(item.path)
        observations.append({
            "path": relative, "sha256": sha256_file(item.path), "size": item.size_bytes,
            "mtime": item.path.stat().st_mtime,
            "embedded_capture_at": capture.isoformat() if capture else None,
            "hash_matches_seed": sha256_file(item.path) == expected[relative]["sha256"],
        })
    result = {"file_count": len(scanned), "metadata_reader_available": metadata.has_media_metadata_reader(),
              "observations": observations, "similarity_engine_exercised": False}
    (root / "observed.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 1:
        raise SystemExit("This generator accepts no paths or other arguments")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    corpus_root, expected_manifest = build_variant_corpus()
    observed_manifest = inspect_variant_corpus(corpus_root, expected_manifest)
    print(json.dumps({"root": str(corpus_root), "files": observed_manifest["file_count"],
                      "media_bytes": expected_manifest["media_bytes"]}, indent=2))
