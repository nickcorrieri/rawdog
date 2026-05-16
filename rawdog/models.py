# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class OrganizationMode(StrEnum):
    DATE = "date"
    PROJECT = "project"


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


class SessionCandidate(BaseModel):
    start_at: datetime
    end_at: datetime
    file_count: int
    suggested_name: str | None = None
