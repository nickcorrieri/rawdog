# Author: Nicholas Corrieri

from pathlib import Path

from rawdog.cli import _operation_manifest_row
from rawdog.models import DenTransferAction, ExecutionPlanRow
from rawdog.reports import write_operation_manifest


def test_operation_manifest_documents_copy_python_apis(tmp_path: Path) -> None:
    row = ExecutionPlanRow(
        row_id=1,
        plan_id=12,
        source_path=tmp_path / "source" / "IMG_0001.CR3",
        destination_path=tmp_path / "den" / "IMG_0001.CR3",
        size_bytes=123,
        transfer_action=DenTransferAction.COPY,
        status="plan_copy",
    )

    item = _operation_manifest_row(row)

    assert item["operation"] == "copy_with_partial"
    assert item["python_api"] == (
        "Path.mkdir + Python file copy/shutil.copystat + os.rename + macOS setattrlist best-effort"
    )
    assert "best-effort created-date preservation" in item["safety_rule"]
    assert item["partial_path"] == tmp_path / "den" / "IMG_0001.CR3.partial"
    assert item["will_write"] == "yes"


def test_operation_manifest_documents_move_safety(tmp_path: Path) -> None:
    row = ExecutionPlanRow(
        row_id=1,
        plan_id=12,
        source_path=tmp_path / "source" / "IMG_0001.CR3",
        destination_path=tmp_path / "den" / "IMG_0001.CR3",
        size_bytes=123,
        transfer_action=DenTransferAction.MOVE,
        status="plan_copy",
    )

    item = _operation_manifest_row(row)

    assert item["operation"] == "same_filesystem_move"
    assert item["python_api"] == "Path.mkdir + os.rename"
    assert item["safety_rule"] == "destination root containment; same filesystem; no overwrite"


def test_operation_manifest_csv_has_review_columns(tmp_path: Path) -> None:
    path = write_operation_manifest(
        tmp_path / "ops.csv",
        [
            {
                "plan_id": 12,
                "row_id": 1,
                "operation": "skip",
                "source_path": "/source/IMG_0001.CR3",
                "destination_path": "/den/IMG_0001.CR3",
                "partial_path": "",
                "size_bytes": 123,
                "python_api": "none",
                "safety_rule": "already represented",
                "status": "skip_existing",
                "will_write": "no",
            }
        ],
    )

    contents = path.read_text(encoding="utf-8")

    assert "operation,source_path,destination_path,partial_path" in contents
    assert "skip,/source/IMG_0001.CR3,/den/IMG_0001.CR3" in contents
