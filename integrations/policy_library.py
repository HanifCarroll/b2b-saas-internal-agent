"""Read-only policy library operations."""

from .employee_directory import EmployeeSession


def list_policies(session: EmployeeSession) -> list[dict]:
    session._role()
    return [
        {"id": row[0], "content": row[1]}
        for row in session._connection.execute(
            "SELECT id, content FROM policies ORDER BY id"
        )
    ]
