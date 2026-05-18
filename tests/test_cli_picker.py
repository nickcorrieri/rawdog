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


def _answers(*values: str):
    answers = iter(values)

    def fake_ask(*args, **kwargs) -> str:
        return next(answers)

    return fake_ask
