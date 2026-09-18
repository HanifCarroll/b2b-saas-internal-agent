"""Read and save proposals and approvals; never execute configuration changes."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from switchboard.models import Approval, Proposal
from switchboard.proposals import validate_endpoint_change_request

from .database import PROPOSALS_DATABASE, initialize_proposal_database
from .employee_directory import ROLES, EmployeeSession


def save_proposal(
    *,
    proposal: Proposal,
    session: EmployeeSession,
    database_path: Path = PROPOSALS_DATABASE,
) -> tuple[Proposal, bool]:
    """Recheck authorization and records, then save or return an identical proposal.

    Returns (proposal, created): created is False for an existing proposal.

    Identity and the full configuration snapshot must still match. SQLite serializes
    duplicate detection and insertion so concurrent retries cannot create duplicates.
    Execution must independently recheck current authority and configuration later.
    """
    # 1. Validate the input and recheck it against current business records.
    proposal = Proposal.model_validate_json(proposal.model_dump_json())
    ensure_proposal_matches_current_records(proposal=proposal, session=session)

    parameters = proposal.model_dump(mode="json")

    # 2. Keep duplicate detection and insertion in one transaction.
    initialize_proposal_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        # IDs and creation times differ on retries; compare the business fields.
        existing = connection.execute(
            """
            SELECT * FROM proposals
            WHERE proposed_by_employee_id = :proposed_by_employee_id
              AND ticket_id = :ticket_id
              AND requester_contact_id = :requester_contact_id
              AND customer_id = :customer_id
              AND integration_id = :integration_id
              AND environment = :environment
              AND current_endpoint = :current_endpoint
              AND proposed_endpoint = :proposed_endpoint
              AND expected_configuration_version = :expected_configuration_version
              AND recovery_plan = :recovery_plan
              AND status = :status
            """,
            parameters,
        ).fetchone()
        if existing is not None:
            return Proposal.model_validate_json(json.dumps(dict(existing))), False

        # 3. Insert only when there is no identical proposal.
        connection.execute(
            """
            INSERT INTO proposals (
                id, proposed_by_employee_id, ticket_id, requester_contact_id,
                customer_id, integration_id, environment, current_endpoint,
                proposed_endpoint, expected_configuration_version, recovery_plan, created_at, status
            ) VALUES (
                :id, :proposed_by_employee_id, :ticket_id, :requester_contact_id,
                :customer_id, :integration_id, :environment, :current_endpoint,
                :proposed_endpoint, :expected_configuration_version, :recovery_plan, :created_at, :status
            )
            """,
            parameters,
        )

    return proposal, True


def ensure_proposal_matches_current_records(
    *, proposal: Proposal, session: EmployeeSession
) -> None:
    """Raise if access, request validity, or the proposal snapshot has changed."""
    # 1. Recheck access and whether the request is still supported.
    ticket, integration = validate_endpoint_change_request(
        ticket_id=proposal.ticket_id,
        proposed_endpoint=proposal.proposed_endpoint,
        session=session,
    )

    # 2. Reject changes to the proposing identity or configuration snapshot.
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


def get_proposal(
    *,
    session: EmployeeSession,
    proposal_id: str,
    database_path: Path = PROPOSALS_DATABASE,
) -> Proposal:
    """Read a proposal for an active employee assigned to its customer.

    All recognized roles may read. Missing and inaccessible proposals produce
    the same error.
    """
    try:
        # 1. Check the employee before looking up any proposal.
        session.require_active_employee()

        # 2. Fetch from existing storage without creating or changing it.
        if not database_path.exists():
            raise PermissionError("Record unavailable")

        uri = database_path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()

        if row is None:
            raise PermissionError("Record unavailable")

        # 3. Recheck active status and role, and require customer assignment.
        session.require_customer_access(
            customer_id=row["customer_id"], allowed_roles=ROLES
        )
    except PermissionError:
        raise PermissionError("Record unavailable") from None

    # 4. Return the stored proposal only after access has been checked.
    return Proposal.model_validate_json(json.dumps(dict(row)))


def approve_proposal(
    *,
    proposal_id: str,
    session: EmployeeSession,
    database_path: Path = PROPOSALS_DATABASE,
) -> Approval:
    """Record independent technical-lead approval or return the existing approval.

    Approves the stored proposal snapshot, which must remain immutable. Sandbox
    proposals need no independent approval. Execution must separately recheck
    authority, configuration, the change window, and the recovery plan.
    """
    # 1. Load the saved proposal through current customer-access checks.
    proposal = get_proposal(
        session=session, proposal_id=proposal_id, database_path=database_path
    )

    # 2. Require an independent technical lead for a production proposal.
    session.require_customer_access(
        customer_id=proposal.customer_id,
        allowed_roles={"technical_lead"},
    )
    if session.employee_id == proposal.proposed_by_employee_id:
        raise PermissionError(
            "The proposing employee cannot approve their own proposal"
        )
    if proposal.environment != "production":
        raise ValueError("Sandbox proposals do not require independent approval")

    # 3. Serialize retries so only one approval can be stored for this proposal.
    initialize_proposal_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM approvals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if existing is not None:
            return Approval.model_validate_json(json.dumps(dict(existing)))

        # 4. Bind the approver and timestamp in application code, then persist.
        approval = Approval(
            id=str(uuid4()),
            proposal_id=proposal.id,
            approved_by_employee_id=session.employee_id,
            created_at=datetime.now(timezone.utc),
        )
        connection.execute(
            """
            INSERT INTO approvals (id, proposal_id, approved_by_employee_id, created_at)
            VALUES (:id, :proposal_id, :approved_by_employee_id, :created_at)
            """,
            approval.model_dump(mode="json"),
        )

    return approval


def get_proposal_review(
    *,
    session: EmployeeSession,
    proposal_id: str,
    database_path: Path = PROPOSALS_DATABASE,
) -> tuple[Proposal, Approval | None]:
    """Return an accessible proposal together with its optional approval receipt."""
    # 1. Require current access before querying approval storage.
    proposal = get_proposal(
        session=session, proposal_id=proposal_id, database_path=database_path
    )

    # 2. Read existing storage, including older databases with no approval table yet.
    uri = database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'approvals'"
        ).fetchone()
        if table is None:
            return proposal, None

        row = connection.execute(
            "SELECT * FROM approvals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()

    approval = Approval.model_validate_json(json.dumps(dict(row))) if row else None
    return proposal, approval
