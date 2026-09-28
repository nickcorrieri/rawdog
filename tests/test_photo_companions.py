"""Verify fixture facts independently; future policy is not implementation proof."""

import hashlib
import json
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest
from photo_companions import build_companion_corpus, inspect_companion_corpus


@pytest.fixture(scope="module")
def corpus():
    return build_companion_corpus()


def test_small_deterministic_corpus_with_literal_expected_scan_results(corpus):
    root, manifest = corpus
    observed = inspect_companion_corpus(root, manifest)
    assert observed["file_count"] == 26
    assert observed["scan_count"] == 19
    assert observed["media_bytes"] < 100_000
    assert json.loads((root / "expected.json").read_text()) == manifest
    for expected, actual in zip(manifest["files"], observed["observations"], strict=True):
        assert actual["scan_included"] == expected["expected_current_scan_included"]
        assert actual["sha256"] == expected["sha256"]
        assert actual["size_bytes"] == expected["size_bytes"]
        assert (root / expected["path"]).stat().st_mtime == datetime.fromisoformat(expected["mtime"]).timestamp()
    second_root, second_manifest = build_companion_corpus()
    assert second_root != root
    assert second_manifest == manifest


def test_xmp_versions_are_valid_distinct_packets_not_discardable_duplicates(corpus):
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    observed_ratings = []
    digests = []
    for identifier in ("bundle_xmp", "xmp_edit_one", "xmp_edit_two"):
        payload = (root / rows[identifier]["path"]).read_bytes()
        tree = ElementTree.fromstring(payload)
        description = tree.find(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description")
        assert description is not None
        observed_ratings.append(description.attrib["{http://ns.adobe.com/xap/1.0/}Rating"])
        digests.append(hashlib.sha256(payload).hexdigest())
    assert observed_ratings == ["2", "4", "5"]
    assert len(set(digests)) == 3
    assert manifest["divergent_sidecars"]["action"] == "preserve_all_versions_no_automatic_winner"


def test_context_keeps_reused_names_and_raw_jpeg_representations_distinct(corpus):
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    raw_ids = ("bundle_raw", "shoot_b_CR2", "other_body_CR2")
    assert {Path(rows[key]["path"]).name for key in raw_ids} == {"IMG_0001.CR2"}
    assert len({rows[key]["sha256"] for key in raw_ids}) == 3
    assert rows["bundle_raw"]["sha256"] != rows["bundle_jpeg"]["sha256"]
    assert len(manifest["expected_bundles"]) == 3
    assert all(row["future_behavior_implemented"] is False for row in manifest["files"])
    assert (root / rows["bundle_raw"]["path"]).read_bytes().startswith(b"II*\0")
    assert (root / rows["bundle_jpeg"]["path"]).read_bytes().startswith(b"\xff\xd8")


def test_case_and_unicode_conflicts_exist_only_in_planned_destinations(corpus):
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    for conflict in manifest["planned_destination_conflicts"]:
        first, second = conflict["targets"]
        assert first != second
        normalize = str.casefold if conflict["comparison"] == "casefold" else lambda value: unicodedata.normalize("NFC", value)
        assert normalize(first) == normalize(second)
        paths = [root / rows[key]["path"] for key in conflict["members"]]
        assert paths[0].parent != paths[1].parent
        assert all(path.is_file() for path in paths)
        assert paths[0].read_bytes() != paths[1].read_bytes()
        assert not (root / first).exists()
        assert not (root / second).exists()


def test_malformed_mismatched_and_partial_inputs_are_not_validity_claims(corpus):
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    observed = {row["id"]: row for row in inspect_companion_corpus(root, manifest)["observations"]}
    for key in ("zero_jpeg", "zero_raw"):
        assert (root / rows[key]["path"]).read_bytes() == b""
        assert observed[key]["scan_included"]  # Documents current extension-only recognition.
    assert not (root / rows["truncated_jpeg"]["path"]).read_bytes().endswith(b"\xff\xd9")
    assert (root / rows["truncated_raw"]["path"]).stat().st_size == 12
    assert (root / rows["raw_named_jpeg"]["path"]).read_bytes().startswith(b"II*\0")
    assert (root / rows["jpeg_named_raw"]["path"]).read_bytes().startswith(b"\xff\xd8")
    for key in ("partial_complete", "partial_truncated", "appledouble", "appledouble_jpeg"):
        assert not observed[key]["scan_included"]
    assert (root / rows["appledouble"]["path"]).read_bytes()[:4] == b"\0\x05\x16\x07"


def test_equal_bytes_keep_roles_partial_state_and_offline_uncertainty(corpus):
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    digests = {hashlib.sha256((root / rows[key]["path"]).read_bytes()).hexdigest()
               for key in manifest["expected_same_bytes"]}
    assert len(digests) == 1
    assert rows["archive_copy"]["protection"] == rows["backup_copy"]["protection"] == "protected"
    assert rows["working_copy"]["protection"] == "review_only"
    assert rows["partial_complete"]["required_future_action"] == "review_partial_no_automatic_promotion"
    offline = manifest["logical_locations"][0]
    assert offline["state"] == "offline" and offline["observed_now"] is False
    assert "path" not in offline and "root_path" not in offline
    assert not (root / "offline-backup").exists()


def test_real_metadata_reader_sees_contextual_camera_and_date_differences(corpus):
    executable = shutil.which("exiftool")
    if executable is None:
        pytest.skip("Requires already installed ExifTool; no install attempted")
    root, manifest = corpus
    rows = {row["id"]: row for row in manifest["files"]}
    keys = ("bundle_raw", "shoot_b_CR2", "other_body_CR2")
    result = subprocess.run(
        [executable, "-j", "-SerialNumber", "-DateTimeOriginal", "-FileType",
         *[str(root / rows[key]["path"]) for key in keys]],
        capture_output=True, text=True, check=True, timeout=30,
    )
    actual = json.loads(result.stdout)
    assert [row["SerialNumber"] for row in actual] == ["BODY-A", "BODY-A", "BODY-B"]
    assert [row["DateTimeOriginal"] for row in actual] == ["2024:05:20 10:30:00", "2024:07:20 10:30:00", "2024:05:20 10:30:00"]
    assert [row["FileType"] for row in actual] == ["CR2", "CR2", "CR2"]


def test_cli_refuses_path_arguments_before_generating(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("photo_companions.py")), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "No path arguments accepted" in result.stderr
    assert list(tmp_path.iterdir()) == []
