# Author: Nicholas Corrieri

from pathlib import Path

from rawdog import cli
from rawdog.config import build_config
from rawdog.db import initialize, session
from rawdog.models import OrganizationMode, StoreCreate, StoreKind
from rawdog.stores import create_or_update_store


def test_choose_path_accepts_direct_path_without_exiting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "standard_path_choices", lambda: [("Root", tmp_path)])
    monkeypatch.setattr(cli.Prompt, "ask", _answers(str(tmp_path / "RAW_YARD")))

    picked = cli._choose_path("Source")

    assert picked == (tmp_path / "RAW_YARD").resolve()


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


def _answers(*values: str):
    answers = iter(values)

    def fake_ask(*args, **kwargs) -> str:
        return next(answers)

    return fake_ask
