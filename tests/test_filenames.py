# Author: Nicholas Corrieri

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rawdog.filenames import destination_path_for_filename_policy, strip_capture_suffix
from rawdog.models import DestinationFilenamePolicy
from rawdog.safety import SafetyError


def test_strip_capture_suffix_removes_leftover_separator_from_date_only_suffix() -> None:
    assert strip_capture_suffix("20250412-152329-84__7P1A0233__20250412") == "7P1A0233"


def test_date_original_policy_does_not_leave_trailing_separator_for_video_names(tmp_path) -> None:
    source = tmp_path / "20250412-152329-84__7P1A0233__20250412.MP4"
    source.write_bytes(b"video")
    captured_at = datetime(2025, 4, 12, 15, 23, 29, 840000, tzinfo=UTC)

    destination = destination_path_for_filename_policy(
        source,
        tmp_path / "dest",
        captured_at,
        policy=DestinationFilenamePolicy.DATE_ORIGINAL,
        reserved_destinations=set(),
        size_bytes=source.stat().st_size,
    )

    assert destination.name == "20250412-152329-84__7P1A0233.MP4"


@pytest.mark.parametrize("candidate_stage", ["original", "initial", "numbered"])
@pytest.mark.parametrize("alias_kind", ["leaf", "parent", "broken-leaf", "broken-parent"])
def test_filename_chooser_refuses_alias_before_target_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate_stage: str, alias_kind: str,
) -> None:
    source = tmp_path / "source-dir" / "source.CR3"
    source.parent.mkdir()
    source.write_bytes(b"original")
    destination_dir = tmp_path / "archive" / "nested"
    destination_dir.parent.mkdir()
    captured_at = datetime(2025, 4, 12, 15, 23, 29, 840000, tzinfo=UTC)
    policy = DestinationFilenamePolicy.DATE_ORIGINAL
    reserved: set[Path] = set()
    first_name = "20250412-152329-84__source.CR3"
    second_name = "20250412-152329-84__source__source-dir.CR3"
    if candidate_stage == "original":
        policy = DestinationFilenamePolicy.ORIGINAL
        candidate = destination_dir / source.name
    elif candidate_stage == "numbered":
        reserved = {destination_dir / first_name, destination_dir / second_name}
        candidate = destination_dir / "20250412-152329-84__source__source-dir__02.CR3"
    else:
        candidate = destination_dir / first_name
    target_dir = tmp_path / "targets"
    target = target_dir / candidate.name
    broken = alias_kind.startswith("broken-")
    if not broken:
        target_dir.mkdir()
        target.write_bytes(b"foreign!")
    if alias_kind.endswith("parent"):
        destination_dir.symlink_to(target_dir, target_is_directory=True)
    else:
        destination_dir.mkdir()
        candidate.symlink_to(target)

    real_stat, real_open = os.stat, Path.open
    guarded_paths = {candidate, target}

    def refuse_target_stat(path, *args, **kwargs):
        if (not isinstance(path, int) and Path(path) in guarded_paths
                and kwargs.get("follow_symlinks", True)):
            raise AssertionError("filename chooser followed the candidate alias for metadata")
        return real_stat(path, *args, **kwargs)

    def refuse_target_open(path, *args, **kwargs):
        if path in guarded_paths:
            raise AssertionError("filename chooser opened the candidate alias or target")
        return real_open(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "stat", refuse_target_stat)
        scoped.setattr(Path, "open", refuse_target_open)
        with pytest.raises(SafetyError, match="symlink"):
            destination_path_for_filename_policy(
                source, destination_dir, captured_at, policy=policy,
                reserved_destinations=reserved, size_bytes=len(b"original"),
            )

    assert source.read_bytes() == b"original"
    if broken:
        assert not target.exists()
    else:
        assert target.read_bytes() == b"foreign!"
