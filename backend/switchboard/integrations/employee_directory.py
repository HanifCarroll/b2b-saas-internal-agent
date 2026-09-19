"""Trusted employee context and shared customer-access enforcement."""

from typing import get_args

from switchboard.models import Role
from switchboard.storage import WorkspaceStorage

ROLES = set(get_args(Role))
CONFIG_ROLES = {"implementation_engineer", "technical_lead"}


class EmployeeSession:
    """Bind trusted identity to one isolated storage workspace."""

    def __init__(self, *, storage: WorkspaceStorage, employee_id: str):
        self._storage = storage
        self._employee_id = employee_id

    @property
    def employee_id(self) -> str:
        return self._employee_id

    @property
    def storage(self) -> WorkspaceStorage:
        return self._storage

    def get_active_employee_role(self) -> Role:
        employee = self._storage.get_employee(employee_id=self._employee_id)
        if (
            employee is None
            or employee["active"] not in (True, 1)
            or employee["role"] not in ROLES
        ):
            raise PermissionError("Access denied")
        return employee["role"]

    def get_employee_name(self, *, employee_id: str) -> str:
        self.require_active_employee()
        name = self._storage.get_employee_name(employee_id=employee_id)
        if name is None:
            raise PermissionError("Employee unavailable")
        return name

    def require_active_employee(self) -> None:
        self.get_active_employee_role()

    def require_customer_access(
        self, *, customer_id: str, allowed_roles: set[str]
    ) -> None:
        permitted_roles = allowed_roles & ROLES
        role = self.get_active_employee_role()
        assignments = self._storage.get_employee_assignments(
            employee_id=self._employee_id
        )
        if (
            role not in permitted_roles
            or customer_id not in assignments
            or self._storage.get_customer(customer_id=customer_id) is None
        ):
            raise PermissionError("Record unavailable")

    def read_authorized_record(
        self, *, table: str, record_id: str, allowed_roles: set[str]
    ) -> dict:
        readers = {
            "customers": lambda: self._storage.get_customer(customer_id=record_id),
            "integrations": lambda: self._storage.get_integration(
                integration_id=record_id
            ),
            "tickets": lambda: self._storage.get_ticket(ticket_id=record_id),
        }
        if table not in readers:
            raise ValueError("Unknown business record type")

        record = readers[table]()
        if record is None:
            raise PermissionError("Record unavailable")
        customer_id = record["id"] if table == "customers" else record["customer_id"]
        self.require_customer_access(
            customer_id=customer_id, allowed_roles=allowed_roles
        )
        return record

    def read_authorized_records(
        self, *, table: str, allowed_roles: set[str]
    ) -> list[dict]:
        if table != "tickets":
            raise ValueError("Unknown business record collection")
        self.require_active_employee()

        records = []
        for record in self._storage.list_tickets():
            try:
                self.require_customer_access(
                    customer_id=record["customer_id"], allowed_roles=allowed_roles
                )
            except PermissionError:
                continue
            records.append(record)
        return records
