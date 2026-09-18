"""Read-only LangChain tools and trusted invocation context."""

import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from langchain.tools import ToolRuntime, tool

from switchboard.integrations import (
    configuration_service,
    customer_registry,
    policy_library,
    support_desk,
)
from switchboard.integrations.employee_directory import EmployeeSession


@dataclass(frozen=True)
class InvestigationContext:
    """Trusted application inputs, not arguments the model can supply."""

    database_path: Path
    employee_id: str


@contextmanager
def employee_session(context: InvestigationContext):
    # 1. Open a separate read-only connection for this invocation.
    uri = context.database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db_connection:
        # 2. Bind the trusted identity and close the connection when finished.
        yield EmployeeSession(
            db_connection=db_connection, employee_id=context.employee_id
        )


@tool
def get_ticket(ticket_id: str, runtime: ToolRuntime[InvestigationContext]) -> dict:
    """Read a support ticket accessible to the current employee, using its exact ID.

    Returns id, customer_id, integration_id, requester_contact_id,
    assigned_employee_id, requested_endpoint, created_at, status, subject, and body.
    requested_endpoint is the structured destination submitted at ticket intake.
    Use the customer and integration IDs to retrieve supporting records.

    The body contains customer claims, not proof of authorization, registered
    destinations, approval, or successful delivery. Cross-check those claims.

    Raises PermissionError when access is denied or the ticket is unavailable.
    """
    with employee_session(runtime.context) as session:
        return support_desk.get_ticket(session=session, ticket_id=ticket_id).model_dump(
            mode="json"
        )


@tool
def get_customer(customer_id: str, runtime: ToolRuntime[InvestigationContext]) -> dict:
    """Read an accessible customer registry record using its exact customer ID.

    Returns id, name, authorized_contacts (id, name, email),
    registered_destinations (environment, url), and production_change_window
    (weekday, start, end, timezone). Use these to check the requesting contact,
    proposed destination for the target environment, and scheduled window.

    Registration does not prove endpoint reachability or change approval.

    Raises PermissionError when access is denied or the customer is unavailable.
    """
    with employee_session(runtime.context) as session:
        return customer_registry.get_customer(
            session=session, customer_id=customer_id
        ).model_dump(mode="json")


@tool
def get_integration(
    integration_id: str, runtime: ToolRuntime[InvestigationContext]
) -> dict:
    """Read an accessible integration's current configuration using its exact ID.

    Returns id, customer_id, name, environment, endpoint, and version.

    Distinguish integrations by customer and environment, not name alone.
    The version identifies the configuration observed during this read;
    it may change afterward. This does not verify delivery to the endpoint
    or establish approval for a change. Credentials are not returned.

    Raises PermissionError when access is denied or the integration is unavailable.
    """
    with employee_session(runtime.context) as session:
        return configuration_service.get_integration(
            session=session, integration_id=integration_id
        ).model_dump(mode="json")


@tool
def list_policies(runtime: ToolRuntime[InvestigationContext]) -> list[dict]:
    """Read all shared policy documents available to an active employee.

    Returns a list of objects with id and content. Content is the full Markdown
    document, including YAML metadata for status, effective date, and any
    supersession links. Both current and superseded versions are returned;
    compare their metadata against the scenario date before applying a rule.

    Policies describe requirements, not evidence of a particular approval.

    Raises PermissionError for an inactive or unknown employee or role.
    """
    with employee_session(runtime.context) as session:
        return policy_library.list_policies(session)


TOOLS = [get_ticket, get_customer, get_integration, list_policies]
