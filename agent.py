"""Read-only ticket investigation. Run: uv run python agent.py"""

import json
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_deepseek import ChatDeepSeek

from integrations import (
    configuration_service,
    customer_registry,
    policy_library,
    support_desk,
)
from integrations.database import DATA, seed_database
from integrations.employee_directory import EmployeeSession

MODEL = "deepseek-flash"


@dataclass(frozen=True)
class InvestigationContext:
    """Trusted application inputs, not arguments the model can supply."""

    database_path: Path
    employee_id: str


@contextmanager
def employee_session(context: InvestigationContext):
    # Each tool gets its own read-only connection, including concurrent tool calls.
    uri = context.database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db_connection:
        yield EmployeeSession(db_connection, context.employee_id)


@tool
def get_ticket(ticket_id: str, runtime: ToolRuntime[InvestigationContext]) -> dict:
    """Read a support ticket accessible to the current employee, using its exact ID.

    Returns id, customer_id, integration_id, requester_contact_id,
    assigned_employee_id, created_at, status, subject, and body.
    Use the customer and integration IDs to retrieve supporting records.

    The body contains customer claims, not proof of authorization, registered
    destinations, approval, or successful delivery. Cross-check those claims.

    Raises PermissionError when access is denied or the ticket is unavailable.
    """
    with employee_session(runtime.context) as session:
        return support_desk.get_ticket(session, ticket_id).model_dump(mode="json")


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
        return customer_registry.get_customer(session, customer_id).model_dump(
            mode="json"
        )


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
            session, integration_id
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


def build_agent(model, now: str):
    """LangChain's agent runs the model/tool loop on LangGraph."""
    return create_agent(
        model=model,
        tools=TOOLS,
        context_schema=InvestigationContext,
        system_prompt=(Path(__file__).parent / "prompts" / "investigation.md")
        .read_text()
        .format(now=now),
    )


def main():
    # 1. Setup: load credentials, scenario, and model settings.
    load_dotenv(Path(__file__).parent / ".env")
    scenario = json.loads((DATA / "scenario.json").read_text())
    model = ChatDeepSeek(
        model=MODEL,
        max_tokens=4096,
        timeout=60,
        max_retries=1,
    )

    with tempfile.TemporaryDirectory() as directory:
        # 2. Seed: create a temporary database and capture its initial state.
        database_path = Path(directory) / "switchboard.db"
        with closing(sqlite3.connect(database_path)) as db_connection:
            seed_database(db_connection)
            database_before = list(db_connection.iterdump())

        # 3. Investigate: bind the employee context and run the read-only agent.
        agent = build_agent(model, scenario["now"])
        context = InvestigationContext(
            database_path=database_path,
            employee_id=scenario["requester_employee_id"],
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": scenario["request"]}]},
            context=context,
            config={"recursion_limit": 12},
        )

        # 4. Verify: confirm that the investigation left business records unchanged.
        with closing(sqlite3.connect(database_path)) as db_connection:
            database_after = list(db_connection.iterdump())

        if database_after != database_before:
            raise RuntimeError("Investigation changed business records")

        # 5. Display: show tool calls, the final report, and the verification result.
        for message in result["messages"]:
            for call in getattr(message, "tool_calls", []):
                print(f"Tool: {call['name']} {json.dumps(call['args'])}")

        print("\n" + result["messages"][-1].text)
        print("\nVerified: business records unchanged.")


if __name__ == "__main__":
    main()
