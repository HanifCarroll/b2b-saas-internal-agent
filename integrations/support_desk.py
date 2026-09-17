"""Read-only support desk operations."""

import json

from models import Ticket

from .employee_directory import ROLES, EmployeeSession


def get_ticket(session: EmployeeSession, ticket_id: str) -> Ticket:
    record = session.read_authorized_record("tickets", ticket_id, ROLES)
    record = {
        key: record[key]
        for key in (
            "id",
            "customer_id",
            "integration_id",
            "requester_contact_id",
            "assigned_employee_id",
            "created_at",
            "status",
            "subject",
            "body",
        )
    }
    return Ticket.model_validate_json(json.dumps(record))
