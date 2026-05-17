# Author: Nicholas Corrieri

from datetime import datetime, timezone

import pytest

from rawdog.planner import (
    TemplateError,
    default_project_destination,
    plan_append_only_copy,
    render_folder_template,
    slug_folder_name,
)


def test_project_template_rendering() -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=timezone.utc)

    rendered = render_folder_template("YYYY/YYYYMMDD_PROJECT", captured_at)

    assert str(rendered) == "2026/20260516_Date_Only"


def test_project_destination_uses_sanitized_project_name(tmp_path) -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=timezone.utc)

    rendered = default_project_destination(tmp_path, "Senior Photos Emma", captured_at)

    assert rendered == tmp_path / "2026" / "20260516_Senior_Photos_Emma"


def test_slug_folder_name_handles_custom_project_names() -> None:
    assert slug_folder_name(" Nike Summer Campaign ") == "Nike_Summer_Campaign"


def test_slug_folder_name_deduplicates_separator_runs() -> None:
    assert slug_folder_name("foo...bar---baz___qux") == "foo.bar-baz_qux"


def test_template_cannot_escape_destination() -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=timezone.utc)

    with pytest.raises(TemplateError):
        render_folder_template("../YYYY", captured_at)


def test_plan_append_only_copy_reports_size_mismatch(tmp_path) -> None:
    source = tmp_path / "source.CR3"
    destination = tmp_path / "destination.CR3"
    source.write_bytes(b"raw")
    destination.write_bytes(b"different")

    plan = plan_append_only_copy(source, destination)

    assert plan is not None
    assert plan.reason == "collision_size_mismatch"
