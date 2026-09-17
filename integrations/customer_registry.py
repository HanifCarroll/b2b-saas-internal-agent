"""Read-only customer registry operations."""

import json

from models import Customer

from .employee_directory import CONFIG_ROLES, EmployeeSession


def get_customer(session: EmployeeSession, customer_id: str) -> Customer:
    record = session.read_authorized_record("customers", customer_id, CONFIG_ROLES)
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
