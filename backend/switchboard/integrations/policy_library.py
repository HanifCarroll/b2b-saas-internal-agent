"""Read-only policy library operations."""

from .employee_directory import EmployeeSession


def list_policies(session: EmployeeSession) -> list[dict]:
    # 1. Require an active employee with a recognized role.
    session.require_active_employee()

    # 2. Return all shared policies in a stable order.
    return session.storage.list_policies()
