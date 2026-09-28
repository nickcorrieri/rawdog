"""Generate known companion/storage fixtures, never accept a user-library path.

RAW payloads are metadata containers from photo_corpus, not camera decoder samples.
Expected relationships and actions are seed inputs, not inferred product results.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from photo_corpus import media_bytes

SHOT_A = "2024-05-20T10:30:00.125000-05:00"
SHOT_B = "2024-07-20T10:30:00.125000-05:00"
MTIME = "2024-05-20T15:30:00+00:00"


def xmp_bytes(rating: int, label: str) -> bytes:
    """A real XML/XMP packet with deliberate, independent edit versions."""
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" '
        f'xmp:Rating="{rating}" xmp:Label="{label}" crs:Exposure2012="0.50"/>'
        '</rdf:RDF></x:xmpmeta>\n'
    ).encode()


def build_companion_corpus() -> tuple[Path, dict]:
    """Allocate a fresh OS temporary directory; no path arguments or cleanup."""
    root = Path(tempfile.mkdtemp(prefix="rawdog-photo-companions-")).resolve()
    (root / ".rawdog-synthetic-companions").write_text("Owned generated fixture files only.\n")
    records = []

    def seed(identifier: str, relative: str, payload: bytes, *, scanned: bool,
             coverage: str, future: str, role: str = "working", **extra) -> None:
        path = root / "media" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(payload)
        instant = datetime.fromisoformat(MTIME).timestamp()
        os.utime(path, (instant, instant))
        records.append({
            "id": identifier, "path": "media/" + relative,
            "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "mtime": MTIME, "coverage": coverage, "role": role,
            "expected_current_scan_included": scanned, "required_future_action": future,
            "future_behavior_implemented": False, **extra,
        })

    raw_a = media_bytes("CR2", SHOT_A, "bundle-a", "BODY-A")
    jpeg_a = media_bytes("jpg", SHOT_A, "bundle-a", "BODY-A")
    for identifier, extension, payload, coverage in (
        ("bundle_raw", "CR2", raw_a, "synthetic_raw_metadata_container"),
        ("bundle_jpeg", "jpg", jpeg_a, "decodable_jpeg"),
        ("bundle_xmp", "xmp", xmp_bytes(2, "Baseline"), "xmp_xml"),
    ):
        seed(identifier, f"shoot_a/IMG_0001.{extension}", payload,
             scanned=extension != "xmp", coverage=coverage, future="preserve_bundle_member",
             capture_id="shoot-a-body-a", body="BODY-A", shot=SHOT_A)
    for identifier, rating, label in (("xmp_edit_one", 4, "Select"), ("xmp_edit_two", 5, "Final")):
        seed(identifier, f"{identifier}/IMG_0001.xmp", xmp_bytes(rating, label), scanned=False,
             coverage="xmp_xml", future="preserve_divergent_sidecar_version",
             capture_id="shoot-a-body-a", expected_rating=rating)
    for shoot, shot, body in (("shoot_b", SHOT_B, "BODY-A"), ("other_body", SHOT_A, "BODY-B")):
        for extension in ("CR2", "jpg"):
            seed(f"{shoot}_{extension}", f"{shoot}/IMG_0001.{extension}",
                 media_bytes(extension, shot, shoot, body), scanned=True,
                 coverage="decodable_jpeg" if extension == "jpg" else "synthetic_raw_metadata_container",
                 future="preserve_distinct_capture", capture_id=shoot, body=body, shot=shot)

    # Separate source directories remain representable on case-insensitive and
    # normalization-insensitive filesystems. Only planned targets conflict.
    for identifier, name in (("case_lower", "IMG_0001.jpg"), ("case_upper", "IMG_0001.JPG"),
                             ("unicode_nfc", "Caf\u00e9.jpg"), ("unicode_nfd", "Cafe\u0301.jpg")):
        seed(identifier, f"{identifier}/{name}", media_bytes("jpg", SHOT_A, identifier),
             scanned=True, coverage="decodable_jpeg", future="hold_destination_name_conflict")

    appledouble = struct.pack(">II16sH", 0x00051607, 0x00020000, bytes(16), 0)
    seed("appledouble", "shoot_a/._IMG_0001.CR2", appledouble, scanned=False,
         coverage="appledouble_header_only", future="classify_filesystem_companion_not_capture")
    seed("appledouble_jpeg", "shoot_a/._IMG_0001.jpg", appledouble, scanned=False,
         coverage="appledouble_header_only", future="classify_filesystem_companion_not_capture")
    seed("partial_complete", "interrupted/IMG_0001.CR2.partial", raw_a, scanned=False,
         coverage="complete_bytes_in_partial_name", future="review_partial_no_automatic_promotion")
    seed("partial_truncated", "interrupted/IMG_0002.jpg.partial", jpeg_a[:96], scanned=False,
         coverage="truncated_partial", future="review_partial_not_capture_or_cleanup_proof")

    for identifier, name, payload in (
        ("zero_jpeg", "empty.jpg", b""), ("zero_raw", "empty.CR2", b""),
        ("truncated_jpeg", "broken.jpg", b"\xff\xd8\xff\xe1\x00\x20Exif\0\0"),
        ("truncated_raw", "broken.CR2", b"II*\0\x10\0\0\0CR\x02\0"),
    ):
        seed(identifier, f"malformed/{name}", payload, scanned=True,
             coverage="deliberately_malformed", future="retain_and_flag_invalid_no_valid_media_claim")
    seed("raw_named_jpeg", "mismatched/RAW_BYTES.jpg", raw_a, scanned=True,
         coverage="extension_container_mismatch", future="flag_extension_mismatch_preserve_bytes",
         actual_container="synthetic_CR2_metadata_container")
    seed("jpeg_named_raw", "mismatched/JPEG_BYTES.CR2", jpeg_a, scanned=True,
         coverage="extension_container_mismatch", future="flag_extension_mismatch_preserve_bytes",
         actual_container="JPEG")

    for identifier, role, protection in (
        ("archive_copy", "primary_archive", "protected"),
        ("backup_copy", "intentional_backup", "protected"),
        ("working_copy", "working", "review_only"),
    ):
        seed(identifier, f"stores/{identifier}/IMG_0001.CR2", raw_a, scanned=True,
             coverage="synthetic_raw_metadata_container", future="preserve_protected_copy" if protection == "protected" else "review_exact_duplicate",
             role=role, protection=protection, capture_id="shoot-a-body-a")

    manifest = {
        "schema_version": 1, "synthetic": True,
        "scope": "Companion and storage fixtures; expected actions are future requirements.",
        "raw_limit": "Metadata containers only; no vendor sensor decoding or safe RAW rewrite proof.",
        "files": records,
        "expected_bundles": [
            {"capture_id": "shoot-a-body-a", "members": ["bundle_raw", "bundle_jpeg", "bundle_xmp"],
             "relation": "representations_and_sidecar_not_byte_duplicates"},
            {"capture_id": "shoot_b", "members": ["shoot_b_CR2", "shoot_b_jpg"], "relation": "distinct_shoot"},
            {"capture_id": "other_body", "members": ["other_body_CR2", "other_body_jpg"], "relation": "distinct_camera"},
        ],
        "divergent_sidecars": {"members": ["bundle_xmp", "xmp_edit_one", "xmp_edit_two"],
                               "action": "preserve_all_versions_no_automatic_winner"},
        "expected_same_bytes": ["bundle_raw", "raw_named_jpeg", "partial_complete", "archive_copy", "backup_copy", "working_copy"],
        "same_bytes_is_not_cleanup_permission": True,
        "planned_destination_conflicts": [
            {"members": ["case_lower", "case_upper"], "targets": ["2024/IMG_0001.jpg", "2024/IMG_0001.JPG"],
             "comparison": "casefold", "action": "hold_for_review"},
            {"members": ["unicode_nfc", "unicode_nfd"], "targets": ["2024/Caf\u00e9.jpg", "2024/Cafe\u0301.jpg"],
             "comparison": "unicode_nfc", "action": "hold_for_review"},
        ],
        "logical_locations": [
            {"id": "offline-backup", "role": "intentional_backup", "state": "offline",
             "observed_now": False, "last_known_content_file_id": "bundle_raw", "last_known_relative_path": "2024/IMG_0001.CR2",
             "action": "retain_offline_record_do_not_mark_missing_or_count_as_verified_keeper"},
        ],
        "storage_scope": "Store roles and offline state are manifest facts, not real mounts or registered stores.",
    }
    (root / "expected.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")
    return root, manifest


def inspect_companion_corpus(root: Path, manifest: dict) -> dict:
    """Read-only scan/hash of a generated fixture, not a bundle classifier."""
    from rawdog.inventory import scan_raw_files
    from rawdog.verifier import sha256_file

    if not (root / ".rawdog-synthetic-companions").is_file():
        raise ValueError("Not a generated companion corpus")
    scanned = {str(item.relative_path) for item in scan_raw_files(root / "media")}
    observations = []
    for row in manifest["files"]:
        relative = Path(row["path"])
        path = root / relative
        if relative.is_absolute() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Fixture manifest path escapes corpus")
        observations.append({
            "id": row["id"], "path": row["path"], "sha256": sha256_file(path),
            "scan_included": str(relative.relative_to("media")) in scanned,
            "size_bytes": path.stat().st_size,
        })
    return {"file_count": len(observations), "scan_count": len(scanned),
            "media_bytes": sum(row["size_bytes"] for row in observations), "observations": observations,
            "limitation": "Scan inclusion is not media validation, bundle association, or cleanup permission."}


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("No path arguments accepted; always generates a fresh temporary corpus.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    corpus_root, expected = build_companion_corpus()
    observed = inspect_companion_corpus(corpus_root, expected)
    (corpus_root / "observed.json").write_text(json.dumps(observed, indent=2) + "\n")
    print(json.dumps({"root": str(corpus_root), **{key: observed[key] for key in ("file_count", "scan_count", "media_bytes")}}, indent=2))
