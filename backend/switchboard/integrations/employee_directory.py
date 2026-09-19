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

    def require_active_employee(self) -> None:
        """Raise PermissionError unless the employee is active with a recognized role."""
        self.get_active_employee_role()

    def require_customer_access(
        self, *, customer_id: str, allowed_roles: set[str]
    ) -> None:
        """Require an active employee with a recognized role and customer assignment."""
        # 1. Limit permission to recognized roles, even if the caller supplies others.
        permitted_roles = sorted(allowed_roles & ROLES)
        if not permitted_roles:
            raise PermissionError("Record unavailable")

        # 2. Check existence, identity, role, and assignment without reading the body.
        role_placeholders = ",".join("?" for _ in permitted_roles)
        row = self._db_connection.execute(
            f"""
            SELECT 1
            FROM customers AS customer
            JOIN assignments AS assignment
              ON assignment.customer_id = customer.id
            JOIN employees AS employee
              ON employee.id = assignment.employee_id
            WHERE customer.id = ?
              AND employee.id = ?
              AND employee.active = 1
              AND employee.role IN ({role_placeholders})
            """,
            (customer_id, self._employee_id, *permitted_roles),
        ).fetchone()
        if row is None:
            raise PermissionError("Record unavailable")

    def read_authorized_record(
        self, *, table: str, record_id: str, allowed_roles: set[str]
    ) -> dict:
        """Authorize and retrieve a record within one consistent database snapshot."""
        # 1. Keep ownership lookup, authorization, and retrieval in one snapshot.
        # A savepoint also works inside a caller's transaction without committing it.
        # table is an internal constant, never a tool argument.
        customer_column = "id" if table == "customers" else "customer_id"
        self._db_connection.execute("SAVEPOINT authorized_record_read")
        try:
            row = self._db_connection.execute(
                f"SELECT {customer_column} FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise PermissionError("Record unavailable")

            # 2. Use the shared permission check before retrieving customer data.
            self.require_customer_access(
                customer_id=row[0], allowed_roles=allowed_roles
            )

            # 3. Retrieve and decode the body only after authorization succeeds.
            row = self._db_connection.execute(
                f"SELECT body FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            return json.loads(row[0])
        finally:
            self._db_connection.execute("RELEASE SAVEPOINT authorized_record_read")

    def read_authorized_records(
        self, *, table: str, allowed_roles: set[str]
    ) -> list[dict]:
        """Return every record the bound employee may read."""
        # 1. Reject an inactive or unknown employee even when the table is empty.
        self.require_active_employee()
        record_ids = self._db_connection.execute(
            f"SELECT id FROM {table} ORDER BY id"
        ).fetchall()

        # 2. Reuse the single-record access check for each candidate record.
        records = []
        for (record_id,) in record_ids:
            try:
                records.append(
                    self.read_authorized_record(
                        table=table,
                        record_id=record_id,
                        allowed_roles=allowed_roles,
                    )
                )
            except PermissionError:
                continue

        return records
