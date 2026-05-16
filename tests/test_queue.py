# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.db import initialize, session
from rawdog.models import (
    DenLayoutMode,
    DenTransferAction,
    PlanQueueCreate,
    PlanQueueStepCreate,
    PlanStepKind,
)
from rawdog.queue import add_queue_step, create_or_update_queue, list_queue_steps


def test_create_queue_and_add_den_step(tmp_path: Path) -> None:
    database = tmp_path / "rawdog.sqlite"
    initialize(database)

    with session(database) as connection:
        queue = create_or_update_queue(connection, PlanQueueCreate(name="old_drive"))
        step = add_queue_step(
            connection,
            PlanQueueStepCreate(
                queue_id=queue.queue_id,
                step_order=1,
                step_kind=PlanStepKind.DEN,
                source_root=tmp_path / "old",
                destination_root=tmp_path / "archive",
                layout_mode=DenLayoutMode.PRESERVE,
                transfer_action=DenTransferAction.COPY,
            ),
        )

    with session(database) as connection:
        steps = list_queue_steps(connection, queue.queue_id)

    assert step.step_id == steps[0].step_id
    assert steps[0].transfer_action == DenTransferAction.COPY
