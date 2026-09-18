"""Local demo API. Employee headers simulate identity; they are not authentication."""

import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from switchboard.integrations.change_management import (
    approve_proposal,
    get_proposal_review,
)
from switchboard.integrations.database import PROPOSALS_DATABASE
from switchboard.models import Approval, Proposal
from switchboard.tools import InvestigationContext, employee_session

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
