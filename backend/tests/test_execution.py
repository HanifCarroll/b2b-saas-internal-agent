"""Execution receipt validation and storage, without executing business changes."""

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from switchboard.integrations.database import seed_database
from switchboard.models import Execution

RECEIPT = {
    "id": "execution-001",
    "proposal_id": "proposal-001",
    "executed_by_employee_id": "emp-alex",
    "approval_id": "approval-001",
    "executed_at": "2026-09-22T14:30:00Z",
    "previous_configuration_version": 7,
    "resulting_configuration_version": 8,
}


@pytest.mark.parametrize(
    "update",
    [
        {"proposal_id": ""},
        {"executed_by_employee_id": " "},
        {"approval_id": ""},
        {"executed_at": "2026-09-22T14:30:00"},
        {"previous_configuration_version": 0},
        {"resulting_configuration_version": 7},
        {"resulting_configuration_version": 9},
    ],
)
def test_execution_rejects_invalid_receipt(update):
    with pytest.raises(ValidationError):
        Execution.model_validate_json(json.dumps(RECEIPT | update))


@pytest.mark.parametrize("approval_id", ["approval-001", None])
def test_execution_receipt_is_durable_and_unique_per_proposal(tmp_path, approval_id):
    # 1. Store a validated receipt in the configuration database.
    path = tmp_path / "business.db"
    receipt = Execution.model_validate_json(
        json.dumps(RECEIPT | {"approval_id": approval_id})
    )
    insert = """
        INSERT INTO executions (
            id, proposal_id, executed_by_employee_id, approval_id, executed_at,
            previous_configuration_version, resulting_configuration_version
        ) VALUES (
            :id, :proposal_id, :executed_by_employee_id, :approval_id, :executed_at,
            :previous_configuration_version, :resulting_configuration_version
        )
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        seed_database(connection=connection)
        connection.execute(insert, receipt.model_dump(mode="json"))

    # 2. Reopen storage and verify the receipt, including sandbox's absent approval.
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM executions WHERE proposal_id = ?", (receipt.proposal_id,)
        ).fetchone()
        assert Execution.model_validate_json(json.dumps(dict(row))) == receipt

        # 3. Reject a duplicate even with a different execution ID.
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute(
                insert, receipt.model_dump(mode="json") | {"id": "execution-002"}
            )

        # 4. Enforce the version rule even when code bypasses model validation.
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute(
                insert,
                receipt.model_dump(mode="json")
                | {
                    "id": "execution-003",
                    "proposal_id": "proposal-002",
                    "resulting_configuration_version": 9,
                },
            )

        assert connection.execute("SELECT count(*) FROM executions").fetchone()[0] == 1


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "stale",
        "support",
        "revoked",
        "missing_approval",
        "window",
        "rollback",
        "request",
    ],
)
def test_execute_proposal(tmp_path, case):
    from datetime import datetime, timezone

    from test_proposals import candidate

    from switchboard.integrations.change_management import (
        approve_proposal,
        execute_proposal,
        save_proposal,
    )
    from switchboard.integrations.employee_directory import EmployeeSession
    from switchboard.proposals import validate_proposal

    # 1. Save a proposal and its independent approval in shared storage.
    path = tmp_path / "business.db"
    with closing(sqlite3.connect(path)) as connection:
        seed_database(connection=connection)
        author = EmployeeSession(db_connection=connection, employee_id="emp-alex")
        saved_proposal = save_proposal(
            proposal=validate_proposal(investigation=candidate(), session=author),
            session=author,
            database_path=path,
        )
        proposal = saved_proposal.proposal
        if case != "missing_approval":
            approve_proposal(
                proposal_id=proposal.id,
                session=EmployeeSession(
                    db_connection=connection, employee_id="emp-priya"
                ),
                database_path=path,
            )
            connection.execute(
                "UPDATE approvals SET created_at = '2026-09-22T13:00:00Z'"
            )

        # 2. Break one requirement or force the receipt write to fail.
        changes = {
            "stale": "UPDATE integrations SET body = json_set(body, '$.version', 8) WHERE id = 'int-acme-prod'",
            "support": "UPDATE employees SET role = 'support_specialist' WHERE id = 'emp-alex'",
            "revoked": "DELETE FROM assignments WHERE employee_id = 'emp-priya'",
            "request": "UPDATE tickets SET body = json_set(body, '$.requested_endpoint', 'https://other.example/') WHERE id = 'CHG-1042'",
            "rollback": "CREATE TRIGGER fail_receipt BEFORE INSERT ON executions BEGIN SELECT RAISE(ABORT, 'receipt failed'); END",
        }
        if case in changes:
            connection.execute(changes[case])
        connection.commit()
        before = list(connection.execute("SELECT * FROM integrations ORDER BY id"))
        now = datetime(
            2026, 9, 22, 16 if case == "window" else 14, 0, tzinfo=timezone.utc
        )

        # 3. Failures must leave both configuration and receipts unchanged.
        if case != "success":
            with pytest.raises((ValueError, PermissionError, sqlite3.IntegrityError)):
                execute_proposal(
                    proposal_id=proposal.id,
                    session=author,
                    executed_at=now,
                    database_path=path,
                )
            assert (
                list(connection.execute("SELECT * FROM integrations ORDER BY id"))
                == before
            )
            assert (
                connection.execute("SELECT count(*) FROM executions").fetchone()[0] == 0
            )
            return

        # 4. Change only the selected endpoint/version, then return the same receipt on retry.
        result = execute_proposal(
            proposal_id=proposal.id, session=author, executed_at=now, database_path=path
        )
        assert result.was_created
        after = list(connection.execute("SELECT * FROM integrations ORDER BY id"))
        for old, new in zip(before, after):
            if old[0] == proposal.integration_id:
                assert json.loads(new[2]) == json.loads(old[2]) | {
                    "endpoint": str(proposal.proposed_endpoint),
                    "version": 8,
                }
            else:
                assert old == new
        repeated = execute_proposal(
            proposal_id=proposal.id,
            session=author,
            executed_at=now.replace(hour=18),
            database_path=path,
        )
        assert repeated.execution == result.execution
        assert not repeated.was_created
        connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")
        connection.commit()
        with pytest.raises(PermissionError):
            execute_proposal(
                proposal_id=proposal.id,
                session=author,
                executed_at=now,
                database_path=path,
            )
