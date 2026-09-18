"""Business validation for endpoint-change proposals, independent of the agent."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import HttpUrl

from switchboard.integrations import (
    configuration_service,
    customer_registry,
    support_desk,
)
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import Integration, InvestigationResult, Proposal, Ticket


def validate_proposal(
    *, investigation: InvestigationResult, session: EmployeeSession
) -> Proposal:
    """Build a proposal from authorized records; raise if the request is unsupported.

    Approval and execution windows are checked later, before execution.
    The model's summary and evidence IDs are not proof of business authorization.
    """
    # 1. Require a candidate with the fields needed to prepare a proposal.
    if (
        investigation.outcome != "proposal_candidate"
        or investigation.ticket_id is None
        or investigation.proposed_endpoint is None
        or investigation.blockers
    ):
        raise ValueError("Investigation is not a proposal candidate")

    # 2. Check the request against current, access-controlled records.
    ticket, integration = validate_endpoint_change_request(
        ticket_id=investigation.ticket_id,
        proposed_endpoint=investigation.proposed_endpoint,
        session=session,
    )

    # 3. Build the snapshot with application-generated identity and time.
    return Proposal(
        id=str(uuid4()),
        proposed_by_employee_id=session.employee_id,
        ticket_id=ticket.id,
        requester_contact_id=ticket.requester_contact_id,
        customer_id=ticket.customer_id,
        integration_id=integration.id,
        environment=integration.environment,
        current_endpoint=integration.endpoint,
        proposed_endpoint=ticket.requested_endpoint,
        expected_configuration_version=integration.version,
        created_at=datetime.now(timezone.utc),
    )


def validate_endpoint_change_request(
    *,
    ticket_id: str,
    proposed_endpoint: HttpUrl,
    session: EmployeeSession,
) -> tuple[Ticket, Integration]:
    """Return checked records or raise if the endpoint-change request is unsupported.

    Checks access, customer ownership, requester authority, and destination.
    This does not grant approval or permission to execute the change.
    """
    # 1. Read the related records through employee access checks.
    ticket = support_desk.get_ticket(session=session, ticket_id=ticket_id)
    customer = customer_registry.get_customer(
        session=session, customer_id=ticket.customer_id
    )
    integration = configuration_service.get_integration(
        session=session, integration_id=ticket.integration_id
    )
    # 2. Confirm customer ownership and requester authority.
    if integration.customer_id != customer.id:
        raise ValueError("Ticket and integration belong to different customers")
    if ticket.requester_contact_id not in {
        contact.id for contact in customer.authorized_contacts
    }:
        raise ValueError("Ticket requester is not an authorized customer contact")
    # 3. Match the requested destination and its environment registration.
    if proposed_endpoint != ticket.requested_endpoint:
        raise ValueError("Proposed endpoint does not match the ticket request")
    if not any(
        destination.environment == integration.environment
        and destination.url == ticket.requested_endpoint
        for destination in customer.registered_destinations
    ):
        raise ValueError("Requested endpoint is not registered for this environment")
    # 4. Reject a no-op and return the checked records.
    if ticket.requested_endpoint == integration.endpoint:
        raise ValueError("Requested endpoint is already configured")

    return ticket, integration
