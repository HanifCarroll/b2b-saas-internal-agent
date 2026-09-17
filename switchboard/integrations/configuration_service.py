"""Read-only configuration service operations."""

import json

from switchboard.models import Integration

from .employee_directory import CONFIG_ROLES, EmployeeSession


def get_integration(session: EmployeeSession, integration_id: str) -> Integration:
    record = session.read_authorized_record(
        "integrations", integration_id, CONFIG_ROLES
    )
    record = {
        key: record[key]
        for key in (
            "id",
            "customer_id",
            "name",
            "environment",
            "endpoint",
            "version",
        )
    }
    return Integration.model_validate_json(json.dumps(record))
