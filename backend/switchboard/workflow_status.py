"""Current workflow guidance derived from business records, never model claims."""

from typing import Literal

from pydantic import BaseModel

from switchboard.change_management import get_proposal_review
from switchboard.investigation.tools import InvestigationContext, employee_session
from switchboard.models import (
    Approval,
    DeliveryVerification,
    EndpointChangeResult,
    Execution,
    Proposal,
)


class WorkflowStatus(BaseModel):
    code: Literal[
        "configuration_updated",
        "delivery_verified",
        "manual_intervention_required",
        "blocked",
        "awaiting_approval",
        "approval_recorded",
        "approval_not_required",
        "unavailable",
    ]
    title: str
    next_action: str


def proposal_status(
    *,
    proposal: Proposal,
    approval: Approval | None,
    execution: Execution | None = None,
    verification: DeliveryVerification | None = None,
) -> WorkflowStatus:
    """Describe recorded approval; this does not establish readiness to execute."""
    if verification is not None:
        if verification.outcome == "delivered":
            return WorkflowStatus(
                code="delivery_verified",
                title="Delivery verified",
                next_action="The synthetic event was delivered and the request is closed.",
            )
        return WorkflowStatus(
            code="manual_intervention_required",
            title="Manual intervention required",
            next_action="Review the verification evidence. Do not repeat execution or roll back automatically.",
        )

    if execution is not None:
        return WorkflowStatus(
            code="configuration_updated",
            title="Configuration updated — delivery not yet verified",
            next_action="Verify delivery separately. If verification fails, stop for manual intervention; do not repeat the configuration change.",
        )

    if approval is not None:
        return WorkflowStatus(
            code="approval_recorded",
            title="Approval recorded",
            next_action="Execute the saved proposal. The server rechecks permissions, configuration, and the production change window.",
        )

    if proposal.environment == "sandbox":
        return WorkflowStatus(
            code="approval_not_required",
            title="Independent approval not required",
            next_action="Review and execute the saved sandbox proposal. The server rechecks permissions and configuration.",
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
                proposal_review = get_proposal_review(
                    session=session, proposal_id=result.proposal.id
                )
                proposal = proposal_review.proposal
                approval = proposal_review.approval
        except PermissionError:
            pass  # Missing and inaccessible records must remain indistinguishable.
        else:
            return proposal_status(
                proposal=proposal,
                approval=approval,
                execution=proposal_review.execution,
                verification=proposal_review.verification,
            )

    return WorkflowStatus(
        code="unavailable",
        title="Current status unavailable",
        next_action="Refresh the proposal or check access before taking further action.",
    )
