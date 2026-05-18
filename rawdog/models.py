# Author: Nicholas Corrieri

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class OrganizationMode(StrEnum):
    DATE = "date"
    PROJECT = "project"


class ProfileKind(StrEnum):
    INGEST = "ingest"


class NamingConvention(StrEnum):
    DETECT = "detect"
    KEEP_EXISTING = "keep-existing"
    DDD = "ddd"
    PROJECT_LABEL = "project-label"


class CollisionPolicy(StrEnum):
    SKIP = "skip"
    ASK = "ask"


class DenLayoutMode(StrEnum):
    PRESERVE = "preserve"
    PRESERVE_DATES = "preserve-dates"
    DATE = "date"
    PROJECT = "project"


class DenTransferAction(StrEnum):
    COPY = "copy"
    MOVE = "move"


class PlanStepKind(StrEnum):
    SNIFF = "sniff"
    SCORE = "score"
    DEN = "den"


class ExecutionPlanStatus(StrEnum):
    PLANNED = "planned"
    STARTED = "started"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


def _require_name(value: str, field_name: str = "name") -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def model_to_json_data(value: Any) -> Any:
    if is_dataclass(value):
        return {key: model_to_json_data(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [model_to_json_data(item) for item in value]
    if isinstance(value, dict):
        return {key: model_to_json_data(item) for key, item in value.items()}
    return value


@dataclass(slots=True, kw_only=True)
class RawdogConfig:
    organization_mode: OrganizationMode
    working_root: Path | None = None
    archive_root: Path | None = None
    database_path: Path
    date_folder_template: str = "YYYY/YYYY-MM"
    project_folder_template: str = "YYYY/YYYYMMDD_PROJECT"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawdogConfig:
        return cls(
            organization_mode=OrganizationMode(data["organization_mode"]),
            working_root=Path(data["working_root"]) if data.get("working_root") else None,
            archive_root=Path(data["archive_root"]) if data.get("archive_root") else None,
            database_path=Path(data["database_path"]),
            date_folder_template=data.get("date_folder_template", "YYYY/YYYY-MM"),
            project_folder_template=data.get("project_folder_template", "YYYY/YYYYMMDD_PROJECT"),
        )


@dataclass(slots=True, kw_only=True)
class ProjectCreate:
    name: str
    client_name: str | None = None
    tags: list[str] = field(default_factory=list)
    location: str | None = None
    notes: str | None = None
    preferred_folder_template: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name)


@dataclass(slots=True, kw_only=True)
class Project:
    project_id: int
    name: str
    folder_slug: str
    created_at: datetime
    updated_at: datetime
    client_name: str | None = None
    tags: list[str] = field(default_factory=list)
    location: str | None = None
    notes: str | None = None
    preferred_folder_template: str | None = None
    archived: bool = False
    last_import_at: datetime | None = None


@dataclass(slots=True, kw_only=True)
class ImportProfileCreate:
    name: str
    source_root: Path
    destination_root: Path
    profile_kind: ProfileKind = ProfileKind.INGEST
    organization_mode: OrganizationMode = OrganizationMode.PROJECT
    folder_template: str = "YYYY/YYYYMMDD_PROJECT"
    naming_convention: NamingConvention = NamingConvention.DETECT
    collision_policy: CollisionPolicy = CollisionPolicy.SKIP
    verify_after_copy: bool = True
    dry_run_default: bool = True
    exclude_patterns: list[str] = field(default_factory=list)
    project_id: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name)


@dataclass(slots=True, kw_only=True)
class ImportProfile:
    profile_id: int
    name: str
    source_root: Path
    destination_root: Path
    profile_kind: ProfileKind
    organization_mode: OrganizationMode
    folder_template: str
    naming_convention: NamingConvention
    collision_policy: CollisionPolicy
    verify_after_copy: bool
    dry_run_default: bool
    exclude_patterns: list[str] = field(default_factory=list)
    project_id: int | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    notes: str | None = None


@dataclass(slots=True, kw_only=True)
class ConsolidationWorkflowCreate:
    name: str
    source_root: Path
    destination_root: Path
    layout_mode: DenLayoutMode = DenLayoutMode.PRESERVE
    transfer_action: DenTransferAction = DenTransferAction.COPY
    folder_template: str | None = None
    project_id: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name)


@dataclass(slots=True, kw_only=True)
class ConsolidationWorkflow:
    workflow_id: int
    name: str
    source_root: Path
    destination_root: Path
    layout_mode: DenLayoutMode
    transfer_action: DenTransferAction = DenTransferAction.COPY
    folder_template: str | None = None
    project_id: int | None = None
    created_at: datetime
    updated_at: datetime
    last_planned_at: datetime | None = None
    last_committed_at: datetime | None = None
    notes: str | None = None


@dataclass(slots=True, kw_only=True)
class PlanQueueCreate:
    name: str
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name)


@dataclass(slots=True, kw_only=True)
class PlanQueue:
    queue_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    status: str
    notes: str | None = None


@dataclass(slots=True, kw_only=True)
class PlanQueueStepCreate:
    queue_id: int
    step_order: int
    step_kind: PlanStepKind
    source_root: Path | None = None
    destination_root: Path | None = None
    layout_mode: DenLayoutMode | None = None
    transfer_action: DenTransferAction | None = None
    folder_template: str | None = None
    project_name: str | None = None


@dataclass(slots=True, kw_only=True)
class PlanQueueStep:
    step_id: int
    queue_id: int
    step_order: int
    step_kind: PlanStepKind
    source_root: Path | None = None
    destination_root: Path | None = None
    layout_mode: DenLayoutMode | None = None
    transfer_action: DenTransferAction | None = None
    folder_template: str | None = None
    project_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, kw_only=True)
class ExecutionPlanCreate:
    plan_kind: str
    what: str
    subject: str
    expected_result: str
    execution_summary: str = ""
    post_audit_summary: str = ""
    source_root: Path | None = None
    destination_root: Path | None = None
    queue_id: int | None = None


@dataclass(slots=True, kw_only=True)
class ExecutionPlan:
    plan_id: int
    plan_kind: str
    status: ExecutionPlanStatus
    what: str
    subject: str
    expected_result: str
    execution_summary: str
    post_audit_summary: str
    source_root: Path | None = None
    destination_root: Path | None = None
    queue_id: int | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True, kw_only=True)
class ExecutionPlanRowCreate:
    source_path: Path
    destination_path: Path
    size_bytes: int
    transfer_action: DenTransferAction
    status: str


@dataclass(slots=True, kw_only=True)
class ExecutionPlanRow:
    row_id: int
    plan_id: int
    source_path: Path
    destination_path: Path
    size_bytes: int
    transfer_action: DenTransferAction
    status: str
    audit_status: str | None = None
    executed_at: datetime | None = None
    audited_at: datetime | None = None
    error: str | None = None


@dataclass(slots=True, kw_only=True)
class SessionCandidate:
    start_at: datetime
    end_at: datetime
    file_count: int
    suggested_name: str | None = None
