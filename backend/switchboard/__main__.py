"""Investigate, review, or reset the local D1-backed Switchboard demo."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from pydantic import ValidationError

from switchboard.agent import create_model
from switchboard.demo import read_demo_setup, reset_demo
from switchboard.integrations.change_management import get_proposal
from switchboard.investigations import investigate_scenario
from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import evaluate_policy
from switchboard.runs import load_run
from switchboard.scenarios import load_scenarios
from switchboard.storage import WorkspaceStorage
from switchboard.tools import InvestigationContext, employee_session


def cli_storage() -> WorkspaceStorage:
    return WorkspaceStorage.from_environment(
        workspace_id=os.getenv("SWITCHBOARD_CLI_WORKSPACE", "cli")
    )


def review_saved_proposal(
    *, proposal_id: str, workflow_id: str, employee_id: str
) -> None:
    storage = cli_storage()
    try:
        run_id = UUID(workflow_id)
    except ValueError:
        raise ValueError("Invalid workflow ID") from None
    if load_run(storage=storage, run_id=run_id) is None:
        raise ValueError("Scenario run unavailable")

    with employee_session(
        InvestigationContext(storage=storage, employee_id=employee_id)
    ) as session:
        proposal = get_proposal(session=session, proposal_id=proposal_id)
    print(proposal.model_dump_json(indent=2))
    print("\nViewing does not approve or execute the proposal.")


def display_investigation_result(
    *, result: EndpointChangeResult, workflow_id: str
) -> None:
    if result.proposal is not None:
        outcome = "created" if result.was_created else "already exists"
        print(f"\nProposal {outcome}: {result.proposal.id}. Pending approval.")

    for message in result.messages:
        for call in getattr(message, "tool_calls", []):
            print(f"Tool: {call['name']} {json.dumps(call['args'])}")
    print("\n" + result.investigation.model_dump_json(indent=2))

    if result.proposal is not None:
        print("\nInvestigation complete. Review the saved proposal separately:")
        print(
            f"uv run python -m switchboard --review {result.proposal.id} "
            f"--run {workflow_id} --employee emp-priya"
        )


def run_investigation(*, scenario_id: str, evaluate_policy_claims: bool) -> None:
    model = create_model()
    try:
        run = investigate_scenario(
            scenario_id=scenario_id,
            model=model,
            storage=cli_storage(),
        )
    except ValidationError as error:
        raise SystemExit(
            "Workflow returned invalid or inconsistent data; no result accepted.\n"
            + str(error.errors(include_input=False, include_url=False))
        ) from None
    except (ValueError, PermissionError) as error:
        raise SystemExit(f"Workflow rejected: {error}") from None

    print(f"Workflow ID: {run.workflow_id}")
    display_investigation_result(result=run.result, workflow_id=run.workflow_id)
    if evaluate_policy_claims:
        review = evaluate_policy(
            claims=run.result.investigation.model_dump_json(), model=model
        )
        print("\nPolicy faithfulness review (model judgment):")
        print(review.model_dump_json(indent=2))


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios, default=None)
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--reset-demo", choices=scenarios, metavar="SCENARIO")
    parser.add_argument("--confirm-reset", action="store_true")
    parser.add_argument("--evaluate-policy", action="store_true")
    parser.add_argument("--review", metavar="PROPOSAL_ID")
    parser.add_argument("--run", metavar="WORKFLOW_ID")
    parser.add_argument("--employee")
    args = parser.parse_args()

    if args.list_scenarios:
        for name in scenarios:
            print(name)
        return

    if args.reset_demo:
        if (
            args.review
            or args.run
            or args.employee
            or args.scenario
            or args.evaluate_policy
        ):
            parser.error(
                "--reset-demo cannot be combined with investigation or review options"
            )
        if not args.confirm_reset:
            parser.error(
                "Reset deletes all saved demo work. Add --confirm-reset to proceed"
            )
        reset_demo(
            storage=cli_storage(),
            scenario_id=args.reset_demo,
            identity_mode="cli",
        )
        print(f"Demo reset to {args.reset_demo}. Saved demo work cleared.")
        return

    if args.confirm_reset:
        parser.error("--confirm-reset requires --reset-demo")
    if args.review:
        if not args.employee or not args.run:
            parser.error("Review requires --run and --employee (simulated identity)")
        if args.evaluate_policy:
            parser.error("--evaluate-policy applies only to new investigations")
        review_saved_proposal(
            proposal_id=args.review,
            workflow_id=args.run,
            employee_id=args.employee,
        )
        return
    if args.employee or args.run:
        parser.error("--employee and --run are only used with --review")

    setup = read_demo_setup(cli_storage())
    if setup is None:
        parser.error("Reset the demo first: --reset-demo baseline --confirm-reset")
    run_investigation(
        scenario_id=args.scenario or setup.scenario_id,
        evaluate_policy_claims=args.evaluate_policy,
    )


if __name__ == "__main__":
    main()
