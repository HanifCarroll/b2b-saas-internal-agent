"""Shared investigation runner for the CLI and local web demo."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from switchboard.agent import build_agent
from switchboard.integrations.database import seed_database
from switchboard.models import EndpointChangeResult
from switchboard.scenarios import Scenario, apply_scenario
from switchboard.tools import InvestigationContext
from switchboard.workflow import EndpointChangeContext, endpoint_change_graph


def investigate_scenario(
    *,
    scenario_id: str,
    selected_scenario: Scenario,
    model: BaseChatModel,
    runs_directory: Path,
    proposals_database_path: Path,
    employee_id: str | None = None,
) -> tuple[str, EndpointChangeResult]:
    """Create isolated records, run the existing graph, and retain its result."""
    # 1. Create durable scenario records and a trusted run manifest.
    workflow_id = str(uuid4())
    directory = runs_directory / workflow_id
    directory.mkdir(parents=True)
    database_path = directory / "business.db"
    with closing(sqlite3.connect(database_path)) as connection:
        seed_database(connection=connection)
        scenario = apply_scenario(db_connection=connection, scenario=selected_scenario)

    requester = employee_id or scenario["requester_employee_id"]
    (directory / "run.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "requester_employee_id": requester,
                "proposals_database_path": str(proposals_database_path.resolve()),
            },
            indent=2,
        )
        + "\n"
    )

    # 2. Run the same access-controlled workflow for either application interface.
    context = EndpointChangeContext(
        agent=build_agent(model=model, now=scenario["now"]),
        investigation_context=InvestigationContext(
            database_path=database_path,
            employee_id=requester,
        ),
        proposals_database_path=proposals_database_path,
    )
    raw_result = endpoint_change_graph.invoke(
        {"request": scenario["request"]},
        context=context,
        config={
            "run_name": f"investigation-{scenario_id}",
            "metadata": {"scenario_id": scenario_id, "workflow_id": workflow_id},
        },
    )
    result = EndpointChangeResult.model_validate(raw_result)

    # 3. Publish a complete result atomically for refresh and later review.
    temporary = directory / "result.tmp"
    temporary.write_text(result.model_dump_json(indent=2))
    temporary.replace(directory / "result.json")
    return workflow_id, result
