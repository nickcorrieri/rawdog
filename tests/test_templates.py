# Author: Nicholas Corrieri

from datetime import datetime, timezone

from rawdog.planner import render_folder_template


def test_project_template_rendering() -> None:
    captured_at = datetime(2026, 5, 16, tzinfo=timezone.utc)

    rendered = render_folder_template("YYYY/YYYY-MM_PROJECT", captured_at)

    assert str(rendered) == "2026/2026-05_Date_Only"
