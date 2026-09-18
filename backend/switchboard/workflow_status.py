"""Current workflow guidance derived from business records, never model claims."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from switchboard.integrations.change_management import get_proposal_review
from switchboard.models import Approval, EndpointChangeResult, Proposal
from switchboard.tools import InvestigationContext, employee_session


class WorkflowStatus(BaseModel):
    code: Literal[
        "blocked",
        "awaiting_approval",
        "approval_recorded",
        "approval_not_required",
        "unavailable",
    ]
    title: str
    next_action: str


def proposal_status(*, proposal: Proposal, approval: Approval | None) -> WorkflowStatus:
    """Describe recorded approval; this does not establish readiness to execute."""
    if approval is not None:
        return WorkflowStatus(
            code="approval_recorded",
            title="Approval recorded",
            next_action="Execution is not implemented yet.",
        )

    if proposal.environment == "sandbox":
        return WorkflowStatus(
            code="approval_not_required",
            title="Independent approval not required",
            next_action="Review the saved sandbox proposal. Execution is not implemented yet.",
        )

    return WorkflowStatus(
        code="awaiting_approval",
        title="Awaiting approval",
        next_action="Review the saved proposal and obtain approval from a different technical lead assigned to the customer.",
    )


def get_workflow_status(
    *,
    result: EndpointChangeResult,
    context: InvestigationContext,
    proposals_database_path: Path,
) -> WorkflowStatus:
    """Read current approval under the caller's existing access controls."""
    # 1. A blocked investigation never reaches proposal review.
    if result.investigation.outcome == "blocked":
        return WorkflowStatus(
            code="blocked",
            title="Investigation blocked",
            next_action="Resolve the reported blockers before investigating again.",
        )

    # 2. Retrieve confirmed proposal and approval records, not historical model claims.
    if result.proposal is not None:
        try:
            with employee_session(context) as session:
                proposal, approval = get_proposal_review(
                    session=session,
                    proposal_id=result.proposal.id,
                    database_path=proposals_database_path,
                )
        except PermissionError:
            pass  # Missing and inaccessible records must remain indistinguishable.
        else:
            return proposal_status(proposal=proposal, approval=approval)

    return WorkflowStatus(
        code="unavailable",
        title="Current status unavailable",
        next_action="Refresh the proposal or check access before taking further action.",
    )
