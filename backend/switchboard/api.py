"""API with isolated public demo workspaces or verified Entra authentication."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from switchboard.agent import create_model
from switchboard.auth import (
    get_auth_mode,
    get_entra_settings,
    get_request_employee_id,
)
from switchboard.demo import DemoBusyError, demo_operation
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
from switchboard.integrations.database import DATABASE_PATH
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.integrations.support_desk import (
    get_ticket,
    get_ticket_details,
    list_tickets,
)
from switchboard.investigations import investigate_ticket
from switchboard.models import (
    Approval,
    ExecuteProposalResult,
    Execution,
    Proposal,
    Role,
    Ticket,
    TicketDetails,
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
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow_status import (
    WorkflowStatus,
    get_workflow_status,
    proposal_status,
)

logger = logging.getLogger(__name__)

RUNS_DIRECTORY = DATABASE_PATH.parent / "workflows"
DEMO_WORKSPACES_DIRECTORY = DATABASE_PATH.parent / "workspaces"
DEMO_WORKSPACE_COOKIE = "switchboard-demo-workspace"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if get_auth_mode() == "entra":
        get_entra_settings()
    yield


@dataclass(frozen=True)
class RequestContext:
    employee_id: str
    database_path: Path
    runs_directory: Path


def get_request_context(request: Request, response: Response) -> RequestContext:
    """Resolve trusted identity and storage once for every business request."""
    if get_auth_mode() == "entra":
        return RequestContext(
            employee_id=get_request_employee_id(request),
            database_path=DATABASE_PATH,
            runs_directory=RUNS_DIRECTORY,
        )

    try:
        workspace_id = UUID(request.cookies[DEMO_WORKSPACE_COOKIE])
    except (KeyError, ValueError):
        workspace_id = None
    opened = open_demo_workspace(
        workspace_id=workspace_id,
        root_directory=DEMO_WORKSPACES_DIRECTORY,
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
        with sqlite3.connect(opened.workspace.database_path) as connection:
            EmployeeSession(
                db_connection=connection, employee_id=employee_id
            ).require_active_employee()
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Demo persona unavailable"
        ) from None

    return RequestContext(
        employee_id=employee_id,
        database_path=opened.workspace.database_path,
        runs_directory=opened.workspace.runs_directory,
    )


def protect_demo_operation(
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    if request.method == "POST" and request.url.path.endswith("/prepare"):
        yield
        return

    try:
        with demo_operation(database_path=context.database_path):
            yield
    except DemoBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


app = FastAPI(
    title="Switchboard demo",
    lifespan=lifespan,
    dependencies=[Depends(protect_demo_operation)],
)


class CurrentEmployee(BaseModel):
    employee_id: str
    name: str
    role: Role


@app.get("/api/me", response_model=CurrentEmployee)
def read_current_employee(
    context: RequestContext = Depends(get_request_context),
) -> CurrentEmployee:
    investigation_context = InvestigationContext(
        database_path=context.database_path, employee_id=context.employee_id
    )
    try:
        with employee_session(investigation_context) as session:
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
    context: RequestContext = Depends(get_request_context),
) -> list[DemoPersona]:
    with sqlite3.connect(context.database_path) as connection:
        rows = connection.execute(
            "SELECT id, name, role FROM employees WHERE active = 1 ORDER BY id"
        ).fetchall()
    return [DemoPersona(id=row[0], name=row[1], role=row[2]) for row in rows]


@app.get("/api/demo/cases", response_model=list[DemoCaseSummary])
def read_demo_cases() -> list[DemoCaseSummary]:
    return list_demo_cases()


@app.post("/api/demo/cases/{case_id}/prepare", response_model=PreparedDemoCase)
def prepare_case(
    case_id: str,
    context: RequestContext = Depends(get_request_context),
) -> PreparedDemoCase:
    if get_auth_mode() != "demo":
        raise HTTPException(status_code=403, detail="Demo case preparation is disabled")
    try:
        return prepare_demo_case(
            case_id=case_id,
            workspace=DemoWorkspace(
                id=UUID(context.database_path.parent.name),
                database_path=context.database_path,
                runs_directory=context.runs_directory,
            ),
        )
    except DemoBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


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


def review_context(
    *, run_id: UUID, request_context: RequestContext
) -> InvestigationContext:
    """Resolve only application-created run manifests, never client filesystem paths."""
    try:
        manifest = load_run_manifest(
            runs_directory=request_context.runs_directory, run_id=run_id
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Scenario run unavailable"
        ) from None

    database_path = Path(manifest["database_path"])
    if database_path.resolve() != request_context.database_path.resolve():
        raise HTTPException(status_code=404, detail="Scenario run unavailable")
    return InvestigationContext(
        database_path=database_path, employee_id=request_context.employee_id
    )


@app.get("/api/approvals", response_model=list[ApprovalInboxItem])
def list_pending_approvals(
    request_context: RequestContext = Depends(get_request_context),
) -> list[ApprovalInboxItem]:
    """List completed proposals this employee may independently approve."""
    context = InvestigationContext(
        database_path=request_context.database_path,
        employee_id=request_context.employee_id,
    )
    try:
        with employee_session(context) as session:
            proposals = list_proposals_awaiting_approval(
                session=session,
                database_path=request_context.database_path,
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Employee unavailable") from None

    items = []
    for proposal in proposals:
        run_id = find_proposal_run_id(
            runs_directory=request_context.runs_directory,
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
    # 1. Resolve application storage and authenticated or demo employee context.
    context = review_context(run_id=run_id, request_context=request_context)

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
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> Approval:
    # 1. Resolve application storage and authenticated or demo employee context.
    context = review_context(run_id=run_id, request_context=request_context)

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
    run_id: UUID,
    proposal_id: str,
    request_context: RequestContext = Depends(get_request_context),
) -> ExecuteProposalResult:
    """Execute through deterministic checks; a receipt does not verify delivery."""
    # 1. Resolve application storage and authenticated or demo employee identity.
    context = review_context(run_id=run_id, request_context=request_context)

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


def _ticket_context(*, request_context: RequestContext) -> InvestigationContext:
    return InvestigationContext(
        database_path=request_context.database_path,
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
    # 1. Reject unavailable tickets before creating a model client or spending tokens.
    _get_accessible_ticket(ticket_id=request.ticket_id, request_context=request_context)

    # 2. Run the workflow with server time and the authenticated employee identity.
    try:
        run = investigate_ticket(
            ticket_id=request.ticket_id,
            employee_id=request_context.employee_id,
            model=create_model(),
            runs_directory=request_context.runs_directory,
            database_path=request_context.database_path,
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
                database_path=request_context.database_path,
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
        runs_directory=request_context.runs_directory,
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
            runs_directory=request_context.runs_directory,
            run_id=run_id,
            employee_id=request_context.employee_id,
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None


@app.post("/api/investigations/{run_id}/policy-review", response_model=PolicyReview)
def review_policy(
    run_id: UUID,
    request_context: RequestContext = Depends(get_request_context),
) -> PolicyReview:
    # 1. Require access to the investigation before invoking the optional judge.
    run = read_investigation(run_id=run_id, request_context=request_context)
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
            runs_directory=request_context.runs_directory,
            run_id=run_id,
            employee_id=request_context.employee_id,
            review=review,
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404, detail="Investigation unavailable"
        ) from None

    return review
