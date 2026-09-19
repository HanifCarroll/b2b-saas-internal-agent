"""Named access to one workspace in the private D1 bridge."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

StorageTransport = Callable[[str, str, dict], Any]


class StorageError(RuntimeError):
    def __init__(self, message: str, *, status: int = 500):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class WorkspaceStorage:
    """Call explicit domain operations for one isolated workspace."""

    workspace_id: str
    bridge_url: str
    bridge_token: str | None = None
    transport: StorageTransport | None = None

    @classmethod
    def from_environment(cls, *, workspace_id: str) -> "WorkspaceStorage":
        return cls(
            workspace_id=workspace_id,
            bridge_url=os.getenv("STORAGE_BRIDGE_URL", "http://127.0.0.1:8787"),
            bridge_token=os.getenv("LOCAL_STORAGE_BRIDGE_TOKEN"),
        )

    def for_workspace(self, *, workspace_id: str) -> "WorkspaceStorage":
        return WorkspaceStorage(
            workspace_id=workspace_id,
            bridge_url=self.bridge_url,
            bridge_token=self.bridge_token,
            transport=self.transport,
        )

    def get_workspace(self) -> dict | None:
        return self._call("workspace.get")

    def reset_workspace(self, *, payload: dict) -> None:
        self._call("workspace.reset", payload)

    def delete_workspace(self) -> None:
        self._call("workspace.delete")

    def touch_workspace(self, *, updated_at: str) -> None:
        self._call("workspace.touch", {"updatedAt": updated_at})

    def get_employee(self, *, employee_id: str) -> dict | None:
        return self._call("employee.get", {"id": employee_id})

    def get_employee_name(self, *, employee_id: str) -> str | None:
        return self._call("employee.name", {"id": employee_id})

    def list_active_employees(self) -> list[dict]:
        return self._call("employee.list")

    def get_employee_assignments(self, *, employee_id: str) -> list[str]:
        return self._call("employee.assignments", {"employeeId": employee_id})

    def get_customer(self, *, customer_id: str) -> dict | None:
        return self._call("customer.get", {"id": customer_id})

    def get_integration(self, *, integration_id: str) -> dict | None:
        return self._call("integration.get", {"id": integration_id})

    def get_ticket(self, *, ticket_id: str) -> dict | None:
        return self._call("ticket.get", {"id": ticket_id})

    def list_tickets(self) -> list[dict]:
        return self._call("ticket.list")

    def list_policies(self) -> list[dict]:
        return self._call("policy.list")

    def get_proposal(self, *, proposal_id: str) -> dict | None:
        return self._call("proposal.get", {"id": proposal_id})

    def list_pending_proposals(self) -> list[dict]:
        return self._call("proposal.list")

    def save_proposal(self, *, proposal: dict) -> dict:
        return self._call("proposal.save", {"proposal": proposal})

    def get_approval(self, *, proposal_id: str) -> dict | None:
        return self._call("approval.get", {"proposalId": proposal_id})

    def save_approval(self, *, approval: dict) -> dict:
        return self._call("approval.save", {"approval": approval})

    def get_execution(self, *, proposal_id: str) -> dict | None:
        return self._call("execution.get", {"proposalId": proposal_id})

    def apply_execution(
        self,
        *,
        execution: dict,
        integration_id: str,
        customer_id: str,
        expected_version: int,
        current_endpoint: str,
        proposed_endpoint: str,
    ) -> dict:
        return self._call(
            "execution.apply",
            {
                "execution": execution,
                "integrationId": integration_id,
                "customerId": customer_id,
                "expectedVersion": expected_version,
                "currentEndpoint": current_endpoint,
                "proposedEndpoint": proposed_endpoint,
            },
        )

    def get_run(self, *, run_id: str) -> dict | None:
        return self._call("run.get", {"id": run_id})

    def list_runs(self, *, ticket_id: str) -> list[dict]:
        return self._call("run.list", {"ticketId": ticket_id})

    def save_run(self, *, run: dict) -> None:
        self._call("run.save", {"run": run})

    def find_proposal_run(self, *, proposal_id: str) -> str | None:
        return self._call("run.findProposal", {"proposalId": proposal_id})

    def save_policy_review(self, *, run_id: str, review: dict) -> None:
        self._call("run.savePolicyReview", {"id": run_id, "review": review})

    def _call(self, operation: str, payload: dict | None = None):
        if self.transport is not None:
            return self.transport(operation, self.workspace_id, payload or {})

        content = json.dumps(
            {
                "operation": operation,
                "workspaceId": self.workspace_id,
                "payload": payload or {},
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.bridge_token:
            headers["Authorization"] = f"Bearer {self.bridge_token}"
        request = Request(self.bridge_url, data=content, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=10) as response:
                body = json.load(response)
        except HTTPError as error:
            body = json.loads(error.read())
            raise StorageError(
                body.get("error", "Storage request failed"), status=error.code
            ) from None
        except (URLError, TimeoutError):
            raise StorageError("Storage service unavailable", status=503) from None

        return body["data"]
