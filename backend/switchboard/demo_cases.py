"""Prepare deterministic workflow cases inside one demo workspace."""

import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, HttpUrl

from switchboard.demo import demo_operation
from switchboard.demo_workspaces import DemoWorkspace
from switchboard.integrations.change_management import approve_proposal, save_proposal
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import (
    EndpointChangeResult,
    InvestigationFindings,
    InvestigationResult,
)
from switchboard.proposals import validate_proposal
from switchboard.scenarios import initialize_demo_database, load_scenarios


class DemoCaseSummary(BaseModel):
    id: str
    title: str
    description: str
    recommended_persona_id: str


class PreparedDemoCase(BaseModel):
    case_id: str
    persona_id: str
    path: str


class _DemoCase(BaseModel):
    id: str
    title: str
    description: str
    recommended_persona_id: str
    scenario_id: str
    starting_stage: Literal["request", "approval", "execution"]


CASES = (
    _DemoCase(
        id="valid-request",
        title="Investigate a valid request",
        description="Gather evidence for a registered production destination.",
        recommended_persona_id="emp-alex",
        scenario_id="baseline",
        starting_stage="request",
    ),
    _DemoCase(
        id="unsafe-destination",
        title="Detect an unsafe destination",
        description="Find and explain an unregistered production destination.",
        recommended_persona_id="emp-ben",
        scenario_id="unregistered-destination",
        starting_stage="request",
    ),
    _DemoCase(
        id="pending-approval",
        title="Review a pending proposal",
        description="Review a valid proposal as an independent technical lead.",
        recommended_persona_id="emp-priya",
        scenario_id="baseline",
        starting_stage="approval",
    ),
    _DemoCase(
        id="ready-to-execute",
        title="Execute an approved proposal",
        description="Recheck and execute a proposal with independent approval.",
        recommended_persona_id="emp-alex",
        scenario_id="baseline",
        starting_stage="execution",
    ),
)


def list_demo_cases() -> list[DemoCaseSummary]:
    return [
        DemoCaseSummary(
            id=item.id,
            title=item.title,
            description=item.description,
            recommended_persona_id=item.recommended_persona_id,
        )
        for item in CASES
    ]


def prepare_demo_case(*, case_id: str, workspace: DemoWorkspace) -> PreparedDemoCase:
    """Atomically replace one workspace with the requested prepared case."""
    selected = next((item for item in CASES if item.id == case_id), None)
    if selected is None:
        raise ValueError("Unknown demo case")

    workspace.database_path.parent.mkdir(parents=True, exist_ok=True)
    with demo_operation(database_path=workspace.database_path, reset=True):
        with TemporaryDirectory(dir=workspace.database_path.parent) as temporary:
            replacement_directory = Path(temporary)
            replacement_database = replacement_directory / "switchboard.db"
            replacement_runs = replacement_directory / "workflows"
            initialize_demo_database(
                database_path=replacement_database,
                scenario_id=selected.scenario_id,
                selected_scenario=load_scenarios()[selected.scenario_id],
            )
            prepared = _prepare_starting_stage(
                selected=selected,
                database_path=replacement_database,
                final_database_path=workspace.database_path,
                runs_directory=replacement_runs,
            )

            if workspace.runs_directory.exists():
                shutil.rmtree(workspace.runs_directory)
            replacement_database.replace(workspace.database_path)
            if replacement_runs.exists():
                replacement_runs.replace(workspace.runs_directory)

    return prepared


def _prepare_starting_stage(
    *,
    selected: _DemoCase,
    database_path: Path,
    final_database_path: Path,
    runs_directory: Path,
) -> PreparedDemoCase:
    if selected.id == "unsafe-destination":
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO assignments VALUES ('emp-ben', 'acme')"
            )

    if selected.starting_stage == "request":
        return PreparedDemoCase(
            case_id=selected.id,
            persona_id=selected.recommended_persona_id,
            path="/requests/CHG-1042",
        )

    proposal, run_id = _prepare_proposal(
        database_path=database_path,
        final_database_path=final_database_path,
        runs_directory=runs_directory,
        scenario_id=selected.scenario_id,
    )
    if selected.starting_stage == "execution":
        with closing(sqlite3.connect(database_path)) as connection:
            reviewer = EmployeeSession(
                db_connection=connection, employee_id="emp-priya"
            )
            approve_proposal(
                proposal_id=proposal.id,
                session=reviewer,
                database_path=database_path,
            )
        _open_current_change_window(database_path=database_path)

    return PreparedDemoCase(
        case_id=selected.id,
        persona_id=selected.recommended_persona_id,
        path=f"/approvals/{proposal.id}?run={run_id}",
    )


def _prepare_proposal(
    *,
    database_path: Path,
    final_database_path: Path,
    runs_directory: Path,
    scenario_id: str,
):
    with closing(sqlite3.connect(database_path)) as connection:
        author = EmployeeSession(db_connection=connection, employee_id="emp-alex")
        investigation = InvestigationResult(
            outcome="proposal_candidate",
            ticket_id="CHG-1042",
            proposed_endpoint=HttpUrl("https://events.acme.example/deals"),
            evidence_ids=["CHG-1042", "acme", "int-acme-prod"],
            findings=InvestigationFindings(
                overview="The request is supported by current customer and integration records.",
                checks=[
                    "The requester and destination are registered for Acme production."
                ],
                policy_requirements=[
                    "A different technical lead must approve before execution."
                ],
                gaps=[],
                recommendation="Review the saved proposal before execution.",
            ),
            blockers=[],
        )
        proposal = save_proposal(
            proposal=validate_proposal(investigation=investigation, session=author),
            session=author,
            database_path=database_path,
        ).proposal

    run_id = uuid4()
    directory = runs_directory / str(run_id)
    directory.mkdir(parents=True)
    manifest = {
        "ticket_id": "CHG-1042",
        "requester_employee_id": "emp-alex",
        "requester_role": "implementation_engineer",
        "customer_ids": ["acme"],
        "database_path": str(final_database_path.resolve()),
        "scenario_id": scenario_id,
    }
    result = EndpointChangeResult(
        investigation=investigation,
        messages=[],
        proposal=proposal,
        was_created=True,
    )
    (directory / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (directory / "result.json").write_text(result.model_dump_json(indent=2) + "\n")
    return proposal, run_id


def _open_current_change_window(*, database_path: Path) -> None:
    now = datetime.now(timezone.utc)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT body FROM customers WHERE id = 'acme'"
        ).fetchone()
        if row is None:
            raise ValueError("Demo customer is missing")
        customer = json.loads(row[0])
        customer["production_change_window"] = {
            "weekday": now.strftime("%A"),
            "start": "00:00",
            "end": "23:59",
            "timezone": "UTC",
        }
        connection.execute(
            "UPDATE customers SET body = ? WHERE id = 'acme'",
            (json.dumps(customer),),
        )
