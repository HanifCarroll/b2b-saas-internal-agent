"""Approval authorization and durable retries, without model calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError
from test_proposals import candidate

from switchboard.integrations.change_management import approve_proposal, save_proposal
from switchboard.integrations.database import (
    initialize_proposal_database,
    seed_database,
)
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import Approval
from switchboard.proposals import validate_proposal


@pytest.mark.parametrize(
    "update",
    [
        {"proposal_id": " "},
        {"approved_by_employee_id": ""},
        {"created_at": "2026-09-18T12:00:00"},
    ],
)
def test_approval_rejects_invalid_fields(update):
    record = {
        "id": "approval-1",
        "proposal_id": "proposal-1",
        "approved_by_employee_id": "emp-priya",
        "created_at": "2026-09-18T12:00:00Z",
    }

    with pytest.raises(ValidationError):
        Approval.model_validate_json(json.dumps(record | update))


@pytest.mark.parametrize(
    "case",
    [
        "allowed",
        "support",
        "engineer",
        "other_customer",
        "inactive",
        "self",
        "revoked",
        "missing",
        "sandbox",
    ],
)
def test_approval_permissions_and_persistence(tmp_path, case):
    # 1. Save a proposal and prepare the reviewer's current directory state.
    path = tmp_path / "proposals.db"
    with closing(sqlite3.connect(":memory:")) as directory:
        seed_database(connection=directory)
        author = EmployeeSession(db_connection=directory, employee_id="emp-alex")
        proposal, _ = save_proposal(
            proposal=validate_proposal(investigation=candidate(), session=author),
            session=author,
            database_path=path,
        )
        employee_id = "emp-priya"
        if case in {"support", "engineer"}:
            role = (
                "support_specialist" if case == "support" else "implementation_engineer"
            )
            directory.execute(
                "UPDATE employees SET role = ? WHERE id = 'emp-priya'", (role,)
            )
        elif case == "other_customer":
            employee_id = "emp-ben"
            directory.execute(
                "UPDATE employees SET role = 'technical_lead' WHERE id = 'emp-ben'"
            )
        elif case == "inactive":
            directory.execute("UPDATE employees SET active = 0 WHERE id = 'emp-priya'")
        elif case == "self":
            employee_id = "emp-alex"
            directory.execute(
                "UPDATE employees SET role = 'technical_lead' WHERE id = 'emp-alex'"
            )
        elif case == "revoked":
            directory.execute("DELETE FROM assignments WHERE employee_id = 'emp-priya'")
        elif case == "sandbox":
            with closing(sqlite3.connect(path)) as storage, storage:
                storage.execute("UPDATE proposals SET environment = 'sandbox'")

        reviewer = EmployeeSession(db_connection=directory, employee_id=employee_id)
        proposal_id = "missing" if case == "missing" else proposal.id
        records_before = list(directory.iterdump())

        # 2. Denied attempts must leave approval storage empty.
        if case != "allowed":
            with pytest.raises((PermissionError, ValueError)):
                approve_proposal(
                    proposal_id=proposal_id, session=reviewer, database_path=path
                )

            with closing(sqlite3.connect(path)) as storage:
                assert (
                    storage.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
                )

        # 3. A permitted retry returns the original durable approval.
        else:
            approval = approve_proposal(
                proposal_id=proposal_id, session=reviewer, database_path=path
            )
            initialize_proposal_database(path)
            retry = approve_proposal(
                proposal_id=proposal_id, session=reviewer, database_path=path
            )

            assert retry == approval
            assert approval.approved_by_employee_id == "emp-priya"
            assert approval.proposal_id == proposal.id
            with closing(sqlite3.connect(path)) as storage:
                assert (
                    storage.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1
                )
                assert (
                    storage.execute("SELECT status FROM proposals").fetchone()[0]
                    == "pending_approval"
                )

            # Current permissions are required even when an approval already exists.
            directory.execute("SAVEPOINT revoke_access")
            directory.execute("DELETE FROM assignments WHERE employee_id = 'emp-priya'")

            with pytest.raises(PermissionError):
                approve_proposal(
                    proposal_id=proposal_id, session=reviewer, database_path=path
                )
            directory.execute("ROLLBACK TO revoke_access")
            directory.execute("RELEASE revoke_access")

        assert list(directory.iterdump()) == records_before
