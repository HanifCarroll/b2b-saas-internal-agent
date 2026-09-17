"""Read-only policy library operations."""

from .employee_directory import EmployeeSession


def list_policies(session: EmployeeSession) -> list[dict]:
    session.get_active_employee_role()
    return [
        {"id": row[0], "content": row[1]}
        for row in session._db_connection.execute(
            "SELECT id, content FROM policies ORDER BY id"
        )
    ]
