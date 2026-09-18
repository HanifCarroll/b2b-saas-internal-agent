"""Local demo API. Employee headers simulate identity; they are not authentication."""

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from switchboard.agent import create_model
from switchboard.integrations.change_management import (
    approve_proposal,
    get_proposal_review,
)
from switchboard.integrations.database import FIXTURES, PROPOSALS_DATABASE
from switchboard.integrations.employee_directory import ROLES
from switchboard.investigations import investigate_scenario
from switchboard.models import Approval, EndpointChangeResult, Proposal
from switchboard.policy_evaluation import PolicyReview, evaluate_policy
from switchboard.scenarios import load_scenarios
from switchboard.tools import InvestigationContext, employee_session

logger = logging.getLogger(__name__)

RUNS_DIRECTORY = PROPOSALS_DATABASE.parent / "workflows"
app = FastAPI(title="Switchboard local demo")


class ProposalReview(BaseModel):
    proposal: Proposal
    approval: Approval | None


def review_context(
    *, run_id: UUID, employee_id: str
) -> tuple[InvestigationContext, Path]:
    """Resolve only application-created run manifests, never client filesystem paths."""
    # 1. Locate the persisted scenario records.
    directory = RUNS_DIRECTORY / str(run_id)
    manifest_path = directory / "run.json"
    database_path = directory / "business.db"
    if not manifest_path.is_file() or not database_path.is_file():
        raise HTTPException(status_code=404, detail="Scenario run unavailable")

    # 2. Bind the simulated identity to the selected run.
    manifest = json.loads(manifest_path.read_text())
    return InvestigationContext(
        database_path=database_path, employee_id=employee_id
    ), Path(manifest["proposals_database_path"])


@app.get("/api/runs/{run_id}/proposals/{proposal_id}", response_model=ProposalReview)
def read_proposal(
    run_id: UUID, proposal_id: str, x_employee_id: str = Header(min_length=1)
):
    # 1. Resolve application storage and simulated employee context.
    context, storage = review_context(run_id=run_id, employee_id=x_employee_id)

    # 2. Delegate authorization and storage to the business functions.
    try:
        with employee_session(context) as session:
            proposal, approval = get_proposal_review(
                session=session, proposal_id=proposal_id, database_path=storage
            )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Proposal unavailable") from None

    return ProposalReview(proposal=proposal, approval=approval)


@app.post(
    "/api/runs/{run_id}/proposals/{proposal_id}/approval", response_model=Approval
)
def record_approval(
    run_id: UUID, proposal_id: str, x_employee_id: str = Header(min_length=1)
):
    # 1. Resolve application storage and simulated employee context.
    context, storage = review_context(run_id=run_id, employee_id=x_employee_id)

    # 2. Delegate authorization and storage to the business functions.
    try:
        with employee_session(context) as session:
            return approve_proposal(
                session=session, proposal_id=proposal_id, database_path=storage
            )
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Approval not permitted or proposal unavailable"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=409, detail="Proposal is not eligible for independent approval"
        ) from None


class InvestigationRequest(BaseModel):
    scenario_id: str


class InvestigationRun(BaseModel):
    run_id: UUID
    scenario_id: str
    result: EndpointChangeResult
    policy_review: PolicyReview | None = None


@app.get("/api/demo-options")
def demo_options():
    """Expose synthetic demo choices, never secrets or provider configuration."""
    employees = json.loads((FIXTURES / "employees.json").read_text())
    return {
        "scenarios": [
            {"id": key, "expected": scenario.expected}
            for key, scenario in load_scenarios().items()
        ],
        "employees": [
            {"id": item["id"], "name": item["name"], "role": item["role"]}
            for item in employees
            if item["active"]
        ],
    }


@app.post("/api/investigations", response_model=InvestigationRun)
def start_investigation(
    request: InvestigationRequest, x_employee_id: str = Header(min_length=1)
):
    # 1. Validate demo choices before spending any model tokens.
    scenarios = load_scenarios()
    if request.scenario_id not in scenarios:
        raise HTTPException(status_code=422, detail="Unknown scenario")
    employees = json.loads((FIXTURES / "employees.json").read_text())
    if not any(e["id"] == x_employee_id and e["active"] for e in employees):
        raise HTTPException(status_code=403, detail="Employee unavailable")

    # 2. Run the existing workflow, including deterministic validation and saving.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    try:
        run_id, result = investigate_scenario(
            scenario_id=request.scenario_id,
            selected_scenario=scenarios[request.scenario_id],
            model=create_model(),
            runs_directory=RUNS_DIRECTORY,
            proposals_database_path=PROPOSALS_DATABASE,
            employee_id=x_employee_id,
        )
    except (ValueError, PermissionError):
        raise HTTPException(
            status_code=422, detail="Investigation result was rejected"
        ) from None
    except Exception:
        logger.exception("Investigation failed")
        raise HTTPException(
            status_code=502,
            detail="Investigation could not complete. Check run history before retrying; a proposal may already have been saved.",
        ) from None

    return InvestigationRun(
        run_id=UUID(run_id), scenario_id=request.scenario_id, result=result
    )


def accessible_run(*, run_id: UUID, employee_id: str) -> InvestigationRun:
    """Restrict investigation history to its requester with current record access."""
    # 1. Check the run owner before reading saved model output.
    context, _ = review_context(run_id=run_id, employee_id=employee_id)
    directory = RUNS_DIRECTORY / str(run_id)
    manifest = json.loads((directory / "run.json").read_text())
    if manifest.get("requester_employee_id") != employee_id:
        raise HTTPException(status_code=404, detail="Investigation unavailable")
    result_path = directory / "result.json"
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="Investigation unavailable")

    # 2. Recheck current access before returning any saved evidence.
    result = EndpointChangeResult.model_validate_json(result_path.read_text())
    try:
        with employee_session(context) as session:
            session.get_active_employee_role()
            if result.investigation.ticket_id is not None:
                session.read_authorized_record(
                    table="tickets",
                    record_id=result.investigation.ticket_id,
                    allowed_roles=ROLES,
                )
    except PermissionError:
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None

    policy_path = directory / "policy-review.json"
    return InvestigationRun(
        run_id=run_id,
        scenario_id=manifest["scenario_id"],
        result=result,
        policy_review=PolicyReview.model_validate_json(policy_path.read_text())
        if policy_path.exists()
        else None,
    )


@app.get("/api/investigations")
def list_investigations(x_employee_id: str = Header(min_length=1)):
    # 1. Read only completed runs accessible to this employee.
    runs = []
    for path in sorted(
        RUNS_DIRECTORY.glob("*/result.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            run = accessible_run(
                run_id=UUID(path.parent.name), employee_id=x_employee_id
            )
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise

        # 2. Return a compact index; detailed evidence is loaded separately.
        runs.append(
            {
                "run_id": str(run.run_id),
                "scenario_id": run.scenario_id,
                "outcome": run.result.investigation.outcome,
            }
        )
    return runs


@app.get("/api/investigations/{run_id}", response_model=InvestigationRun)
def read_investigation(run_id: UUID, x_employee_id: str = Header(min_length=1)):
    return accessible_run(run_id=run_id, employee_id=x_employee_id)


@app.post("/api/investigations/{run_id}/policy-review", response_model=PolicyReview)
def review_policy(run_id: UUID, x_employee_id: str = Header(min_length=1)):
    # 1. Require access to the investigation before invoking the optional judge.
    run = accessible_run(run_id=run_id, employee_id=x_employee_id)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    try:
        review = evaluate_policy(
            claims=run.result.investigation.model_dump_json(), model=create_model()
        )
    except Exception:
        logger.exception("Policy review failed")
        raise HTTPException(
            status_code=502,
            detail="Policy review could not complete; investigation and approval are unchanged",
        ) from None

    # 2. Retain the separate model judgment without changing proposal authority.
    directory = RUNS_DIRECTORY / str(run_id)
    temporary = directory / f"policy-{uuid4()}.tmp"
    temporary.write_text(review.model_dump_json(indent=2))
    temporary.replace(directory / "policy-review.json")
    return review
