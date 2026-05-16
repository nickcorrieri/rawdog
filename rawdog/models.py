# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class OrganizationMode(StrEnum):
    DATE = "date"
    PROJECT = "project"


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


class RawdogConfig(BaseModel):
    organization_mode: OrganizationMode
    working_root: Path | None = None
    archive_root: Path | None = None
    database_path: Path
    date_folder_template: str = "YYYY/YYYY-MM"
    project_folder_template: str = "YYYY/YYYYMMDD_PROJECT"


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    client_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    location: str | None = None
    notes: str | None = None
    preferred_folder_template: str | None = None


class Project(BaseModel):
    project_id: int
    name: str
    folder_slug: str
    created_at: datetime
    updated_at: datetime
    client_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    location: str | None = None
    notes: str | None = None
    preferred_folder_template: str | None = None
    archived: bool = False
    last_import_at: datetime | None = None


class ImportProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    source_root: Path
    destination_root: Path
    organization_mode: OrganizationMode = OrganizationMode.PROJECT
    folder_template: str = "YYYY/YYYYMMDD_PROJECT"
    project_id: int | None = None
    notes: str | None = None


class ImportProfile(BaseModel):
    profile_id: int
    name: str
    source_root: Path
    destination_root: Path
    organization_mode: OrganizationMode
    folder_template: str
    project_id: int | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    notes: str | None = None


class ConsolidationWorkflowCreate(BaseModel):
    name: str = Field(min_length=1)
    source_root: Path
    destination_root: Path
    layout_mode: DenLayoutMode = DenLayoutMode.PRESERVE
    transfer_action: DenTransferAction = DenTransferAction.COPY
    folder_template: str | None = None
    project_id: int | None = None
    notes: str | None = None


class ConsolidationWorkflow(BaseModel):
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


class PlanQueueCreate(BaseModel):
    name: str = Field(min_length=1)
    notes: str | None = None


class PlanQueue(BaseModel):
    queue_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    status: str
    notes: str | None = None


class PlanQueueStepCreate(BaseModel):
    queue_id: int
    step_order: int
    step_kind: PlanStepKind
    source_root: Path | None = None
    destination_root: Path | None = None
    layout_mode: DenLayoutMode | None = None
    transfer_action: DenTransferAction | None = None
    folder_template: str | None = None
    project_name: str | None = None


class PlanQueueStep(BaseModel):
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


class ExecutionPlanCreate(BaseModel):
    plan_kind: str
    what: str
    subject: str
    expected_result: str
    execution_summary: str = ""
    post_audit_summary: str = ""
    source_root: Path | None = None
    destination_root: Path | None = None
    queue_id: int | None = None


class ExecutionPlan(BaseModel):
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


class ExecutionPlanRowCreate(BaseModel):
    source_path: Path
    destination_path: Path
    size_bytes: int
    transfer_action: DenTransferAction
    status: str


class ExecutionPlanRow(BaseModel):
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


class SessionCandidate(BaseModel):
    start_at: datetime
    end_at: datetime
    file_count: int
    suggested_name: str | None = None
