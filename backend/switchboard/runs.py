"""Read saved investigations and enforce current access independently of HTTP."""

import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import PolicyReview
from switchboard.tools import InvestigationContext, employee_session


class InvestigationRun(BaseModel):
    run_id: UUID
    scenario_id: str
    result: EndpointChangeResult
    policy_review: PolicyReview | None = None


class InvestigationSummary(BaseModel):
    run_id: UUID
    scenario_id: str
    outcome: Literal["proposal_candidate", "blocked"]


def load_run_manifest(*, runs_directory: Path, run_id: UUID) -> dict:
    """Resolve application-created run IDs, never client filesystem paths."""
    directory = runs_directory / str(run_id)
    manifest_path = directory / "run.json"
    if not manifest_path.is_file() or not (directory / "business.db").is_file():
        raise FileNotFoundError("Scenario run unavailable")

    return json.loads(manifest_path.read_text())


def require_run_access(*, context: InvestigationContext, manifest: dict) -> None:
    """Require the original requester and their current role and customer access."""
    # 1. Reject other employees and legacy manifests without an access snapshot.
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
        database_path=directory / "business.db", employee_id=employee_id
    )
    result_path = directory / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError("Investigation unavailable")

    # 2. Recheck current access before returning any saved evidence.
    require_run_access(context=context, manifest=manifest)
    saved = json.loads(result_path.read_text())
    investigation = saved["investigation"]
    if "findings" not in investigation and "summary" in investigation:
        investigation["findings"] = {
            "overview": investigation.pop("summary"),
            "checks": [],
            "policy_requirements": [],
            "gaps": ["This older report did not store separate findings sections."],
            "next_step": "See the original report above for its recommended next step.",
        }
    result = EndpointChangeResult.model_validate_json(json.dumps(saved))

    policy_path = directory / "policy-review.json"
    return InvestigationRun(
        run_id=run_id,
        scenario_id=manifest["scenario_id"],
        result=result,
        policy_review=PolicyReview.model_validate_json(policy_path.read_text())
        if policy_path.exists()
        else None,
    )


def list_investigation_runs(
    *, runs_directory: Path, employee_id: str
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

        # 2. Return a compact index; detailed evidence is loaded separately.
        runs.append(
            InvestigationSummary(
                run_id=run.run_id,
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
            database_path=directory / "business.db", employee_id=employee_id
        ),
        manifest=manifest,
    )

    # 2. Publish a complete review without changing the investigation or proposal.
    temporary = directory / f"policy-{uuid4()}.tmp"
    temporary.write_text(review.model_dump_json(indent=2))
    temporary.replace(directory / "policy-review.json")
