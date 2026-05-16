# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import ConsolidationWorkflowCreate, DenLayoutMode
from rawdog.workflows import create_or_update_workflow, get_workflow_by_name, list_workflows


def test_create_and_list_consolidation_workflow(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        workflow = create_or_update_workflow(
            connection,
            ConsolidationWorkflowCreate(
                name="old_drive_cleanup",
                source_root=tmp_path / "old",
                destination_root=tmp_path / "archive",
                layout_mode=DenLayoutMode.PRESERVE,
            ),
        )

    with session(database) as connection:
        loaded = get_workflow_by_name(connection, "old_drive_cleanup")
        workflows = list_workflows(connection)

    assert loaded is not None
    assert loaded.workflow_id == workflow.workflow_id
    assert loaded.layout_mode == DenLayoutMode.PRESERVE
    assert workflows[0].name == "old_drive_cleanup"
