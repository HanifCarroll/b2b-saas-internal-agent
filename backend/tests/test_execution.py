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
