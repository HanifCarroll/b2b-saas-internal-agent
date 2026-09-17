"""Persist proposals; never approve or execute configuration changes."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from switchboard.models import Proposal
from switchboard.proposals import validate_endpoint_change_request

from .database import PROPOSALS_DATABASE, initialize_proposal_database
from .employee_directory import EmployeeSession


def save_proposal(
    proposal: Proposal,
    session: EmployeeSession,
    database_path: Path = PROPOSALS_DATABASE,
) -> Proposal:
    """Recheck authorization and records, then save or return an identical proposal.

    Identity and the full configuration snapshot must still match. SQLite serializes
    duplicate detection and insertion so concurrent retries cannot create duplicates.
    Execution must independently recheck current authority and configuration later.
    """
    proposal = Proposal.model_validate_json(proposal.model_dump_json())
    ticket, integration = validate_endpoint_change_request(
        proposal.ticket_id, proposal.proposed_endpoint, session
    )
    if (
        proposal.proposed_by_employee_id != session.employee_id
        or proposal.requester_contact_id != ticket.requester_contact_id
        or proposal.customer_id != ticket.customer_id
        or proposal.integration_id != integration.id
        or proposal.environment != integration.environment
        or proposal.current_endpoint != integration.endpoint
        or proposal.expected_configuration_version != integration.version
    ):
        raise ValueError("Proposal no longer matches the employee or business records")

    snapshot = proposal.model_dump(mode="json", exclude={"id", "created_at"})
    initialize_proposal_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        # Column names come only from the application model, never model output.
        conditions = " AND ".join(f"{column} = :{column}" for column in snapshot)
        existing = connection.execute(
            f"SELECT * FROM proposals WHERE {conditions}", snapshot
        ).fetchone()
        if existing is not None:
            return Proposal.model_validate_json(json.dumps(dict(existing)))
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
            proposal.model_dump(mode="json"),
        )
    return proposal
