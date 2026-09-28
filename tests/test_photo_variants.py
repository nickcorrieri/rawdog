# Author: Nicholas Corrieri

import json
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from photo_variants import (
    CAPTURE_ISO,
    SHOT_TAGS,
    _strip_app_metadata,
    build_variant_corpus,
    inspect_variant_corpus,
)


@pytest.fixture(scope="module")
def corpus():
    if not shutil.which("sips"):
        pytest.skip("Real patterned JPEG encoding requires already installed macOS sips")
    return build_variant_corpus()


def _rows(manifest):
    return {row["id"]: row for row in manifest["files"]}


def _decode(path):
    # Decoder outputs stay in a new scratch directory, outside seed media.
    directory = Path(tempfile.mkdtemp(prefix="rawdog-jpeg-decode-"))
    bitmap = directory / "decoded.bmp"
    subprocess.run([shutil.which("sips"), "-s", "format", "bmp", str(path), "--out", str(bitmap)],
                   check=True, capture_output=True, timeout=30)
    data = bitmap.read_bytes()
    assert data[:2] == b"BM"
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    depth = struct.unpack_from("<H", data, 28)[0]
    assert depth in {24, 32}
    assert struct.unpack_from("<I", data, 30)[0] == 0
    stride = ((width * depth + 31) // 32) * 4
    rows = [data[offset + index * stride:offset + index * stride + width * (depth // 8)]
            for index in range(abs(height))]
    if height > 0:
        rows.reverse()
    return width, abs(height), b"".join(rows)


def test_small_fresh_complete_repeatable_corpus(corpus):
    root, manifest = corpus
    second_root, second_manifest = build_variant_corpus()
    assert root != second_root
    assert len(manifest["files"]) == 13
    assert manifest["media_bytes"] < 1_000_000
    assert [row["sha256"] for row in manifest["files"]] == [
        row["sha256"] for row in second_manifest["files"]]
    assert json.loads((root / "expected.json").read_text()) == manifest
    assert all(not row["scan_authorizes_removal"] for row in manifest["files"])


def test_exact_bytes_ignore_paths_extensions_and_filesystem_times(corpus):
    root, manifest = corpus
    rows = _rows(manifest)
    names = ["original", "exact_copy_working", "exact_copy_backup", "original_jpeg_extension"]
    assert len({rows[name]["sha256"] for name in names}) == 1
    assert len({rows[name]["mtime"] for name in names}) == 3
    for name in names:
        path = root / rows[name]["path"]
        assert path.stat().st_mtime == rows[name]["mtime"]
    assert rows["exact_copy_backup"]["role"] == "intentional_backup"


def test_real_decoder_verifies_dimensions_and_metadata_only_pixels(corpus):
    root, manifest = corpus
    rows = _rows(manifest)
    decoded = {}
    for identity, row in rows.items():
        decoded[identity] = _decode(root / row["path"])
        # sips applies EXIF orientation while decoding; stored dimensions remain separate.
        assert list(decoded[identity][:2]) == row["rendered_dimensions"]
    assert decoded["original"] == decoded["same_pixels_metadata_changed"]
    assert decoded["original"] == decoded["exif_stripped"]
    assert decoded["original"][2] != decoded["recompressed"][2]
    assert decoded["original"][2] != decoded["different_photo_same_palette"][2]
    # The negative control is patterned rather than a trivial solid colour.
    assert len(set(decoded["original"][2])) > 20


def test_same_basename_capture_metadata_does_not_prove_same_file(corpus):
    root, manifest = corpus
    rows = _rows(manifest)
    names = ["original", "reduced_recompressed", "different_photo_same_palette"]
    assert len({Path(rows[name]["path"]).name for name in names}) == 1
    assert all(rows[name]["capture_tags"] == SHOT_TAGS for name in names)
    assert len({rows[name]["sha256"] for name in names}) == 3
    assert rows["reduced_recompressed"]["dimensions"] == [32, 24]
    assert rows["reduced_recompressed"]["size"] < rows["original"]["size"]
    assert (root / rows["reduced_recompressed"]["path"]).stat().st_size < (
        root / rows["original"]["path"]).stat().st_size
    assert rows["different_photo_same_palette"]["expected_read_only_outcome"] == "distinct_keep"
    assert (root / rows["original"]["path"]).read_bytes() != (
        root / rows["reduced_recompressed"]["path"]).read_bytes()


def test_upscaled_derivative_is_not_a_better_original_by_dimensions(corpus):
    root, manifest = corpus
    rows = _rows(manifest)
    reference, upscaled = rows["original"], rows["upscaled_recompressed"]
    assert Path(reference["path"]).name == Path(upscaled["path"]).name
    assert reference["capture_tags"] == upscaled["capture_tags"] == SHOT_TAGS
    assert reference["sha256"] != upscaled["sha256"]
    reference_decoded = _decode(root / reference["path"])
    upscaled_decoded = _decode(root / upscaled["path"])
    assert upscaled_decoded[:2] == (128, 96)
    assert all(large > small for large, small in zip(upscaled_decoded[:2], reference_decoded[:2]))
    assert upscaled["known_seed_relation"] == "upscaled_recompressed_derivative"
    assert upscaled["best_original_oracle"] == "derived_not_better_original_merely_because_larger"
    assert upscaled["expected_read_only_outcome"] == "visual_candidate_review"
    assert not upscaled["scan_authorizes_removal"]


def test_orientation_is_metadata_relation_not_exact_identity(corpus):
    root, manifest = corpus
    rows = _rows(manifest)
    first = (root / rows["original"]["path"]).read_bytes()
    second = (root / rows["orientation_6"]["path"]).read_bytes()
    assert first != second
    assert _strip_app_metadata(first) == _strip_app_metadata(second)
    assert rows["orientation_6"]["orientation"] == 6
    assert rows["rotated_pixels"]["dimensions"] == [48, 64]


def test_actual_exif_capture_subset_and_stripping(corpus):
    if not shutil.which("exiftool"):
        pytest.skip("Real EXIF inspection requires already installed ExifTool")
    root, manifest = corpus
    rows = _rows(manifest)
    paths = [str(root / row["path"]) for row in manifest["files"]]
    result = subprocess.run([shutil.which("exiftool"), "-json", "-DateTimeOriginal",
                             "-OffsetTimeOriginal", "-SubSecTimeOriginal", "-Orientation#", *paths],
                            check=True, capture_output=True, text=True, timeout=30)
    tags = {Path(row["SourceFile"]).parent.name: row for row in json.loads(result.stdout)}
    for identity, row in rows.items():
        if row["metadata"] == "stripped":
            assert all(tag not in tags[identity] for tag in SHOT_TAGS)
        else:
            assert all(str(tags[identity][tag]) == value for tag, value in SHOT_TAGS.items())
            assert tags[identity]["Orientation"] == row["orientation"]


def test_current_rawdog_scan_is_read_only_and_labels_similarity_unimplemented(corpus):
    root, manifest = corpus
    before = {row["path"]: ((root / row["path"]).read_bytes(),
                            (root / row["path"]).stat().st_mtime_ns) for row in manifest["files"]}
    observed = inspect_variant_corpus(root, manifest)
    assert observed["file_count"] == 13
    assert not observed["similarity_engine_exercised"]
    assert all(row["hash_matches_seed"] for row in observed["observations"])
    for relative, previous in before.items():
        assert ((root / relative).read_bytes(), (root / relative).stat().st_mtime_ns) == previous
    if not observed["metadata_reader_available"]:
        pytest.skip("Capture metadata integration requires already installed ExifTool")
    for row in observed["observations"]:
        if "exif_stripped" in row["path"]:
            assert row["embedded_capture_at"] is None
        else:
            assert datetime.fromisoformat(row["embedded_capture_at"]) == datetime.fromisoformat(CAPTURE_ISO)
