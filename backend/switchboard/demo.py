"""Explicit local demo setup and reset, separate from investigation."""

import fcntl
import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from switchboard.scenarios import initialize_demo_database, load_scenarios


class DemoBusyError(RuntimeError):
    pass


@contextmanager
def demo_operation(*, database_path: Path, reset: bool = False):
    """Exclude resets across CLI/API processes while allowing ordinary operations."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: one POSIX file lock for the local demo; use a distributed lease for multiple hosts.
    with database_path.with_suffix(".lock").open("a") as lock:
        mode = fcntl.LOCK_EX if reset else fcntl.LOCK_SH
        try:
            fcntl.flock(lock, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DemoBusyError(
                "Demo is busy. Wait for the current operation, then retry."
            ) from None

        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_demo_setup(database_path: Path) -> tuple[str, dict] | None:
    """Read the active scenario without creating or changing the database."""
    if not database_path.exists():
        return None

    with closing(
        sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        row = connection.execute(
            "SELECT scenario_id, inputs FROM demo_setup WHERE id = 1"
        ).fetchone()

    if row is None:
        raise ValueError("Demo setup is incomplete; reset the demo")

    return row[0], json.loads(row[1])


def reset_demo(*, database_path: Path, runs_directory: Path, scenario_id: str) -> None:
    """Replace the local demo only after the requested scenario builds successfully."""
    scenarios = load_scenarios()
    if scenario_id not in scenarios:
        raise ValueError("Unknown scenario")

    # 1. Exclude every active CLI/API operation, including other resets.
    with demo_operation(database_path=database_path, reset=True):
        # 2. Validate and build replacement records before deleting saved work.
        with TemporaryDirectory(dir=database_path.parent) as temporary:
            replacement = Path(temporary) / "switchboard.db"
            initialize_demo_database(
                database_path=replacement,
                scenario_id=scenario_id,
                selected_scenario=scenarios[scenario_id],
            )

            # 3. Clear historical runs, then atomically publish the complete database.
            # If history deletion fails, the previous business database remains intact.
            if runs_directory.exists():
                shutil.rmtree(runs_directory)
            replacement.replace(database_path)
