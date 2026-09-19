"""API with explicit demo identity or verified Entra authentication."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, StrictBool

from switchboard.agent import create_model
from switchboard.auth import (
    get_auth_mode,
    get_entra_settings,
    get_request_employee_id,
    require_api_authentication,
)
from switchboard.demo import DemoBusyError, demo_operation, read_demo_setup, reset_demo
from switchboard.integrations.change_management import (
    approve_proposal,
    execute_proposal,
    get_proposal_review,
    list_proposals_awaiting_approval,
)
from switchboard.integrations.database import DATABASE_PATH, FIXTURES
from switchboard.integrations.support_desk import get_ticket, list_tickets
from switchboard.investigations import investigate_ticket
from switchboard.models import (
    Approval,
    ExecuteProposalResult,
    Execution,
    Proposal,
    Role,
    Ticket,
)
from switchboard.policy_evaluation import PolicyReview, evaluate_policy
from switchboard.runs import (
    InvestigationRun,
    InvestigationSummary,
    find_proposal_run_id,
    get_investigation_run,
    list_investigation_runs,
    load_run_manifest,
    save_policy_review,
)
from switchboard.scenarios import load_scenarios
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow_status import (
    WorkflowStatus,
    get_workflow_status,
    proposal_status,
)

logger = logging.getLogger(__name__)

RUNS_DIRECTORY = DATABASE_PATH.parent / "workflows"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if get_auth_mode() == "entra":
        get_entra_settings()
    yield


def protect_demo_operation(request: Request):
    if request.url.path == "/api/demo/reset":
        yield
        return

    try:
        with demo_operation(database_path=DATABASE_PATH):
            yield
    except DemoBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


app = FastAPI(
    title="Switchboard local demo",
    lifespan=lifespan,
    dependencies=[Depends(require_api_authentication), Depends(protect_demo_operation)],
)


class CurrentEmployee(BaseModel):
    employee_id: str
    role: Role


@app.get("/api/me", response_model=CurrentEmployee)
def read_current_employee(
    employee_id: str = Depends(get_request_employee_id),
) -> CurrentEmployee:
    context = InvestigationContext(database_path=DATABASE_PATH, employee_id=employee_id)
    try:
        with employee_session(context) as session:
            return CurrentEmployee(
                employee_id=session.employee_id,
                role=session.get_active_employee_role(),
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None


class DemoState(BaseModel):
    scenario_id: str | None


class ResetRequest(BaseModel):
    scenario_id: str
    confirm: StrictBool


@app.get("/api/demo", response_model=DemoState)
def read_demo() -> DemoState:
    setup = read_demo_setup(DATABASE_PATH)
    return DemoState(scenario_id=setup.scenario_id if setup else None)


@app.post("/api/demo/reset", response_model=DemoState)
def reset_demo_state(request: ResetRequest) -> DemoState:
    # 1. Allow destructive resets only in explicit demo mode with confirmation.
    if get_auth_mode() != "demo":
        raise HTTPException(
            status_code=403, detail="HTTP reset is disabled in Entra mode"
        )

    if not request.confirm:
        raise HTTPException(
            status_code=422, detail="Confirm deletion of all saved demo work"
        )

    # 2. Reset synthetic records and history under the existing reset lock.
    try:
        reset_demo(
            database_path=DATABASE_PATH,
            runs_directory=RUNS_DIRECTORY,
            scenario_id=request.scenario_id,
        )
    except DemoBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return DemoState(scenario_id=request.scenario_id)


class ProposalReview(BaseModel):
    proposal: Proposal
    approval: Approval | None
    execution: Execution | None
    current_status: WorkflowStatus


class ApprovalInboxItem(BaseModel):
    run_id: UUID
    proposal: Proposal


class InvestigationRequest(BaseModel):
    ticket_id: str


class ScenarioOption(BaseModel):
    id: str


class EmployeeOption(BaseModel):
    id: str
    name: str
    role: Role


class DemoOptions(BaseModel):
    scenarios: list[ScenarioOption]
    employees: list[EmployeeOption]


def review_context(*, run_id: UUID, employee_id: str) -> InvestigationContext:
    """Resolve only application-created run manifests, never client filesystem paths."""
    try:
        manifest = load_run_manifest(runs_directory=RUNS_DIRECTORY, run_id=run_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Scenario run unavailable"
        ) from None

    database_path = Path(manifest["database_path"])
    return InvestigationContext(database_path=database_path, employee_id=employee_id)


@app.get("/api/approvals", response_model=list[ApprovalInboxItem])
def list_pending_approvals(
    employee_id: str = Depends(get_request_employee_id),
) -> list[ApprovalInboxItem]:
    """List completed proposals this employee may independently approve."""
    context = InvestigationContext(database_path=DATABASE_PATH, employee_id=employee_id)
    try:
        with employee_session(context) as session:
            proposals = list_proposals_awaiting_approval(
                session=session,
                database_path=DATABASE_PATH,
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None

    items = []
    for proposal in proposals:
        run_id = find_proposal_run_id(
            runs_directory=RUNS_DIRECTORY,
            proposal_id=proposal.id,
        )
        if run_id is not None:
            items.append(ApprovalInboxItem(run_id=run_id, proposal=proposal))

    return items


@app.get("/api/runs/{run_id}/proposals/{proposal_id}", response_model=ProposalReview)
def read_proposal(
    run_id: UUID, proposal_id: str, employee_id: str = Depends(get_request_employee_id)
) -> ProposalReview:
    # 1. Resolve application storage and authenticated or demo employee context.
    context = review_context(run_id=run_id, employee_id=employee_id)

    # 2. Delegate authorization and storage to the business functions.
    try:
        with employee_session(context) as session:
            proposal_review = get_proposal_review(
                session=session,
                proposal_id=proposal_id,
                database_path=context.database_path,
            )
            proposal = proposal_review.proposal
            approval = proposal_review.approval
    except PermissionError:
        raise HTTPException(status_code=404, detail="Proposal unavailable") from None

    return ProposalReview(
        proposal=proposal,
        approval=approval,
        execution=proposal_review.execution,
        current_status=proposal_status(
            proposal=proposal, approval=approval, execution=proposal_review.execution
        ),
    )


@app.post(
    "/api/runs/{run_id}/proposals/{proposal_id}/approval", response_model=Approval
)
def record_approval(
    run_id: UUID, proposal_id: str, employee_id: str = Depends(get_request_employee_id)
) -> Approval:
    # 1. Resolve application storage and authenticated or demo employee context.
    context = review_context(run_id=run_id, employee_id=employee_id)

    # 2. Delegate authorization and storage to the business functions.
    try:
        with employee_session(context) as session:
            return approve_proposal(
                session=session,
                proposal_id=proposal_id,
                database_path=context.database_path,
            )
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Approval not permitted or proposal unavailable"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=409, detail="Proposal is not eligible for independent approval"
        ) from None


@app.post(
    "/api/runs/{run_id}/proposals/{proposal_id}/execution",
    response_model=ExecuteProposalResult,
)
def record_execution(
    run_id: UUID, proposal_id: str, employee_id: str = Depends(get_request_employee_id)
) -> ExecuteProposalResult:
    """Execute through deterministic checks; a receipt does not verify delivery."""
    # 1. Resolve application storage and authenticated or demo employee identity.
    context = review_context(run_id=run_id, employee_id=employee_id)

    # 2. Supply server time and delegate the atomic change to the business function.
    try:
        with employee_session(context) as session:
            return execute_proposal(
                proposal_id=proposal_id,
                session=session,
                executed_at=datetime.now(timezone.utc),
                database_path=context.database_path,
            )
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Execution not permitted or proposal unavailable"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="Proposal does not meet current execution requirements",
        ) from None


@app.get("/api/demo-options", response_model=DemoOptions)
def demo_options() -> DemoOptions:
    """Expose synthetic demo choices, never secrets or provider configuration."""
    employees = json.loads((FIXTURES / "employees.json").read_text())
    return DemoOptions(
        scenarios=[ScenarioOption(id=key) for key in load_scenarios()],
        employees=[
            EmployeeOption(id=item["id"], name=item["name"], role=item["role"])
            for item in employees
            if item["active"]
        ],
    )


def _ticket_context(*, employee_id: str) -> InvestigationContext:
    return InvestigationContext(database_path=DATABASE_PATH, employee_id=employee_id)


def _get_accessible_ticket(*, ticket_id: str, employee_id: str) -> Ticket:
    try:
        with employee_session(_ticket_context(employee_id=employee_id)) as session:
            return get_ticket(session=session, ticket_id=ticket_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Ticket unavailable") from None


@app.get("/api/tickets", response_model=list[Ticket])
def read_tickets(
    employee_id: str = Depends(get_request_employee_id),
) -> list[Ticket]:
    try:
        with employee_session(_ticket_context(employee_id=employee_id)) as session:
            return list_tickets(session=session)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None


@app.get("/api/tickets/{ticket_id}", response_model=Ticket)
def read_ticket(
    ticket_id: str, employee_id: str = Depends(get_request_employee_id)
) -> Ticket:
    return _get_accessible_ticket(ticket_id=ticket_id, employee_id=employee_id)


@app.post("/api/investigations", response_model=InvestigationRun)
def start_investigation(
    request: InvestigationRequest, employee_id: str = Depends(get_request_employee_id)
) -> InvestigationRun:
    # 1. Reject unavailable tickets before creating a model client or spending tokens.
    _get_accessible_ticket(ticket_id=request.ticket_id, employee_id=employee_id)

    # 2. Run the workflow with server time and the authenticated employee identity.
    try:
        run = investigate_ticket(
            ticket_id=request.ticket_id,
            employee_id=employee_id,
            model=create_model(),
            runs_directory=RUNS_DIRECTORY,
            database_path=DATABASE_PATH,
            now=datetime.now(timezone.utc),
        )
        run_id = run.workflow_id
        result = run.result
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
        run_id=UUID(run_id),
        ticket_id=request.ticket_id,
        result=result,
        current_status=get_workflow_status(
            result=result,
            context=InvestigationContext(
                database_path=DATABASE_PATH,
                employee_id=employee_id,
            ),
        ),
    )


@app.get("/api/investigations", response_model=list[InvestigationSummary])
def list_investigations(
    ticket_id: str,
    employee_id: str = Depends(get_request_employee_id),
) -> list[InvestigationSummary]:
    _get_accessible_ticket(ticket_id=ticket_id, employee_id=employee_id)
    return list_investigation_runs(
        runs_directory=RUNS_DIRECTORY,
        employee_id=employee_id,
        ticket_id=ticket_id,
    )


@app.get("/api/investigations/{run_id}", response_model=InvestigationRun)
def read_investigation(
    run_id: UUID, employee_id: str = Depends(get_request_employee_id)
) -> InvestigationRun:
    try:
        return get_investigation_run(
            runs_directory=RUNS_DIRECTORY, run_id=run_id, employee_id=employee_id
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None


@app.post("/api/investigations/{run_id}/policy-review", response_model=PolicyReview)
def review_policy(
    run_id: UUID, employee_id: str = Depends(get_request_employee_id)
) -> PolicyReview:
    # 1. Require access to the investigation before invoking the optional judge.
    run = read_investigation(run_id=run_id, employee_id=employee_id)
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
    try:
        save_policy_review(
            runs_directory=RUNS_DIRECTORY,
            run_id=run_id,
            employee_id=employee_id,
            review=review,
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None

    return review
