# Author: Nicholas Corrieri

from datetime import UTC, datetime

from rawdog.memory import (
    build_destination_memory,
    memory_file_for_destination,
    write_destination_memory,
)
from rawdog.models import OrganizationMode
from rawdog.planner import default_date_only_destination


def test_memory_file_lives_inside_destination_folder(tmp_path) -> None:
    destination = tmp_path / "2026" / "20260516_Wedding_Smith"

    assert memory_file_for_destination(destination) == destination / ".rawdog" / "project.json"


def test_date_only_destination_uses_year_month(tmp_path) -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=UTC)

    assert default_date_only_destination(tmp_path, captured_at) == tmp_path / "2026" / "2026-05"


def test_date_only_destination_respects_template(tmp_path) -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=UTC)

    assert default_date_only_destination(tmp_path, captured_at, "YYYY/MM") == tmp_path / "2026" / "05"


def test_destination_memory_keeps_project_optional(tmp_path) -> None:
    memory = build_destination_memory(
        organization_mode=OrganizationMode.DATE,
        source_root=tmp_path / "card",
        destination_root=tmp_path / "dest",
        destination_folder=tmp_path / "dest" / "2026" / "2026-05",
        folder_template="YYYY/YYYY-MM",
    )

    assert memory.project_name is None
    assert memory.memory_name == "Date_Only"
    assert memory.rawdog_version == "0.2.3"


def test_destination_memory_writes_on_commit(tmp_path) -> None:
    destination_folder = tmp_path / "dest" / "2026" / "2026-05"
    memory = build_destination_memory(
        organization_mode=OrganizationMode.DATE,
        source_root=tmp_path / "card",
        destination_root=tmp_path / "dest",
        destination_folder=destination_folder,
        folder_template="YYYY/YYYY-MM",
    )

    path = write_destination_memory(memory, dry_run=False)

    assert path.exists()
    assert path == destination_folder / ".rawdog" / "project.json"
