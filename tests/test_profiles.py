# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import ImportProfileCreate, ProjectCreate
from rawdog.profiles import create_or_update_profile, get_last_profile, get_profile_by_name, list_profiles
from rawdog.projects import create_project


def test_create_update_and_list_profile(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        profile = create_or_update_profile(
            connection,
            ImportProfileCreate(
                name="Wedding_Smith",
                source_root=tmp_path / "card",
                destination_root=tmp_path / "external",
            ),
        )

    with session(database) as connection:
        loaded = get_profile_by_name(connection, "Wedding_Smith")
        last = get_last_profile(connection)
        profiles = list_profiles(connection)

    assert loaded is not None
    assert last is not None
    assert loaded.profile_id == profile.profile_id
    assert last.profile_id == profile.profile_id
    assert loaded.source_root == tmp_path / "card"
    assert loaded.destination_root == tmp_path / "external"
    assert profiles[0].name == "Wedding_Smith"


def test_profile_can_link_project_id(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        project = create_project(connection, ProjectCreate(name="Wedding_Smith"))
        profile = create_or_update_profile(
            connection,
            ImportProfileCreate(
                name="Wedding_Smith",
                source_root=tmp_path / "card",
                destination_root=tmp_path / "external",
                project_id=project.project_id,
            ),
        )

    assert profile.project_id == project.project_id
