# Author: Nicholas Corrieri

import os
from datetime import UTC, date, datetime
from pathlib import Path

from rawdog import cli, metadata
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.inventory import InventoryItem
from rawdog.models import DestinationFilenamePolicy, NamingConvention, OrganizationMode, StoreCreate, StoreKind
from rawdog.stores import create_or_update_store


def test_choose_path_accepts_direct_path_without_exiting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "standard_path_choices", lambda: [("Root", tmp_path)])
    monkeypatch.setattr(cli.Prompt, "ask", _answers(str(tmp_path / "RAW_YARD")))

    picked = cli._choose_path("Source")

    assert picked == (tmp_path / "RAW_YARD").resolve()


def test_home_choice_uses_letter_workflows_and_hides_init_under_manage() -> None:
    assert cli._normalize_home_choice("D") == "d"
    assert cli._normalize_home_choice("den") == "d"
    assert cli._normalize_home_choice("Y") == "y"
    assert cli._normalize_home_choice("yard") == "y"
    assert cli._normalize_home_choice("S") == "s"
    assert cli._normalize_home_choice("P") == "p"
    assert cli._normalize_home_choice("W") == "w"
    assert cli._normalize_home_choice("M") == "m"
    assert cli._normalize_home_choice("init") == "m"
    assert cli._normalize_home_choice("Q") == "q"
    assert cli._normalize_home_choice("DM") is None
    assert cli._normalize_home_choice("2") is None


def test_filename_policy_menu_accepts_numbered_choice(monkeypatch) -> None:
    monkeypatch.setattr(cli.Prompt, "ask", _answers("4"))

    policy = cli._prompt_filename_policy(
        "Default DEN File Names",
        default=DestinationFilenamePolicy.DATE_ORIGINAL,
    )

    assert policy == DestinationFilenamePolicy.ORIGINAL_HASH


def test_filename_policy_menu_accepts_policy_value(monkeypatch) -> None:
    monkeypatch.setattr(cli.Prompt, "ask", _answers("iuid-og"))

    policy = cli._prompt_filename_policy(
        "Default YARD Import File Names",
        default=DestinationFilenamePolicy.DATE_ORIGINAL,
    )

    assert policy == DestinationFilenamePolicy.UNIQUE_ID_ORIGINAL


def test_choose_path_can_browse_numbered_location(tmp_path: Path, monkeypatch) -> None:
    child = tmp_path / "Photos"
    child.mkdir()
    monkeypatch.setattr(cli, "standard_path_choices", lambda: [("Root", tmp_path)])
    monkeypatch.setattr(cli.Prompt, "ask", _answers("1", "1", "."))

    picked = cli._choose_path("Source", browse_number_selection=True)

    assert picked == child.resolve()


def test_choose_standard_root_accepts_browse_prefix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "standard_path_choices", lambda: [("Root", tmp_path)])
    monkeypatch.setattr(cli.Prompt, "ask", _answers("b1"))

    picked = cli._choose_standard_root("Source")

    assert picked == tmp_path.resolve()


def test_browse_folder_can_page_to_more_children(tmp_path: Path, monkeypatch) -> None:
    for index in range(7):
        child = tmp_path / f"folder-{index}"
        child.mkdir()
        (child / "file.raw").write_bytes(b"x" * (index + 1))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("7", "1", "9"))

    picked = cli._browse_folder(tmp_path, max_children=6)

    assert picked == (tmp_path / "folder-0").resolve()


def test_choose_store_path_lists_established_den_first(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    den_root = tmp_path / "archive"
    den_root.mkdir()
    initialize(database)
    with session(database) as connection:
        create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("1"))

    picked = cli._choose_store_path("Destination", StoreKind.DEN)

    assert picked == den_root.resolve()


def test_choose_audit_root_can_pick_registered_den(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    den_root = tmp_path / "archive"
    yard_root = tmp_path / "yard"
    den_root.mkdir()
    yard_root.mkdir()
    initialize(database)
    with session(database) as connection:
        create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
        create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=yard_root, store_kind=StoreKind.YARD),
        )
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("2", "1"))

    picked = cli._choose_audit_root("Audit")

    assert picked == den_root.resolve()


def test_choose_source_path_requires_existing_manual_path(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(cli, "_known_stores", lambda store_kind: [])
    monkeypatch.setattr(cli.Prompt, "ask", _answers("0", str(tmp_path / "missing"), "0", str(source)))

    picked = cli._choose_source_path("Source")

    assert picked == source.resolve()


def test_choose_den_destination_uses_default_and_can_create_missing_path(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "archive"
    database = tmp_path / "rawdog.sqlite"
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, archive_root=destination, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli, "_known_stores", lambda store_kind: [])
    monkeypatch.setattr(cli, "_yes_no", lambda question, default=False: True)
    monkeypatch.setattr(cli.Prompt, "ask", _answers("1"))

    picked = cli._choose_den_destination_path("Destination")

    assert picked == destination.resolve()
    assert destination.exists()


def test_choose_den_destination_uses_primary_registered_den_when_init_default_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    den_root = tmp_path / "RAW_DEN"
    den_root.mkdir()
    database = tmp_path / "rawdog.sqlite"
    initialize(database)
    with session(database) as connection:
        create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("1"))

    picked = cli._choose_den_destination_path("Destination")

    assert picked == den_root.resolve()


def test_confirm_store_registration_includes_selected_path(tmp_path: Path, monkeypatch) -> None:
    prompts: list[str] = []
    rows: list[str] = []

    def fake_yes_no(label: str, default: bool = False) -> bool:
        prompts.append(label)
        return default

    def fake_print_full_row(parts, *, style):
        rows.append("".join(value for value, _ in parts))

    monkeypatch.setattr(cli, "_yes_no", fake_yes_no)
    monkeypatch.setattr(cli, "_print_full_row", fake_print_full_row)

    result = cli._confirm_store_registration(tmp_path, StoreKind.DEN)

    assert result is True
    assert str(tmp_path.resolve()) in prompts[0]
    assert f"Selected archive den: {tmp_path.resolve()}" in rows[0]


def test_home_den_copy_uses_copy_den_planner(monkeypatch) -> None:
    calls: list[tuple[cli.DenTransferAction, bool]] = []

    monkeypatch.setattr(cli, "_print_copy_to_den_guidance", lambda: None)
    monkeypatch.setattr(
        cli,
        "_home_den",
        lambda action, show_guidance=True: calls.append((action, show_guidance)),
    )

    cli._home_den_copy()

    assert calls == [(cli.DenTransferAction.COPY, False)]


def test_preserve_dates_folder_review_defaults_keep_and_rejects_n(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    real_a = source / "Real Project" / "IMG_0001.CR3"
    real_b = source / "Real Project" / "IMG_0002.CR3"
    junk = source / "Probably Delete" / "IMG_0003.CR3"
    real_a.parent.mkdir(parents=True)
    junk.parent.mkdir(parents=True)
    real_a.write_bytes(b"raw")
    real_b.write_bytes(b"raw")
    junk.write_bytes(b"raw")
    defaults: list[str | None] = []
    answers = iter(["k", "n"])

    def fake_ask(*args, **kwargs) -> str:
        defaults.append(kwargs.get("default"))
        return next(answers)

    monkeypatch.setattr(cli.Prompt, "ask", fake_ask)

    drop_parts = cli._choose_preserve_dates_drop_parts(source, [])

    assert drop_parts == {"Probably Delete"}
    assert defaults == ["k", "k"]


def test_preserve_dates_folder_candidates_skip_pure_date_containers(tmp_path: Path) -> None:
    dated = tmp_path / "2026" / "2026-01" / "IMG_0001.CR3"
    camera = tmp_path / "Probably Delete" / "100CANON" / "IMG_0002.CR3"
    labeled = tmp_path / "2019-06-16 lacrosse" / "IMG_0003.CR3"
    dated.parent.mkdir(parents=True)
    camera.parent.mkdir(parents=True)
    labeled.parent.mkdir(parents=True)
    dated.write_bytes(b"raw")
    camera.write_bytes(b"raw")
    labeled.write_bytes(b"raw")

    candidates = cli._preserve_dates_folder_candidates(tmp_path, exclude_roots=[])

    assert [candidate.name for candidate in candidates] == [
        "2019-06-16 lacrosse",
        "Probably Delete",
    ]


def test_den_organization_report_flags_bad_den_shapes(tmp_path: Path) -> None:
    valid = tmp_path / "2024" / "2024-07" / "IMG_0001.CR3"
    valid_context = tmp_path / "2024" / "Project" / "2024-07" / "IMG_0002.CR3"
    double_year = tmp_path / "2024" / "2024" / "2024-07" / "IMG_0003.CR3"
    missing_bucket = tmp_path / "2024" / "IMG_0004.CR3"
    outside_year = tmp_path / "Loose Project" / "IMG_0005.CR3"
    for path in (valid, valid_context, double_year, missing_bucket, outside_year):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"raw")

    report = cli._build_den_organization_report(tmp_path)

    reasons = {(finding.relative_path.name, finding.reason) for finding in report.findings}
    assert ("IMG_0003.CR3", "double_year_folder") in reasons
    assert ("IMG_0004.CR3", "missing_date_bucket") in reasons
    assert ("IMG_0005.CR3", "outside_year_folder") in reasons
    assert report.valid_count == 2


def test_den_reflow_plan_can_convert_month_to_day_and_keep_context(tmp_path: Path) -> None:
    source = tmp_path / "2024" / "Project" / "2024-07" / "IMG_0001.CR3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"raw")
    captured_ts = datetime(2024, 7, 15, tzinfo=UTC).timestamp()
    os.utime(source, (captured_ts, captured_ts))

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.DAY,
        keep_context=True,
        drop_context=set(),
    )

    assert plan.rows[0].destination_path == tmp_path / "2024" / "Project" / "20240715" / "IMG_0001.CR3"
    assert plan.rows[0].status == "plan_copy"


def test_den_reflow_plan_checks_conflicts_before_moves(tmp_path: Path) -> None:
    source = tmp_path / "2024" / "2024-07" / "IMG_0001.CR3"
    destination = tmp_path / "2024" / "20240715" / "IMG_0001.CR3"
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"raw")
    destination.write_bytes(b"different")
    captured_ts = datetime(2024, 7, 15, tzinfo=UTC).timestamp()
    os.utime(source, (captured_ts, captured_ts))

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.DAY,
        keep_context=False,
        drop_context=set(),
    )

    row = next(row for row in plan.rows if row.source_path == source)
    assert row.destination_path == destination
    assert row.status == "collision"


def test_den_command_allows_registered_same_root_reflow_plan(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    den_root = tmp_path / "RAW_DEN"
    raw_file = den_root / "Probably Delete" / "100CANON" / "IMG_0001.CR3"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"raw")
    captured_ts = datetime(2025, 3, 15, tzinfo=UTC).timestamp()
    os.utime(raw_file, (captured_ts, captured_ts))
    initialize(database)
    with session(database) as connection:
        create_or_update_store(connection, StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN))
    config = build_config(OrganizationMode.PROJECT, archive_root=den_root, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))

    cli.den(
        source=den_root,
        destination=den_root,
        project_name=None,
        workflow_name=None,
        layout=cli.DenLayoutMode.PRESERVE_DATES,
        action=cli.DenTransferAction.MOVE,
        template="YYYY/YYYY-MM",
        group_by=None,
        start_date=None,
        end_date=None,
        limit=None,
        drop_preserved_folder=["Probably Delete"],
        reflow_den=True,
        dry_run=True,
    )

    with session(database) as connection:
        plan = cli.get_latest_execution_plan(connection)
        assert plan is not None
        rows = cli.list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].destination_path == den_root / "2025" / "2025-03" / "20250315-000000-00__IMG_0001.CR3"


def test_fetch_plan_ddd_flattens_camera_dump_into_destination_folder(tmp_path: Path) -> None:
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    destination_folder = destination / "2026" / "20260521_Date_Only"
    (source / "100EOSR7").mkdir(parents=True)
    destination.mkdir()
    raw_file = source / "100EOSR7" / "IMG_0001.CR3"
    raw_file.write_bytes(b"raw")

    plan = cli._build_fetch_plan(source, destination, destination_folder, NamingConvention.DDD)

    assert plan.files_to_transfer == 1
    assert plan.rows[0].destination_path == destination_folder / "IMG_0001.CR3"
    assert plan.rows[0].status == "plan_copy"


def test_fetch_plan_date_suffixes_flattened_camera_names(tmp_path: Path) -> None:
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    destination_folder = destination / "2026" / "2026-05"
    first = source / "101EOSR7" / "LS7A0001.CR3"
    second = source / "102EOSR7" / "LS7A0001.CR3"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    destination_folder.mkdir(parents=True)
    first.write_bytes(b"raw-one")
    second.write_bytes(b"raw-two")
    first_ts = datetime(2026, 5, 29, 12, 1, tzinfo=UTC).timestamp()
    second_ts = datetime(2026, 5, 29, 12, 2, tzinfo=UTC).timestamp()
    os.utime(first, (first_ts, first_ts))
    os.utime(second, (second_ts, second_ts))

    plan = cli._build_fetch_plan(
        source,
        destination,
        destination_folder,
        NamingConvention.DDD,
        DestinationFilenamePolicy.DATE_ORIGINAL,
    )

    assert [row.destination_path.name for row in plan.rows] == [
        "20260529-120100-00__LS7A0001.CR3",
        "20260529-120200-00__LS7A0001.CR3",
    ]
    assert [row.status for row in plan.rows] == ["plan_copy", "plan_copy"]


def test_fetch_plan_can_be_yard_move_plan(tmp_path: Path) -> None:
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    destination_folder = destination / "2026" / "2026-05"
    raw_file = source / "101EOSR7" / "LS7A0001.CR3"
    raw_file.parent.mkdir(parents=True)
    destination_folder.mkdir(parents=True)
    raw_file.write_bytes(b"raw")

    plan = cli._build_fetch_plan(
        source,
        destination,
        destination_folder,
        NamingConvention.DDD,
        transfer_action=cli.DenTransferAction.MOVE,
    )

    assert plan.transfer_action == cli.DenTransferAction.MOVE
    assert plan.rows[0].status == "plan_copy"


def test_fetch_plan_keep_existing_preserves_source_relative_path(tmp_path: Path) -> None:
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    (source / "100EOSR7").mkdir(parents=True)
    destination.mkdir()
    raw_file = source / "100EOSR7" / "IMG_0001.CR3"
    raw_file.write_bytes(b"raw")

    plan = cli._build_fetch_plan(source, destination, destination, NamingConvention.KEEP_EXISTING)

    assert plan.rows[0].destination_path == destination / "100EOSR7" / "IMG_0001.CR3"


def test_fetch_keep_existing_never_uses_project_date_only_folder_for_recovered_cr3(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "TestDisk_Recovered"
    destination = tmp_path / "RAW_YARD"
    raw_file = source / "101EOSR7" / "LS7A0001.CR3"
    raw_file.parent.mkdir(parents=True)
    destination.mkdir()
    raw_file.write_bytes(b"recovered cr3")
    project_ts = datetime(2025, 4, 5, tzinfo=UTC).timestamp()
    os.utime(raw_file, (project_ts, project_ts))
    monkeypatch.setattr(
        metadata,
        "_read_exiftool_tags_for_paths",
        lambda paths: {raw_file: {"DateTimeOriginal": "2026:05:28 13:40:00"}},
    )

    plan = cli._build_fetch_plan(source, destination, destination, NamingConvention.KEEP_EXISTING)

    assert plan.rows[0].destination_path == destination / "101EOSR7" / "LS7A0001.CR3"
    assert "Date_Only" not in plan.rows[0].destination_path.parts
    assert "20250405_Date_Only" not in plan.rows[0].destination_path.parts


def test_fetch_explicit_date_grouping_uses_media_date_not_project_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "TestDisk_Recovered"
    destination = tmp_path / "RAW_YARD"
    raw_file = source / "LS7A0001.CR3"
    source.mkdir()
    destination.mkdir()
    raw_file.write_bytes(b"recovered cr3")
    project_ts = datetime(2025, 4, 5, tzinfo=UTC).timestamp()
    os.utime(raw_file, (project_ts, project_ts))
    monkeypatch.setattr(
        metadata,
        "_read_exiftool_tags_for_paths",
        lambda paths: {raw_file: {"DateTimeOriginal": "2026:05:28 13:40:00"}},
    )
    destination_folder = cli.default_date_only_destination(
        destination,
        cli.earliest_raw_capture_time(source),
        "YYYY/YYYYMMDD_Date_Only",
    )

    plan = cli._build_fetch_plan(source, destination, destination_folder, NamingConvention.DDD)

    assert plan.rows[0].destination_path == destination / "2026" / "20260528_Date_Only" / "LS7A0001.CR3"
    assert "2025" not in plan.rows[0].destination_path.parts


def test_fetch_keep_existing_project_name_does_not_override_no_date_grouping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "rawdog.sqlite"
    source = tmp_path / "TestDisk_Recovered"
    destination = tmp_path / "RAW_YARD"
    raw_file = source / "101EOSR7" / "LS7A0001.CR3"
    raw_file.parent.mkdir(parents=True)
    destination.mkdir()
    raw_file.write_bytes(b"recovered cr3")
    project_ts = datetime(2025, 4, 5, tzinfo=UTC).timestamp()
    os.utime(raw_file, (project_ts, project_ts))
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli, "_prompt_dry_run_plan_next", lambda config, plan_id: None)
    monkeypatch.setattr(
        metadata,
        "_read_exiftool_tags_for_paths",
        lambda paths: {raw_file: {"DateTimeOriginal": "2026:05:28 13:40:00"}},
    )

    cli.fetch(
        source=source,
        destination=destination,
        profile=None,
        project_name="Date Only",
        profile_name=None,
        naming=NamingConvention.KEEP_EXISTING,
        filename_policy=DestinationFilenamePolicy.ORIGINAL,
        collision_policy=None,
        verify_after_copy=None,
        detect_sessions=False,
        action=cli.DenTransferAction.COPY,
        dry_run=True,
    )

    with session(database) as connection:
        plan = cli.get_latest_execution_plan(connection)
        assert plan is not None
        rows = cli.list_execution_plan_rows(connection, plan.plan_id)
    assert rows[0].destination_path == destination / "101EOSR7" / "LS7A0001.CR3"
    assert "20250405_Date_Only" not in rows[0].destination_path.parts


def test_yard_reflow_plan_can_date_suffix_flattened_files(tmp_path: Path) -> None:
    first = tmp_path / "LS7A0001.CR3"
    second = tmp_path / "101EOSR7" / "LS7A0001.CR3"
    second.parent.mkdir()
    first.write_bytes(b"raw-one")
    second.write_bytes(b"raw-two")
    first_ts = datetime(2026, 5, 29, 12, 1, tzinfo=UTC).timestamp()
    second_ts = datetime(2026, 5, 29, 12, 2, tzinfo=UTC).timestamp()
    os.utime(first, (first_ts, first_ts))
    os.utime(second, (second_ts, second_ts))

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.MONTH,
        keep_context=False,
        drop_context=set(),
        filename_policy=DestinationFilenamePolicy.DATE_ORIGINAL,
    )

    assert [row.destination_path for row in plan.rows] == [
        tmp_path / "2026" / "2026-05" / "20260529-120100-00__LS7A0001.CR3",
        tmp_path / "2026" / "2026-05" / "20260529-120200-00__LS7A0001.CR3",
    ]


def test_yard_reflow_plan_can_apply_time_shift(tmp_path: Path) -> None:
    source = tmp_path / "LS7A0001.CR3"
    source.write_bytes(b"raw")
    captured_ts = datetime(2026, 5, 29, 23, 30, tzinfo=UTC).timestamp()
    os.utime(source, (captured_ts, captured_ts))

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.DAY,
        keep_context=False,
        drop_context=set(),
        filename_policy=DestinationFilenamePolicy.DATE_ORIGINAL,
        time_shift=cli.timedelta(hours=1),
    )

    assert plan.rows[0].destination_path == tmp_path / "2026" / "20260530" / "20260530-003000-00__LS7A0001.CR3"


def test_reflow_time_shift_uses_existing_rawdog_filename_time(tmp_path: Path) -> None:
    source = tmp_path / "2026" / "2026-05" / "20260529-233000-00__LS7A0001.CR3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"raw")
    wrong_file_ts = datetime(2021, 1, 1, 1, 1, tzinfo=UTC).timestamp()
    os.utime(source, (wrong_file_ts, wrong_file_ts))

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.DAY,
        keep_context=False,
        drop_context=set(),
        filename_policy=DestinationFilenamePolicy.DATE_ORIGINAL,
        time_shift=cli.timedelta(hours=1),
    )

    assert plan.rows[0].destination_path == tmp_path / "2026" / "20260530" / "20260530-003000-00__LS7A0001.CR3"


def test_persisted_reflow_records_time_shift_rows_by_plan(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    source = tmp_path / "LS7A0001.CR3"
    source.write_bytes(b"raw")
    captured_ts = datetime(2026, 5, 29, 23, 30, tzinfo=UTC).timestamp()
    os.utime(source, (captured_ts, captured_ts))
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)

    plan = cli._build_den_reflow_plan(
        tmp_path,
        group_by=cli.DateGroupMode.DAY,
        keep_context=False,
        drop_context=set(),
        filename_policy=DestinationFilenamePolicy.DATE_ORIGINAL,
        time_shift=cli.timedelta(hours=1),
    )
    execution_plan = cli._persist_reflow_execution_plan(config, plan, store_kind=StoreKind.YARD)

    with session(database) as connection:
        operation_rows = cli.list_execution_plan_rows(connection, execution_plan.plan_id)
        time_shift_rows = cli.list_execution_plan_time_shift_rows(connection, execution_plan.plan_id)

    assert len(time_shift_rows) == 1
    assert time_shift_rows[0].plan_id == execution_plan.plan_id
    assert time_shift_rows[0].execution_row_id == operation_rows[0].row_id
    assert time_shift_rows[0].basis == "metadata_or_file_mtime"
    assert time_shift_rows[0].time_shift_seconds == 3600
    assert time_shift_rows[0].original_capture_at == datetime(2026, 5, 29, 23, 30, tzinfo=UTC)
    assert time_shift_rows[0].shifted_capture_at == datetime(2026, 5, 30, 0, 30, tzinfo=UTC)
    assert time_shift_rows[0].status == operation_rows[0].status

    cli._execute_persisted_plan(config, execution_plan.plan_id)

    with session(database) as connection:
        completed_time_shift_rows = cli.list_execution_plan_time_shift_rows(connection, execution_plan.plan_id)
    assert completed_time_shift_rows[0].status == "moved"
    assert completed_time_shift_rows[0].audit_status == "destination_verified"


def test_parse_time_shift_accepts_compound_offsets() -> None:
    assert cli._parse_time_shift("+1h30m") == cli.timedelta(hours=1, minutes=30)
    assert cli._parse_time_shift("-2d") == -cli.timedelta(days=2)


def test_setup_metadata_warning_can_install_exiftool_with_homebrew(monkeypatch) -> None:
    calls = []
    states = iter([False, True])
    monkeypatch.setattr(cli, "has_media_metadata_reader", lambda: next(states))
    monkeypatch.setattr(cli.sys, "stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    monkeypatch.setattr(cli, "_yes_no", lambda label, default=False: True)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)

    def fake_run(command, check=False):
        calls.append((command, check))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli._print_setup_metadata_reader_status()

    assert calls == [(["/opt/homebrew/bin/brew", "install", "exiftool"], False)]


def test_setup_metadata_warning_respects_declined_exiftool_install(monkeypatch) -> None:
    monkeypatch.setattr(cli, "has_media_metadata_reader", lambda: False)
    monkeypatch.setattr(cli.sys, "stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    monkeypatch.setattr(cli, "_yes_no", lambda label, default=False: False)

    def fail_run(command, check=False):
        raise AssertionError("brew should not run when install prompt is declined")

    monkeypatch.setattr(cli.subprocess, "run", fail_run)

    cli._print_setup_metadata_reader_status()


def test_fetch_commit_executes_persisted_copy_plan(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    destination_folder = destination / "2026" / "20260521_Date_Only"
    (source / "100EOSR7").mkdir(parents=True)
    destination.mkdir()
    raw_file = source / "100EOSR7" / "IMG_0001.CR3"
    raw_file.write_bytes(b"raw")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    plan = cli._build_fetch_plan(source, destination, destination_folder, NamingConvention.DDD)
    execution_plan = cli._persist_fetch_execution_plan(config, plan)

    finished = cli._execute_persisted_plan(config, execution_plan.plan_id)

    assert finished.status == cli.ExecutionPlanStatus.DONE
    assert (destination_folder / "IMG_0001.CR3").read_bytes() == b"raw"


def test_fetch_commit_can_execute_persisted_yard_move_plan(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    source = tmp_path / "DCIM"
    destination = tmp_path / "RAW_YARD"
    destination_folder = destination / "2026" / "20260521_Date_Only"
    (source / "100EOSR7").mkdir(parents=True)
    destination.mkdir()
    raw_file = source / "100EOSR7" / "IMG_0001.CR3"
    raw_file.write_bytes(b"raw")
    initialize(database)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    plan = cli._build_fetch_plan(
        source,
        destination,
        destination_folder,
        NamingConvention.DDD,
        transfer_action=cli.DenTransferAction.MOVE,
    )
    execution_plan = cli._persist_fetch_execution_plan(config, plan)

    finished = cli._execute_persisted_plan(config, execution_plan.plan_id)

    assert finished.status == cli.ExecutionPlanStatus.DONE
    assert not raw_file.exists()
    assert (destination_folder / "IMG_0001.CR3").read_bytes() == b"raw"


def test_browse_den_destination_can_select_known_den_under_current_path(tmp_path: Path, monkeypatch) -> None:
    den_root = tmp_path / "archive"
    den_root.mkdir()
    store = StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN)
    database = tmp_path / "rawdog.sqlite"
    initialize(database)
    with session(database) as connection:
        den = create_or_update_store(connection, store)
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("7", "1"))

    picked = cli._browse_den_destination(tmp_path, [den])

    assert picked == den_root.resolve()


def test_browse_den_destination_accepts_visible_den_shortcut(tmp_path: Path, monkeypatch) -> None:
    den_root = tmp_path / "RAW_DEN"
    den_root.mkdir()
    database = tmp_path / "rawdog.sqlite"
    initialize(database)
    with session(database) as connection:
        den = create_or_update_store(
            connection,
            StoreCreate(name="primary", root_path=den_root, store_kind=StoreKind.DEN),
        )
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli.Prompt, "ask", _answers("D1"))

    picked = cli._browse_den_destination(tmp_path, [den])

    assert picked == den_root.resolve()


def test_choose_source_path_paginates_registered_yards(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)
    with session(database) as connection:
        for index in range(7):
            root = tmp_path / f"yard-{index}"
            root.mkdir()
            create_or_update_store(
                connection,
                StoreCreate(name=f"yard-{index}", root_path=root, store_kind=StoreKind.YARD),
            )
        yards = [store for store in cli.list_stores(connection, StoreKind.YARD) if store.name != "primary"]
    config = build_config(OrganizationMode.PROJECT, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))
    monkeypatch.setattr(cli, "_known_stores", lambda store_kind: yards)
    monkeypatch.setattr(cli.Prompt, "ask", _answers("6", "1"))

    picked = cli._choose_source_path("Source")

    assert picked == yards[5].root_path


def test_known_stores_repairs_configured_working_root_kind(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "rawdog.sqlite"
    working_root = tmp_path / "RAW_YARD"
    working_root.mkdir()
    initialize(database)
    with session(database) as connection:
        create_or_update_store(
            connection,
            StoreCreate(name="RAW_YARD", root_path=working_root, store_kind=StoreKind.DEN),
        )
    config = build_config(OrganizationMode.PROJECT, working_root=working_root, database_path=database)
    monkeypatch.setattr(cli, "_load_or_exit", lambda: (tmp_path / "config.json", config))

    stores = cli._known_stores(StoreKind.YARD)

    assert [store.root_path for store in stores] == [working_root.resolve()]
    with session(database) as connection:
        den_rows = cli.list_stores(connection, StoreKind.DEN)
    assert den_rows == []


def test_parse_junkyard_before_accepts_cli_string_date_and_datetime() -> None:
    assert cli._parse_junkyard_before("2026-04-01") == datetime(2026, 4, 1, tzinfo=UTC)
    assert cli._parse_junkyard_before(date(2026, 4, 1)) == datetime(2026, 4, 1, tzinfo=UTC)
    assert cli._parse_junkyard_before(datetime(2026, 4, 1, 12, 30)) == datetime(
        2026,
        4,
        1,
        12,
        30,
        tzinfo=UTC,
    )


def test_read_junkyard_report_rows_accepts_tsv_report(tmp_path: Path) -> None:
    report = tmp_path / "junkyard.tsv"
    report.write_text(
        "yard_path\tmatched_den_path\tsize_bytes\n"
        "/yard/photo one.CR3\t/den/photo one.CR3\t123\n",
        encoding="utf-8",
    )

    assert cli._read_junkyard_report_rows(report) == [
        (Path("/yard/photo one.CR3"), Path("/den/photo one.CR3"), 123)
    ]


def test_path_is_under_any_requires_registered_root(tmp_path: Path) -> None:
    yard = tmp_path / "yard"
    outside = tmp_path / "outside"

    assert cli._path_is_under_any(yard / "photo.CR3", [yard])
    assert not cli._path_is_under_any(outside / "photo.CR3", [yard])


def test_file_matches_expected_size_requires_real_file(tmp_path: Path) -> None:
    photo = tmp_path / "photo.CR3"
    photo.write_bytes(b"raw")
    folder = tmp_path / "folder"
    folder.mkdir()

    assert cli._file_matches_expected_size(photo, 3)
    assert not cli._file_matches_expected_size(photo, 4)
    assert not cli._file_matches_expected_size(folder, 0)
    assert not cli._file_matches_expected_size(tmp_path / "missing.CR3", 3)


def test_duplicate_year_destination_paths_detects_adjacent_year_under_den() -> None:
    den = Path("/Volumes/Archive/RAW_DEN")
    bad = den / "2024" / "2024" / "IMG_0001.CR3"
    good = den / "2024" / "2024-05" / "IMG_0002.CR3"

    assert cli._duplicate_year_destination_paths([good, bad], destination_root=den) == [bad]


def test_duplicate_year_destination_paths_ignores_den_name_year_prefix() -> None:
    den = Path("/Volumes/Archive/2024")
    good = den / "2024" / "IMG_0001.CR3"

    assert cli._duplicate_year_destination_paths([good], destination_root=den) == []


def test_duplicate_name_groups_reports_repeated_filenames(tmp_path: Path) -> None:
    first = tmp_path / "a" / "IMG_0001.CR3"
    second = tmp_path / "b" / "IMG_0001.CR3"
    unique = tmp_path / "IMG_0002.CR3"
    first.parent.mkdir()
    second.parent.mkdir()
    items = [
        InventoryItem(first, Path("a/IMG_0001.CR3"), 10, 1),
        InventoryItem(second, Path("b/IMG_0001.CR3"), 10, 1),
        InventoryItem(unique, Path("IMG_0002.CR3"), 10, 1),
    ]

    groups = cli._duplicate_name_groups(items)

    assert groups == {"IMG_0001.CR3": [first, second]}


def test_camera_identity_groups_ignore_date_suffixes(tmp_path: Path) -> None:
    original = tmp_path / "LS7A0001.CR3"
    dated = tmp_path / "LS7A0001_20260529.CR3"
    timed = tmp_path / "LS7A0001_20260529_1202.CR3"
    date_first = tmp_path / "20260529-120200-00__LS7A0001.CR3"

    groups = cli._camera_identity_groups([original, dated, timed, date_first])

    assert groups == {"LS7A0001.CR3": [original, dated, timed, date_first]}


def _answers(*values: str):
    answers = iter(values)

    def fake_ask(*args, **kwargs) -> str:
        return next(answers)

    return fake_ask
