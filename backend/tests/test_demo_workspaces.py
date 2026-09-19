"""Anonymous visitors receive isolated, reusable demo storage."""

import sqlite3
from contextlib import closing
from os import utime
from time import time
from uuid import uuid4

from switchboard.demo_workspaces import open_demo_workspace


def test_first_visit_creates_baseline_workspace_and_cookie_id_can_reopen_it(tmp_path):
    opened = open_demo_workspace(workspace_id=None, root_directory=tmp_path)

    assert opened.was_created is True
    assert opened.workspace.database_path.exists()
    with closing(sqlite3.connect(opened.workspace.database_path)) as connection:
        assert connection.execute("SELECT scenario_id FROM demo_setup").fetchone() == (
            "baseline",
        )

    reopened = open_demo_workspace(
        workspace_id=opened.workspace.id,
        root_directory=tmp_path,
    )

    assert reopened.was_created is False
    assert reopened.workspace == opened.workspace


def test_unknown_workspace_id_cannot_select_or_share_another_workspace(tmp_path):
    first = open_demo_workspace(workspace_id=None, root_directory=tmp_path)
    unknown = open_demo_workspace(workspace_id=uuid4(), root_directory=tmp_path)

    assert unknown.was_created is True
    assert unknown.workspace.id != first.workspace.id
    assert unknown.workspace.database_path != first.workspace.database_path


def test_expired_workspace_is_replaced_and_deleted(tmp_path):
    expired = open_demo_workspace(workspace_id=None, root_directory=tmp_path).workspace
    old = time() - 25 * 60 * 60
    utime(expired.database_path.parent, (old, old))

    replacement = open_demo_workspace(
        workspace_id=expired.id,
        root_directory=tmp_path,
    )

    assert replacement.was_created is True
    assert replacement.workspace.id != expired.id
    assert not expired.database_path.parent.exists()
