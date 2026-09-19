"""Read saved investigations and enforce current access independently of HTTP."""

import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import PolicyReview
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow_status import WorkflowStatus, get_workflow_status


class InvestigationRun(BaseModel):
    run_id: UUID
    ticket_id: str
    scenario_id: str | None = None
    result: EndpointChangeResult
    current_status: WorkflowStatus
    policy_review: PolicyReview | None = None


class InvestigationSummary(BaseModel):
    run_id: UUID
    ticket_id: str
    scenario_id: str | None = None
    outcome: Literal["proposal_candidate", "blocked"]


def find_proposal_run_id(*, runs_directory: Path, proposal_id: str) -> UUID | None:
    """Find the completed application run that saved a proposal."""
    for result_path in runs_directory.glob("*/result.json"):
        result = EndpointChangeResult.model_validate_json(result_path.read_text())
        if result.proposal and result.proposal.id == proposal_id:
            return UUID(result_path.parent.name)

    return None


def load_run_manifest(*, runs_directory: Path, run_id: UUID) -> dict:
    """Resolve application-created run IDs, never client filesystem paths."""
    directory = runs_directory / str(run_id)
    manifest_path = directory / "run.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Scenario run unavailable")

    manifest = json.loads(manifest_path.read_text())
    if not Path(manifest["database_path"]).is_file():
        raise FileNotFoundError("Business database unavailable")
    return manifest


def require_run_access(*, context: InvestigationContext, manifest: dict) -> None:
    """Require the original requester and their current role and customer access."""
    # 1. Require the original employee and a complete access snapshot.
    if manifest.get("requester_employee_id") != context.employee_id:
        raise PermissionError("Investigation unavailable")

    if "requester_role" not in manifest or "customer_ids" not in manifest:
        raise PermissionError("Investigation unavailable")

    # 2. Recheck the employee against current business records.
    with employee_session(context) as session:
        if session.get_active_employee_role() != manifest["requester_role"]:
            raise PermissionError("Investigation unavailable")

        for customer_id in manifest["customer_ids"]:
            session.require_customer_access(
                customer_id=customer_id, allowed_roles={manifest["requester_role"]}
            )


def get_investigation_run(
    *, runs_directory: Path, run_id: UUID, employee_id: str
) -> InvestigationRun:
    """Restrict investigation history to its requester with current record access."""
    # 1. Locate the manifest and completed result.
    directory = runs_directory / str(run_id)
    manifest = load_run_manifest(runs_directory=runs_directory, run_id=run_id)
    context = InvestigationContext(
        database_path=Path(manifest["database_path"]), employee_id=employee_id
    )
    result_path = directory / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError("Investigation unavailable")

    # 2. Recheck current access before returning any saved evidence.
    require_run_access(context=context, manifest=manifest)
    result = EndpointChangeResult.model_validate_json(result_path.read_text())

    policy_path = directory / "policy-review.json"
    return InvestigationRun(
        run_id=run_id,
        ticket_id=manifest["ticket_id"],
        scenario_id=manifest.get("scenario_id"),
        result=result,
        current_status=get_workflow_status(
            result=result,
            context=context,
        ),
        policy_review=PolicyReview.model_validate_json(policy_path.read_text())
        if policy_path.exists()
        else None,
    )


def list_investigation_runs(
    *, runs_directory: Path, employee_id: str, ticket_id: str
) -> list[InvestigationSummary]:
    # 1. Read only completed runs accessible to this employee.
    runs = []
    for path in sorted(
        runs_directory.glob("*/result.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            run = get_investigation_run(
                runs_directory=runs_directory,
                run_id=UUID(path.parent.name),
                employee_id=employee_id,
            )
        except (FileNotFoundError, PermissionError):
            continue

        if run.ticket_id != ticket_id:
            continue

        # 2. Return a compact index; detailed evidence is loaded separately.
        runs.append(
            InvestigationSummary(
                run_id=run.run_id,
                ticket_id=run.ticket_id,
                scenario_id=run.scenario_id,
                outcome=run.result.investigation.outcome,
            )
        )
    return runs


def save_policy_review(
    *, runs_directory: Path, run_id: UUID, employee_id: str, review: PolicyReview
) -> None:
    """Recheck access and atomically save the separate model judgment."""
    # 1. Recheck access because evaluation may have taken time.
    directory = runs_directory / str(run_id)
    manifest = load_run_manifest(runs_directory=runs_directory, run_id=run_id)
    require_run_access(
        context=InvestigationContext(
            database_path=Path(manifest["database_path"]), employee_id=employee_id
        ),
        manifest=manifest,
    )

    # 2. Publish a complete review without changing the investigation or proposal.
    temporary = directory / f"policy-{uuid4()}.tmp"
    temporary.write_text(review.model_dump_json(indent=2))
    temporary.replace(directory / "policy-review.json")
