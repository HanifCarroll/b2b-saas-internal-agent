"""Trusted employee context and shared customer-access enforcement."""

import json
import sqlite3
from typing import get_args

from models import Role

ROLES = set(get_args(Role))
CONFIG_ROLES = {"implementation_engineer", "technical_lead"}


class EmployeeSession:
    """Bind identity outside model-controlled arguments. This is not authentication.

    Bind this session in application code before exposing business functions
    as tools. Never expose the constructor, connection, or arbitrary SQL. Checks reread directory state.
    """

    def __init__(self, connection: sqlite3.Connection, employee_id: str):
        self._connection = connection
        self._employee_id = employee_id

    def _role(self) -> str:
        row = self._connection.execute(
            "SELECT role FROM employees WHERE id = ? AND active = 1",
            (self._employee_id,),
        ).fetchone()
        if row is None or row[0] not in ROLES:
            raise PermissionError("Access denied")
        return row[0]

    def _read(self, table: str, record_id: str, allowed_roles: set[str]) -> dict:
        # table is an internal constant, never a tool argument.
        if self._role() not in allowed_roles:
            raise PermissionError("Access denied")
        customer_column = "r.id" if table == "customers" else "r.customer_id"
        row = self._connection.execute(
            f"SELECT r.body FROM {table} r JOIN assignments a ON a.customer_id = {customer_column} "
            "JOIN employees e ON e.id = a.employee_id "
            "WHERE r.id = ? AND e.id = ? AND e.active = 1 AND e.role IN ("
            + ",".join("?" for _ in allowed_roles)
            + ")",
            (record_id, self._employee_id, *sorted(allowed_roles)),
        ).fetchone()
        # Missing and forbidden records have the same response to avoid disclosure.
        if row is None:
            raise PermissionError("Record unavailable")
        return json.loads(row[0])
