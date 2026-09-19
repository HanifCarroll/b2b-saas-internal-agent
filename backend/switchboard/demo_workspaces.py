"""Create isolated storage for each anonymous demo visitor."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import UUID, uuid4

from switchboard.scenarios import initialize_demo_database, load_scenarios

WORKSPACE_LIFETIME_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class DemoWorkspace:
    id: UUID
    database_path: Path
    runs_directory: Path


@dataclass(frozen=True)
class OpenedDemoWorkspace:
    workspace: DemoWorkspace
    was_created: bool


def open_demo_workspace(
    *, workspace_id: UUID | None, root_directory: Path
) -> OpenedDemoWorkspace:
    """Open a known workspace or create a new baseline workspace."""
    root_directory.mkdir(parents=True, exist_ok=True)

    if workspace_id is not None:
        workspace = _workspace(root_directory=root_directory, workspace_id=workspace_id)
        if workspace.database_path.is_file():
            directory = workspace.database_path.parent
            if time() - directory.stat().st_mtime <= WORKSPACE_LIFETIME_SECONDS:
                directory.touch()
                return OpenedDemoWorkspace(workspace=workspace, was_created=False)
            shutil.rmtree(directory)

    workspace = _workspace(root_directory=root_directory, workspace_id=uuid4())
    initialize_demo_database(
        database_path=workspace.database_path,
        scenario_id="baseline",
        selected_scenario=load_scenarios()["baseline"],
    )
    return OpenedDemoWorkspace(workspace=workspace, was_created=True)


def _workspace(*, root_directory: Path, workspace_id: UUID) -> DemoWorkspace:
    directory = root_directory / str(workspace_id)
    return DemoWorkspace(
        id=workspace_id,
        database_path=directory / "switchboard.db",
        runs_directory=directory / "workflows",
    )
