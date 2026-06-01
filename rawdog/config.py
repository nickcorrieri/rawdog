# Author: Nicholas Corrieri

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from rawdog.models import (
    DestinationFilenamePolicy,
    OrganizationMode,
    RawdogConfig,
    model_to_json_data,
)

APP_NAME = "rawdog"


def default_config_path() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False)) / "config.json"


def default_database_path() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False)) / "rawdog.sqlite"


def load_config(config_path: Path | None = None) -> RawdogConfig:
    path = config_path or default_config_path()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return RawdogConfig.from_dict(data)


def save_config(config: RawdogConfig, config_path: Path | None = None) -> Path:
    path = config_path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model_to_json_data(config)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def build_config(
    organization_mode: OrganizationMode,
    working_root: Path | None = None,
    archive_root: Path | None = None,
    database_path: Path | None = None,
    date_folder_template: str = "YYYY/YYYY-MM",
    project_folder_template: str = "YYYY/YYYYMMDD_PROJECT",
    yard_filename_policy: DestinationFilenamePolicy = DestinationFilenamePolicy.DATE_ORIGINAL,
    den_filename_policy: DestinationFilenamePolicy = DestinationFilenamePolicy.DATE_ORIGINAL,
) -> RawdogConfig:
    return RawdogConfig(
        organization_mode=organization_mode,
        working_root=working_root.expanduser().resolve() if working_root else None,
        archive_root=archive_root.expanduser().resolve() if archive_root else None,
        database_path=(database_path or default_database_path()).expanduser(),
        date_folder_template=date_folder_template,
        project_folder_template=project_folder_template,
        yard_filename_policy=yard_filename_policy,
        den_filename_policy=den_filename_policy,
    )
