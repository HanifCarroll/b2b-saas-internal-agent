"""Read-only support desk operations."""

import json

from switchboard.models import Ticket

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
