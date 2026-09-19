"""Shared investigation runner for the CLI and local web demo."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from switchboard.agent import build_agent
from switchboard.demo import read_demo_setup
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.integrations.support_desk import get_ticket
from switchboard.models import EndpointChangeResult, InvestigationRunResult
from switchboard.tools import InvestigationContext
from switchboard.workflow import EndpointChangeContext, endpoint_change_graph


def investigate_scenario(
    *,
    scenario_id: str,
    model: BaseChatModel,
    runs_directory: Path,
    database_path: Path,
    employee_id: str | None = None,
) -> InvestigationRunResult:
    """Investigate shared business records and retain a separate historical result."""
    # 1. Read the explicitly initialized demo; never seed or reapply a scenario here.
    setup = read_demo_setup(database_path)
    if setup is None:
        raise ValueError("Reset the demo to a scenario before investigating")
    active_scenario = setup.scenario_id
    scenario = setup.inputs
    if active_scenario != scenario_id:
        raise ValueError("Selected scenario is not active; reset the demo first")

    requester = employee_id or scenario["requester_employee_id"]
    return _run_investigation(
        ticket_id=scenario["ticket_id"],
        request=scenario["request"],
        employee_id=requester,
        model=model,
        runs_directory=runs_directory,
        database_path=database_path,
        now=scenario["now"],
        scenario_id=scenario_id,
    )


def investigate_ticket(
    *,
    ticket_id: str,
    employee_id: str,
    model: BaseChatModel,
    runs_directory: Path,
    database_path: Path,
    now: datetime,
) -> InvestigationRunResult:
    """Investigate one employee-accessible ticket using the current server time."""
    if now.utcoffset() is None:
        raise ValueError("Investigation time must be timezone-aware")

    return _run_investigation(
        ticket_id=ticket_id,
        request=f"Investigate endpoint change request in ticket {ticket_id}.",
        employee_id=employee_id,
        model=model,
        runs_directory=runs_directory,
        database_path=database_path,
        now=now.isoformat(),
    )


def _run_investigation(
    *,
    ticket_id: str,
    request: str,
    employee_id: str,
    model: BaseChatModel,
    runs_directory: Path,
    database_path: Path,
    now: str,
    scenario_id: str | None = None,
) -> InvestigationRunResult:
    """Authorize, run, and atomically save one ticket investigation."""
    # 1. Authorize the selected ticket before creating a run or invoking the model.
    with closing(sqlite3.connect(database_path)) as connection:
        session = EmployeeSession(db_connection=connection, employee_id=employee_id)
        ticket = get_ticket(session=session, ticket_id=ticket_id)
        role = session.get_active_employee_role()

    # 2. Save the trusted run identity and access snapshot.
    workflow_id = str(uuid4())
    directory = runs_directory / workflow_id
    directory.mkdir(parents=True)
    manifest = {
        "ticket_id": ticket.id,
        "requester_employee_id": employee_id,
        "requester_role": role,
        "customer_ids": [ticket.customer_id],
        "database_path": str(database_path.resolve()),
    }
    if scenario_id is not None:
        manifest["scenario_id"] = scenario_id
    (directory / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # 3. Run the access-controlled workflow with the selected ticket as trusted input.
    context = EndpointChangeContext(
        agent=build_agent(model=model, now=now),
        investigation_context=InvestigationContext(
            database_path=database_path,
            employee_id=employee_id,
        ),
    )
    raw_result = endpoint_change_graph.invoke(
        {"request": request, "ticket_id": ticket.id},
        context=context,
        config={
            "run_name": f"investigation-{scenario_id or ticket.id}",
            "metadata": {
                "ticket_id": ticket.id,
                "workflow_id": workflow_id,
                **({"scenario_id": scenario_id} if scenario_id is not None else {}),
            },
        },
    )
    result = EndpointChangeResult.model_validate(raw_result)

    # 4. Publish a complete result atomically for refresh and later review.
    temporary = directory / "result.tmp"
    temporary.write_text(result.model_dump_json(indent=2))
    temporary.replace(directory / "result.json")
    return InvestigationRunResult(workflow_id=workflow_id, result=result)
