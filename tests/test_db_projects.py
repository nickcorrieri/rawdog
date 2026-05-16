# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import ProjectCreate
from rawdog.projects import create_project, list_projects


def test_create_and_list_project(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        project = create_project(
            connection,
            ProjectCreate(
                name="Wedding_Smith",
                client_name="Smith",
                tags=["wedding", "client"],
                location="Chicago",
            ),
        )

    with session(database) as connection:
        projects = list_projects(connection)

    assert project.project_id == projects[0].project_id
    assert projects[0].name == "Wedding_Smith"
    assert projects[0].folder_slug == "Wedding_Smith"
    assert projects[0].tags == ["wedding", "client"]
