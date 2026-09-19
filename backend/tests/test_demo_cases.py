"""Prepared demo cases start at useful, deterministic workflow stages."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest

from switchboard.demo_cases import list_demo_cases, prepare_demo_case
from switchboard.demo_workspaces import open_demo_workspace
from switchboard.integrations.change_management import execute_proposal
from switchboard.integrations.employee_directory import EmployeeSession


def test_case_catalog_explains_four_starting_points():
    cases = list_demo_cases()

    assert [(item.id, item.recommended_persona_id) for item in cases] == [
        ("valid-request", "emp-alex"),
        ("unsafe-destination", "emp-ben"),
        ("pending-approval", "emp-priya"),
        ("ready-to-execute", "emp-alex"),
    ]
    assert all(item.title and item.description for item in cases)


@pytest.mark.parametrize(
    ("case_id", "scenario_id", "proposal_count", "approval_count"),
    [
        ("valid-request", "baseline", 0, 0),
        ("unsafe-destination", "unregistered-destination", 0, 0),
        ("pending-approval", "baseline", 1, 0),
        ("ready-to-execute", "baseline", 1, 1),
    ],
)
def test_prepare_case_replaces_only_the_selected_workspace_stage(
    tmp_path, case_id, scenario_id, proposal_count, approval_count
):
    workspace = open_demo_workspace(
        workspace_id=None, root_directory=tmp_path
    ).workspace

    prepared = prepare_demo_case(case_id=case_id, workspace=workspace)

    assert prepared.case_id == case_id
    assert prepared.path.startswith(("/requests/", "/approvals/"))
    with closing(sqlite3.connect(workspace.database_path)) as connection:
        assert connection.execute("SELECT scenario_id FROM demo_setup").fetchone() == (
            scenario_id,
        )
        assert (
            connection.execute("SELECT count(*) FROM proposals").fetchone()[0]
            == proposal_count
        )
        assert (
            connection.execute("SELECT count(*) FROM approvals").fetchone()[0]
            == approval_count
        )


def test_unknown_case_preserves_existing_workspace(tmp_path):
    workspace = open_demo_workspace(
        workspace_id=None, root_directory=tmp_path
    ).workspace
    before = workspace.database_path.read_bytes()

    with pytest.raises(ValueError, match="Unknown demo case"):
        prepare_demo_case(case_id="missing", workspace=workspace)

    assert workspace.database_path.read_bytes() == before


def test_failed_case_build_preserves_existing_workspace(tmp_path, monkeypatch):
    from switchboard import demo_cases

    workspace = open_demo_workspace(
        workspace_id=None, root_directory=tmp_path
    ).workspace
    before = workspace.database_path.read_bytes()

    def fail(**kwargs):
        raise ValueError("Invalid prepared records")

    monkeypatch.setattr(demo_cases, "_prepare_starting_stage", fail)
    with pytest.raises(ValueError, match="Invalid prepared records"):
        prepare_demo_case(case_id="pending-approval", workspace=workspace)

    assert workspace.database_path.read_bytes() == before


def test_ready_case_passes_existing_execution_checks(tmp_path):
    workspace = open_demo_workspace(
        workspace_id=None, root_directory=tmp_path
    ).workspace
    prepared = prepare_demo_case(case_id="ready-to-execute", workspace=workspace)
    proposal_id = urlparse(prepared.path).path.rsplit("/", 1)[1]

    with closing(sqlite3.connect(workspace.database_path)) as connection:
        result = execute_proposal(
            proposal_id=proposal_id,
            session=EmployeeSession(db_connection=connection, employee_id="emp-alex"),
            executed_at=datetime.now(timezone.utc),
            database_path=workspace.database_path,
        )

    assert result.was_created is True
    assert result.execution.proposal_id == proposal_id
