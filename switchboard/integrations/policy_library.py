"""Read-only policy library operations."""

from .employee_directory import EmployeeSession


def list_policies(session: EmployeeSession) -> list[dict]:
    # 1. Require an active employee with a recognized role.
    session.get_active_employee_role()

    # 2. Return all shared policies in a stable order.
    return [
        {"id": row[0], "content": row[1]}
        for row in session._db_connection.execute(
            "SELECT id, content FROM policies ORDER BY id"
        )
    ]
