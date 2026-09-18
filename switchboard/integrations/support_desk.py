"""Read-only support desk operations."""

import json

from switchboard.models import Ticket

from .employee_directory import ROLES, EmployeeSession


def get_ticket(*, session: EmployeeSession, ticket_id: str) -> Ticket:
    record = session.read_authorized_record(
        table="tickets", record_id=ticket_id, allowed_roles=ROLES
    )
    record = {
        key: record[key]
        for key in (
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
    }
    return Ticket.model_validate_json(json.dumps(record))
