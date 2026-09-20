"""API with isolated public demo workspaces or verified Entra authentication."""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from switchboard.agent import create_model
from switchboard.auth import get_auth_mode, get_entra_employee_id, get_entra_settings
from switchboard.delivery_verification import verify_execution_delivery
from switchboard.demo_cases import (
    DemoCaseSummary,
    PreparedDemoCase,
    list_demo_cases,
    prepare_demo_case,
)
from switchboard.demo_workspaces import DemoWorkspace, open_demo_workspace
from switchboard.integrations.change_management import (
    approve_proposal,
    execute_proposal,
    get_proposal_review,
    list_proposals_awaiting_approval,
)
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.integrations.support_desk import (
    get_ticket,
    get_ticket_details,
    list_tickets,
)
from switchboard.investigations import investigate_ticket
from switchboard.models import (
    Approval,
    DeliveryVerification,
    ExecuteProposalResult,
    Execution,
    Proposal,
    Role,
    Ticket,
    TicketDetails,
    VerifyDeliveryResult,
)
from switchboard.report_validation import ReportValidationError
from switchboard.runs import (
    InvestigationRun,
    InvestigationSummary,
    find_proposal_run_id,
    get_investigation_run,
    list_investigation_runs,
    load_run,
)
from switchboard.scenarios import initialize_demo_workspace, load_scenarios
from switchboard.storage import StorageError, WorkspaceStorage
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow_status import (
    WorkflowStatus,
    get_workflow_status,
    proposal_status,
)

logger = logging.getLogger(__name__)
DEMO_WORKSPACE_COOKIE = "switchboard-demo-workspace"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if get_auth_mode() in {"entra", "hybrid"}:
        get_entra_settings()
    yield


@dataclass(frozen=True)
class RequestContext:
    identity_mode: Literal["demo", "entra"]
    employee_id: str
    workspace_id: str
    storage: WorkspaceStorage


def get_request_context(request: Request, response: Response) -> RequestContext:
    """Resolve trusted identity and isolated D1 storage once per request."""
    auth_mode = get_auth_mode()
    has_authorization = "Authorization" in request.headers

    # 1. Bind verified Entra identity to its own durable workspace.
    if auth_mode == "entra" or (auth_mode == "hybrid" and has_authorization):
        employee_id = get_entra_employee_id(request)
        workspace_id = f"entra-{employee_id}"
        storage = WorkspaceStorage.from_environment(workspace_id=workspace_id)
        initialize_demo_workspace(
            storage=storage,
            scenario_id="baseline",
            selected_scenario=load_scenarios()["baseline"],
            identity_mode="entra",
        )
        return RequestContext(
            identity_mode="entra",
            employee_id=employee_id,
            workspace_id=workspace_id,
            storage=storage,
        )

    if has_authorization:
        raise HTTPException(status_code=400, detail="Microsoft sign-in is disabled")

    # 2. Restore or create the anonymous visitor's isolated demo workspace.
    try:
        workspace_id = UUID(request.cookies[DEMO_WORKSPACE_COOKIE])
    except (KeyError, ValueError):
        workspace_id = None
    base_storage = WorkspaceStorage.from_environment(workspace_id="new-demo")
    opened = open_demo_workspace(
        workspace_id=workspace_id,
        base_storage=base_storage,
    )
    if opened.was_created:
        response.set_cookie(
            key=DEMO_WORKSPACE_COOKIE,
            value=str(opened.workspace.id),
            max_age=24 * 60 * 60,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )

    employee_id = request.headers.get("X-Demo-Persona-Id", "emp-alex")
    try:
        EmployeeSession(
            storage=opened.workspace.storage,
            employee_id=employee_id,
        ).require_active_employee()
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Demo persona unavailable"
        ) from None

    return RequestContext(
        identity_mode="demo",
        employee_id=employee_id,
        workspace_id=str(opened.workspace.id),
        storage=opened.workspace.storage,
    )


def require_demo_context(
    context: RequestContext = Depends(get_request_context),
) -> RequestContext:
    if context.identity_mode != "demo":
        raise HTTPException(status_code=403, detail="Demo features are disabled")
    return context


app = FastAPI(title="Switchboard demo", lifespan=lifespan)


@app.exception_handler(StorageError)
def storage_error_handler(_request: Request, error: StorageError) -> JSONResponse:
    status = error.status if 400 <= error.status < 500 else 503
    return JSONResponse(status_code=status, content={"detail": str(error)})


class CurrentEmployee(BaseModel):
    employee_id: str
    name: str
    role: Role


@app.get("/api/me", response_model=CurrentEmployee)
def read_current_employee(
    context: RequestContext = Depends(get_request_context),
) -> CurrentEmployee:
    try:
        session = EmployeeSession(
            storage=context.storage, employee_id=context.employee_id
        )
        return CurrentEmployee(
            employee_id=session.employee_id,
            name=session.get_employee_name(employee_id=session.employee_id),
            role=session.get_active_employee_role(),
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None


class DemoPersona(BaseModel):
    id: str
    name: str
    role: Role


@app.get("/api/demo/personas", response_model=list[DemoPersona])
def read_demo_personas(
    context: RequestContext = Depends(require_demo_context),
) -> list[DemoPersona]:
    return [
        DemoPersona.model_validate(item)
        for item in context.storage.list_active_employees()
    ]


@app.get("/api/demo/cases", response_model=list[DemoCaseSummary])
def read_demo_cases(
    _context: RequestContext = Depends(require_demo_context),
) -> list[DemoCaseSummary]:
    return list_demo_cases()


@app.post("/api/demo/cases/{case_id}/prepare", response_model=PreparedDemoCase)
def prepare_case(
    case_id: str,
    context: RequestContext = Depends(require_demo_context),
) -> PreparedDemoCase:
    try:
        return prepare_demo_case(
            case_id=case_id,
            workspace=DemoWorkspace(
                id=UUID(context.workspace_id),
                storage=context.storage,
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


class ProposalReview(BaseModel):
    proposal: Proposal
    approval: Approval | None
    execution: Execution | None
    verification: DeliveryVerification | None
    current_status: WorkflowStatus


class ApprovalInboxItem(BaseModel):
    run_id: UUID
    proposal: Proposal


class InvestigationRequest(BaseModel):
    ticket_id: str


def review_context(
    *, run_id: UUID, request_context: RequestContext
) -> InvestigationContext:
    """Resolve only a run inside the request's already isolated workspace."""
    try:
        load_run(storage=request_context.storage, run_id=run_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Scenario run unavailable"
        ) from None
    return InvestigationContext(
        storage=request_context.storage,
        employee_id=request_context.employee_id,
    )


@app.get("/api/approvals", response_model=list[ApprovalInboxItem])
def list_pending_approvals(
    request_context: RequestContext = Depends(get_request_context),
) -> list[ApprovalInboxItem]:
    context = InvestigationContext(
        storage=request_context.storage,
        employee_id=request_context.employee_id,
    )
    try:
        with employee_session(context) as session:
            proposals = list_proposals_awaiting_approval(session=session)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None

    items = []
    for proposal in proposals:
        run_id = find_proposal_run_id(
            storage=request_context.storage,
            proposal_id=proposal.id,
        )
        if run_id is not None:
            items.append(ApprovalInboxItem(run_id=run_id, proposal=proposal))
    return items


@app.get("/api/runs/{run_id}/proposals/{proposal_id}", response_model=ProposalReview)
def read_proposal(
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> ProposalReview:
    context = review_context(run_id=run_id, request_context=request_context)
    try:
        with employee_session(context) as session:
            review = get_proposal_review(session=session, proposal_id=proposal_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Proposal unavailable") from None

    return ProposalReview(
        proposal=review.proposal,
        approval=review.approval,
        execution=review.execution,
        verification=review.verification,
        current_status=proposal_status(
            proposal=review.proposal,
            approval=review.approval,
            execution=review.execution,
            verification=review.verification,
        ),
    )


@app.post(
    "/api/runs/{run_id}/proposals/{proposal_id}/approval", response_model=Approval
)
def record_approval(
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> Approval:
    context = review_context(run_id=run_id, request_context=request_context)
    try:
        with employee_session(context) as session:
            return approve_proposal(session=session, proposal_id=proposal_id)
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
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> ExecuteProposalResult:
    context = review_context(run_id=run_id, request_context=request_context)
    try:
        with employee_session(context) as session:
            return execute_proposal(
                proposal_id=proposal_id,
                session=session,
                executed_at=datetime.now(timezone.utc),
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


@app.post(
    "/api/runs/{run_id}/proposals/{proposal_id}/verification",
    response_model=VerifyDeliveryResult,
)
def record_delivery_verification(
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> VerifyDeliveryResult:
    context = review_context(run_id=run_id, request_context=request_context)
    try:
        with employee_session(context) as session:
            return verify_execution_delivery(
                proposal_id=proposal_id,
                session=session,
                verified_at=datetime.now(timezone.utc),
            )
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Verification not permitted or proposal unavailable",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="Execution does not meet current delivery-verification requirements",
        ) from None


def _ticket_context(*, request_context: RequestContext) -> InvestigationContext:
    return InvestigationContext(
        storage=request_context.storage,
        employee_id=request_context.employee_id,
    )


def _get_accessible_ticket(
    *, ticket_id: str, request_context: RequestContext
) -> Ticket:
    try:
        with employee_session(
            _ticket_context(request_context=request_context)
        ) as session:
            return get_ticket(session=session, ticket_id=ticket_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Ticket unavailable") from None


@app.get("/api/tickets", response_model=list[TicketDetails])
def read_tickets(
    request_context: RequestContext = Depends(get_request_context),
) -> list[TicketDetails]:
    try:
        with employee_session(
            _ticket_context(request_context=request_context)
        ) as session:
            return [
                get_ticket_details(session=session, ticket=ticket)
                for ticket in list_tickets(session=session)
            ]
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None


@app.get("/api/tickets/{ticket_id}", response_model=TicketDetails)
def read_ticket(
    ticket_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> TicketDetails:
    try:
        with employee_session(
            _ticket_context(request_context=request_context)
        ) as session:
            ticket = get_ticket(session=session, ticket_id=ticket_id)
            return get_ticket_details(session=session, ticket=ticket)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Ticket unavailable") from None


@app.post("/api/investigations", response_model=InvestigationRun)
def start_investigation(
    request: InvestigationRequest,
    request_context: RequestContext = Depends(get_request_context),
) -> InvestigationRun:
    _get_accessible_ticket(ticket_id=request.ticket_id, request_context=request_context)
    try:
        run = investigate_ticket(
            ticket_id=request.ticket_id,
            employee_id=request_context.employee_id,
            model=create_model(),
            storage=request_context.storage,
            now=datetime.now(timezone.utc),
        )
    except ReportValidationError:
        logger.exception("Investigation report validation failed")
        raise HTTPException(
            status_code=502,
            detail="The investigation report could not be validated. Try again.",
        ) from None
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

    result = run.result
    return InvestigationRun(
        run_id=UUID(run.workflow_id),
        ticket_id=request.ticket_id,
        result=result,
        current_status=get_workflow_status(
            result=result,
            context=InvestigationContext(
                storage=request_context.storage,
                employee_id=request_context.employee_id,
            ),
        ),
    )


@app.get("/api/investigations", response_model=list[InvestigationSummary])
def list_investigations(
    ticket_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> list[InvestigationSummary]:
    _get_accessible_ticket(ticket_id=ticket_id, request_context=request_context)
    return list_investigation_runs(
        storage=request_context.storage,
        employee_id=request_context.employee_id,
        ticket_id=ticket_id,
    )


@app.get("/api/investigations/{run_id}", response_model=InvestigationRun)
def read_investigation(
    run_id: UUID,
    request_context: RequestContext = Depends(get_request_context),
) -> InvestigationRun:
    try:
        return get_investigation_run(
            storage=request_context.storage,
            run_id=run_id,
            employee_id=request_context.employee_id,
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None
