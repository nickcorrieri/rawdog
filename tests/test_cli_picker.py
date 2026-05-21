# Author: Nicholas Corrieri

from datetime import UTC, date, datetime
from pathlib import Path

from rawdog import cli
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.inventory import InventoryItem
from rawdog.models import OrganizationMode, StoreCreate, StoreKind
from rawdog.stores import create_or_update_store


def test_choose_path_accepts_direct_path_without_exiting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "standard_path_choices", lambda: [("Root", tmp_path)])
    monkeypatch.setattr(cli.Prompt, "ask", _answers(str(tmp_path / "RAW_YARD")))

    picked = cli._choose_path("Source")

    assert picked == (tmp_path / "RAW_YARD").resolve()


def test_home_choice_uses_letter_workflows_and_hides_init_under_manage() -> None:
    assert cli._normalize_home_choice("F") == "f"
    assert cli._normalize_home_choice("DC") == "dc"
    assert cli._normalize_home_choice("DM") == "dm"
    assert cli._normalize_home_choice("J") == "j"
    assert cli._normalize_home_choice("S") == "s"
    assert cli._normalize_home_choice("P") == "p"
    assert cli._normalize_home_choice("W") == "w"
    assert cli._normalize_home_choice("M") == "m"
    assert cli._normalize_home_choice("init") == "m"
    assert cli._normalize_home_choice("Q") == "q"
    assert cli._normalize_home_choice("2") is None


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


def test_home_backup_uses_copy_den_planner(monkeypatch) -> None:
    calls: list[tuple[cli.DenTransferAction, bool]] = []

    monkeypatch.setattr(cli, "_print_copy_to_den_guidance", lambda: None)
    monkeypatch.setattr(
        cli,
        "_home_den",
        lambda action, show_guidance=True: calls.append((action, show_guidance)),
    )

    cli._home_backup()

    assert calls == [(cli.DenTransferAction.COPY, False)]


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


def _answers(*values: str):
    answers = iter(values)

    def fake_ask(*args, **kwargs) -> str:
        return next(answers)

    return fake_ask
