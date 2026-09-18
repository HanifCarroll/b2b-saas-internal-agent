"""Read-only customer registry operations."""

import json

from switchboard.models import Customer

from .employee_directory import CONFIG_ROLES, EmployeeSession


def get_customer(*, session: EmployeeSession, customer_id: str) -> Customer:
    record = session.read_authorized_record(
        table="customers", record_id=customer_id, allowed_roles=CONFIG_ROLES
    )
    record = {
        key: record[key]
        for key in (
            "id",
            "name",
            "authorized_contacts",
            "production_change_window",
            "registered_destinations",
        )
    }
    return Customer.model_validate_json(json.dumps(record))
