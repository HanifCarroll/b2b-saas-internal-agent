"""Read-only configuration service operations."""

import json

from switchboard.models import Integration

from .employee_directory import CONFIG_ROLES, EmployeeSession


def get_integration(*, session: EmployeeSession, integration_id: str) -> Integration:
    # 1. Read the record only after employee access checks.
    record = session.read_authorized_record(
        table="integrations", record_id=integration_id, allowed_roles=CONFIG_ROLES
    )

    # 2. Select the fields this integration exposes.
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

    # 3. Validate the public record before returning it.
    return Integration.model_validate_json(json.dumps(record))
