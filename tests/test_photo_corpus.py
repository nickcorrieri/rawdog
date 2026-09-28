# Author: Nicholas Corrieri

import json
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytest
from photo_corpus import CASES, FORMATS, build_corpus, inspect_corpus

from rawdog import cli, metadata
from rawdog.inventory import scan_raw_files
from rawdog.models import DateGroupMode
from rawdog.verifier import sha256_file


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return build_corpus(tmp_path_factory.mktemp("photo-corpus"))


@pytest.fixture(scope="module")
def observed(corpus):
    if not metadata.has_media_metadata_reader():
        pytest.skip("Real metadata integration requires an already installed ExifTool")
    root, manifest = corpus
    return inspect_corpus(root, manifest)


def test_corpus_is_small_complete_and_reproducible(corpus, tmp_path):
    root, manifest = corpus
    items = scan_raw_files(root / "media")
    assert len(items) == len(manifest["files"]) == 138
    assert sum(item.size_bytes for item in items) < 128_000
    assert {item.path.suffix.lstrip(".") for item in items} == set(FORMATS)
    assert max(item.size_bytes for item in items) < 2_000
    second_root, second = build_corpus(tmp_path)
    assert second_root != root
    assert [row["sha256"] for row in second["files"]] == [row["sha256"] for row in manifest["files"]]
    assert json.loads((root / "expected.json").read_text()) == manifest


def test_corpus_creation_and_modification_times_match_seed(corpus):
    root, manifest = corpus
    for row in manifest["files"]:
        stat = (root / row["path"]).stat()
        assert stat.st_mtime == pytest.approx(datetime.fromisoformat(row["mtime"]).timestamp(), abs=0.00001, rel=0)
        if row["birthtime_seeded"]:
            assert stat.st_birthtime == pytest.approx(datetime.fromisoformat(row["birth"]).timestamp(), abs=0.00001, rel=0)


def test_exact_copies_ignore_filesystem_times_but_keep_separate_roles(corpus):
    root, manifest = corpus
    groups = defaultdict(list)
    for row in manifest["files"]:
        groups[sha256_file(root / row["path"])].append(row)
    duplicates = [rows for rows in groups.values() if len(rows) > 1]
    assert len(duplicates) == 6
    for rows in duplicates:
        assert len(rows) == 4
        assert len({row["duplicate_group"] for row in rows}) == 1
        assert rows[0]["duplicate_group"] is not None
        assert len({row["mtime"] for row in rows}) == 4
        assert len({row["birth"] for row in rows}) == 4
        assert sorted(row["role"] for row in rows) == ["archive", "intentional_backup", "working", "working"]
        assert sum(row["protection"] == "protected" for row in rows) == 2


@pytest.mark.parametrize("extension", FORMATS)
def test_rollover_is_same_name_same_size_but_different_content(corpus, extension):
    root, manifest = corpus
    rows = [row for row in manifest["files"] if row["format"] == extension and row["id"].startswith("filename_rollover")]
    first, second = (root / row["path"] for row in rows)
    assert first.name == second.name
    assert first.stat().st_size == second.stat().st_size
    assert sha256_file(first) != sha256_file(second)
    assert all(row["action"] == "preserve_distinct_content" for row in rows)


def test_rawdog_reads_real_embedded_dates_without_reader_mocks(corpus, observed):
    _, manifest = corpus
    by_path = {row["path"]: row for row in observed["observations"]}
    assert observed["file_count"] == 138
    for expected in manifest["files"]:
        actual = by_path[expected["path"]]
        assert actual["sha256_matches_seed"]
        if expected["shot"] is None:
            assert actual["embedded_capture_at"] is None
        elif datetime.fromisoformat(expected["shot"]).tzinfo is not None:
            assert datetime.fromisoformat(actual["embedded_capture_at"]) == datetime.fromisoformat(expected["shot"])
        # Unknown timezones are deliberately not asserted as UTC: that is an open product gap.


def test_rawdog_filesystem_fallback_and_metadata_precedence(corpus, observed):
    root, manifest = corpus
    rows = [row for row in manifest["files"] if row["id"] in {"filesystem_owner_confirmed", "metadata_good_filesystem_wrong"}]
    paths = [root / row["path"] for row in rows]
    times = metadata.capture_times(paths)
    for row, path in zip(rows, paths):
        assert times[path] == datetime.fromisoformat(row["expected_shot"])


@pytest.mark.parametrize("case", [case for case in CASES if case.get("delta")], ids=lambda case: case["id"])
def test_explicit_owner_delta_produces_seeded_reflow_plan_without_mutation(corpus, observed, case):
    root, manifest = corpus
    source = root / "media" / case["id"]
    plan = cli._build_den_reflow_plan(
        source, group_by=DateGroupMode.MONTH, keep_context=False, drop_context=set(),
        time_shift=cli._parse_time_shift(case["delta"]),
    )
    expected = datetime.fromisoformat(case["expected_shot"])
    assert len(plan.rows) == len(FORMATS)
    assert len(plan.time_shift_rows) == len(FORMATS)
    for shift in plan.time_shift_rows:
        assert shift.shifted_capture_at == expected
        assert shift.destination_path.parent == source / f"{expected.year}" / expected.strftime("%Y-%m")
    for row in manifest["files"]:
        path = root / row["path"]
        assert sha256_file(path) == row["sha256"]
        assert path.stat().st_mtime == pytest.approx(datetime.fromisoformat(row["mtime"]).timestamp(), abs=0.00001, rel=0)
    assert not (source / "2024").exists()


def test_owner_scope_has_two_months_and_unaffected_controls(corpus):
    _, manifest = corpus
    selected = manifest["clock_correction_scope"]["selected_case_ids"]
    assert "camera_slow_12d2h_may" in selected
    assert "camera_slow_12d2h_july" in selected
    assert "camera_fixed_august_control" not in selected
    assert "different_camera_control" not in selected
    for row in manifest["files"]:
        if row["id"] in manifest["clock_correction_scope"]["exclude"]:
            assert row["action"] == "leave_unchanged"
            assert "delta" not in row


def test_fixture_unknowns_are_not_invented_capture_dates(corpus):
    _, manifest = corpus
    for row in manifest["files"]:
        if row["action"] in {"needs_owner_input", "needs_timezone", "retain_filesystem_candidate"}:
            assert row["expected_shot"] is None
            assert row["approved"] is False
    # These assertions validate the future oracle, not an implemented repair feature.
    assert all(row["future_behavior_implemented"] is False for row in manifest["files"])


def test_exiftool_recognizes_each_container_family(corpus, observed):
    root, manifest = corpus
    rows = [row for row in manifest["files"] if row["id"] == "metadata_good_filesystem_wrong"]
    result = subprocess.run(
        [shutil.which("exiftool"), "-j", "-FileType", "-Error", "-Warning", *[str(root / row["path"]) for row in rows]],
        capture_output=True, text=True, check=True, timeout=30,
    )
    records = json.loads(result.stdout)
    assert len(records) == len(FORMATS)
    for row, record in zip(rows, records):
        assert "Error" not in record
        assert "Warning" not in record
        assert record["FileType"] == ("JPEG" if row["format"] in {"jpg", "jpeg"} else row["format"])


def test_jpegs_decode_to_pixels(corpus, tmp_path):
    decoder = shutil.which("sips")
    if decoder is None:
        pytest.skip("Pixel decoding uses the existing macOS sips tool")
    root, manifest = corpus
    chosen = {"filesystem_plausible", "metadata_good_filesystem_wrong", "filename_rollover_1", "filename_rollover_2"}
    rows = [row for row in manifest["files"] if row["format"] == "jpg" and row["id"] in chosen]
    decoded = {}
    for row in rows:
        destination = tmp_path / f"{row['id']}.bmp"
        subprocess.run([decoder, "-s", "format", "bmp", str(root / row["path"]), "--out", str(destination)],
                       capture_output=True, check=True, timeout=30)
        data = destination.read_bytes()
        assert data[:2] == b"BM"
        assert len(data) > 64 * 3
        decoded[row["id"]] = data
    assert decoded["filename_rollover_1"] != decoded["filename_rollover_2"]


def test_generator_refuses_non_temporary_output():
    with pytest.raises(ValueError, match="OS temporary directory"):
        build_corpus(Path(__file__).resolve().parent)
