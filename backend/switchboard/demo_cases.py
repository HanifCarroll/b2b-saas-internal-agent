"""Prepare deterministic workflow cases inside one demo workspace."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, HttpUrl

from switchboard.demo_workspaces import DemoWorkspace
from switchboard.integrations.change_management import approve_proposal, save_proposal
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import (
    DecisionCriterion,
    EndpointChangeResult,
    InvestigationFindings,
    InvestigationResult,
    ReportValidation,
)
from switchboard.proposals import validate_proposal
from switchboard.scenarios import build_workspace_payload, load_scenarios


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
    """Replace one workspace with the requested deterministic case."""
    selected = next((item for item in CASES if item.id == case_id), None)
    if selected is None:
        raise ValueError("Unknown demo case")

    # 1. Build and adjust the complete workspace before replacing current data.
    payload = build_workspace_payload(
        scenario_id=selected.scenario_id,
        selected_scenario=load_scenarios()[selected.scenario_id],
        identity_mode="demo",
    )
    if selected.id == "unsafe-destination":
        employee = next(
            item for item in payload["records"]["employees"] if item["id"] == "emp-ben"
        )
        employee["customer_ids"] = sorted({*employee["customer_ids"], "acme"})
    if selected.starting_stage == "execution":
        _open_current_change_window(payload=payload)
    workspace.storage.reset_workspace(payload=payload)

    if selected.starting_stage == "request":
        return PreparedDemoCase(
            case_id=selected.id,
            persona_id=selected.recommended_persona_id,
            path="/requests/CHG-1042",
        )

    # 2. Prepare the proposal and durable investigation record.
    proposal, run_id = _prepare_proposal(
        workspace=workspace,
        scenario_id=selected.scenario_id,
    )
    if selected.starting_stage == "execution":
        reviewer = EmployeeSession(storage=workspace.storage, employee_id="emp-priya")
        approve_proposal(proposal_id=proposal.id, session=reviewer)

    return PreparedDemoCase(
        case_id=selected.id,
        persona_id=selected.recommended_persona_id,
        path=f"/approvals/{proposal.id}?run={run_id}",
    )


def _prepare_proposal(*, workspace: DemoWorkspace, scenario_id: str):
    author = EmployeeSession(storage=workspace.storage, employee_id="emp-alex")
    investigation = InvestigationResult(
        outcome="proposal_candidate",
        ticket_id="CHG-1042",
        proposed_endpoint=HttpUrl("https://events.acme.example/deals"),
        evidence_ids=["CHG-1042", "acme", "int-acme-prod"],
        findings=InvestigationFindings(
            overview="The request is supported by current customer and integration records.",
            decision_criteria=[
                DecisionCriterion(
                    name="Requester and destination",
                    status="verified",
                    required_before="proposal",
                    explanation=(
                        "The requester and destination are registered for Acme production."
                    ),
                    policy_id="endpoint-change-v2",
                    evidence_ids=["acme", "int-acme-prod"],
                ),
                DecisionCriterion(
                    name="Independent approval",
                    status="deferred",
                    required_before="execution",
                    explanation=(
                        "A different technical lead must approve before execution."
                    ),
                    policy_id="endpoint-change-v2",
                    evidence_ids=[],
                ),
            ],
            recommendation="Review the saved proposal before execution.",
        ),
        blockers=[],
    )
    proposal = save_proposal(
        proposal=validate_proposal(investigation=investigation, session=author),
        session=author,
    ).proposal

    run_id = uuid4()
    result = EndpointChangeResult(
        investigation=investigation,
        report_validation=ReportValidation(
            policy_ids=["endpoint-change-v1", "endpoint-change-v2"],
            evaluation_count=1,
            revision_count=0,
        ),
        messages=[],
        proposal=proposal,
        was_created=True,
    )
    workspace.storage.save_run(
        run={
            "id": str(run_id),
            "ticket_id": "CHG-1042",
            "scenario_id": scenario_id,
            "requester_employee_id": "emp-alex",
            "requester_role": "implementation_engineer",
            "customer_ids": ["acme"],
            "result": result.model_dump(mode="json"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return proposal, run_id


def _open_current_change_window(*, payload: dict) -> None:
    now = datetime.now(timezone.utc)
    customer = next(
        item for item in payload["records"]["customers"] if item["id"] == "acme"
    )
    customer["production_change_window"] = {
        "weekday": now.strftime("%A"),
        "start": "00:00",
        "end": "23:59",
        "timezone": "UTC",
    }
