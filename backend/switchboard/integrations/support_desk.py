"""Read-only support desk operations."""

import json

from switchboard.models import PersonReference, Ticket, TicketDetails

from .employee_directory import ROLES, EmployeeSession

TICKET_FIELDS = (
    "id",
    "customer_id",
    "integration_id",
    "requester_contact_id",
    "assigned_employee_id",
    "requested_endpoint",
    "created_at",
    "status",
    "subject",
    "body",
)


def _validate_ticket(record: dict) -> Ticket:
    exposed_record = {key: record[key] for key in TICKET_FIELDS}
    return Ticket.model_validate_json(json.dumps(exposed_record))


def get_ticket(*, session: EmployeeSession, ticket_id: str) -> Ticket:
    # 1. Read the record only after employee access checks.
    record = session.read_authorized_record(
        table="tickets", record_id=ticket_id, allowed_roles=ROLES
    )

    # 2. Select the fields this integration exposes.
    # 3. Validate the public record before returning it.
    return _validate_ticket(record)


def list_tickets(*, session: EmployeeSession) -> list[Ticket]:
    """Return tickets assigned to customers the employee may access."""
    records = session.read_authorized_records(table="tickets", allowed_roles=ROLES)
    return [_validate_ticket(record) for record in records]


def get_ticket_details(*, session: EmployeeSession, ticket: Ticket) -> TicketDetails:
    """Add current display names to an already authorized ticket."""
    customer = session.read_authorized_record(
        table="customers", record_id=ticket.customer_id, allowed_roles=ROLES
    )
    requester = next(
        (
            contact
            for contact in customer["authorized_contacts"]
            if contact["id"] == ticket.requester_contact_id
        ),
        None,
    )
    if requester is None:
        raise ValueError("Ticket requester is unavailable")

    return TicketDetails(
        **ticket.model_dump(),
        requester=PersonReference(
            id=ticket.requester_contact_id,
            name=requester["name"],
        ),
        assigned_employee=PersonReference(
            id=ticket.assigned_employee_id,
            name=session.get_employee_name(employee_id=ticket.assigned_employee_id),
        ),
    )
