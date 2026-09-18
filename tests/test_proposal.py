"""Proposal shape and durable storage checks; no model calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from switchboard.integrations.database import initialize_proposal_database
from switchboard.models import Proposal

PROPOSAL = {
    "id": "proposal-001",
    "proposed_by_employee_id": "alex",
    "ticket_id": "CHG-1042",
    "requester_contact_id": "contact-001",
    "customer_id": "acme",
    "integration_id": "int-acme-prod",
    "environment": "production",
    "current_endpoint": "https://old.acme.example/deals",
    "proposed_endpoint": "https://events.acme.example/deals",
    "expected_configuration_version": 7,
    "created_at": "2026-09-17T12:00:00Z",
}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("proposed_by_employee_id", " "),
        ("proposed_endpoint", "not-a-url"),
        ("expected_configuration_version", 0),
        ("created_at", "2026-09-17T12:00:00"),
        ("status", "approved"),
    ],
)
def test_proposal_rejects_invalid_fields(field, value):
    with pytest.raises(ValidationError):
        Proposal.model_validate_json(json.dumps({**PROPOSAL, field: value}))


def test_proposal_survives_reopening_and_initialization(tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    path = tmp_path / "local" / "proposals.db"
    initialize_proposal_database(path)
    proposal = Proposal.model_validate_json(json.dumps(PROPOSAL))
    record = proposal.model_dump(mode="json")
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO proposals (
                id, proposed_by_employee_id, ticket_id, requester_contact_id,
                customer_id, integration_id, environment, current_endpoint,
                proposed_endpoint, expected_configuration_version, created_at, status
            ) VALUES (
                :id, :proposed_by_employee_id, :ticket_id, :requester_contact_id,
                :customer_id, :integration_id, :environment, :current_endpoint,
                :proposed_endpoint, :expected_configuration_version, :created_at, :status
            )
            """,
            record,
        )
    initialize_proposal_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM proposals").fetchall()
    # 2. Verify the expected result and any safety guarantees.
    assert len(rows) == 1
    assert Proposal.model_validate_json(json.dumps(dict(rows[0]))) == proposal
    assert proposal.status == "pending_approval"
