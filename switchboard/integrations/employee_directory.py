"""Trusted employee context and shared customer-access enforcement."""

import json
import sqlite3
from typing import get_args

from switchboard.models import Role

ROLES = set(get_args(Role))
CONFIG_ROLES = {"implementation_engineer", "technical_lead"}


class EmployeeSession:
    """Bind identity outside model-controlled arguments. This is not authentication.

    Bind this session in application code before exposing business functions
    as tools. Never expose the constructor, connection, or arbitrary SQL. Checks reread directory state.
    """

    def __init__(self, *, db_connection: sqlite3.Connection, employee_id: str):
        self._db_connection = db_connection
        self._employee_id = employee_id

    @property
    def employee_id(self) -> str:
        """Identity bound by application code, not supplied by the model."""
        return self._employee_id

    def get_active_employee_role(self) -> Role:
        """Return the current employee's role; deny access if inactive or unknown."""
        # 1. Look up the active employee using the bound identity.
        row = self._db_connection.execute(
            "SELECT role FROM employees WHERE id = ? AND active = 1",
            (self._employee_id,),
        ).fetchone()
        # 2. Reject unknown identities or roles before returning the role.
        if row is None or row[0] not in ROLES:
            raise PermissionError("Access denied")
        return row[0]

    def read_authorized_record(
        self, *, table: str, record_id: str, allowed_roles: set[str]
    ) -> dict:
        """Return a record only when both role and customer assignment permit it."""
        # 1. Require an active employee with a role permitted by this operation.
        role = self.get_active_employee_role()
        if role not in allowed_roles:
            raise PermissionError("Access denied")

        # 2. Enforce customer assignment in the query, before retrieving the body.
        # Recheck active status and role in that same query.
        # table is an internal constant, never a tool argument.
        customer_column = "record.id" if table == "customers" else "record.customer_id"
        role_placeholders = ",".join("?" for _ in allowed_roles)
        row = self._db_connection.execute(
            f"""
            SELECT record.body
            FROM {table} AS record
            JOIN assignments AS assignment
              ON assignment.customer_id = {customer_column}
            JOIN employees AS employee
              ON employee.id = assignment.employee_id
            WHERE record.id = ?
              AND employee.id = ?
              AND employee.active = 1
              AND employee.role IN ({role_placeholders})
            """,
            (record_id, self._employee_id, *sorted(allowed_roles)),
        ).fetchone()
        # Missing and forbidden records have the same response to avoid disclosure.
        if row is None:
            raise PermissionError("Record unavailable")
        return json.loads(row[0])
