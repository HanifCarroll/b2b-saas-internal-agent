"""Investigate and save proposals, or review a saved proposal. Run: uv run python -m switchboard"""

import argparse
import json
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from pydantic import ValidationError

from switchboard.agent import create_model
from switchboard.demo import DemoBusyError, demo_operation, read_demo_setup, reset_demo
from switchboard.integrations.change_management import get_proposal
from switchboard.integrations.database import DATABASE_PATH
from switchboard.investigations import investigate_scenario
from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import evaluate_policy
from switchboard.scenarios import Scenario, load_scenarios
from switchboard.tools import InvestigationContext, employee_session

RUNS_DIRECTORY = DATABASE_PATH.parent / "workflows"


def review_saved_proposal(
    *, proposal_id: str, workflow_id: str, employee_id: str
) -> None:
    """Display a proposal using the shared database's current employee records."""
    # 1. Locate the investigation history and its shared database.
    try:
        run_directory = RUNS_DIRECTORY / str(UUID(workflow_id))
    except ValueError:
        raise ValueError("Invalid workflow ID") from None

    manifest_path = run_directory / "run.json"
    if not manifest_path.is_file():
        raise ValueError("Scenario run unavailable")

    manifest = json.loads(manifest_path.read_text())
    database_path = Path(manifest["database_path"])
    if not database_path.is_file():
        raise ValueError("Business database unavailable")

    # 2. Bind reviewer identity and check access through the business function.
    reviewer_context = InvestigationContext(
        database_path=database_path, employee_id=employee_id
    )
    with employee_session(reviewer_context) as session:
        proposal = get_proposal(
            session=session,
            proposal_id=proposal_id,
            database_path=Path(manifest["database_path"]),
        )

    # 3. Display only the authorized record; viewing makes no changes.
    print(proposal.model_dump_json(indent=2))
    print("\nViewing does not approve or execute the proposal.")


def display_investigation_result(
    *, result: EndpointChangeResult, workflow_id: str
) -> None:
    """Display investigation evidence, storage outcome, and review instructions."""
    # 1. Report the confirmed proposal storage outcome.
    if result.proposal is not None:
        if result.was_created:
            print(f"\nProposal created: {result.proposal.id}. Pending approval.")
        else:
            print(
                f"\nProposal already exists: {result.proposal.id}. No duplicate created."
            )

    # 2. Display tool calls and the validated investigation.
    for message in result.messages:
        for call in getattr(message, "tool_calls", []):
            print(f"Tool: {call['name']} {json.dumps(call['args'])}")

    print("\n" + result.investigation.model_dump_json(indent=2))

    # 3. Show how to review a saved proposal separately.
    if result.proposal is not None:
        print("\nInvestigation complete. Review the saved proposal separately:")
        print(
            f"uv run python -m switchboard --review {result.proposal.id} "
            f"--run {workflow_id} --employee emp-priya"
        )


def run_investigation(
    *, scenario_id: str, selected_scenario: Scenario, evaluate_policy_claims: bool
) -> None:
    """Run one investigation and display its result and optional policy review."""
    # 1. Run the shared investigation with the CLI's configured storage.
    model = create_model()
    try:
        run = investigate_scenario(
            scenario_id=scenario_id,
            model=model,
            runs_directory=RUNS_DIRECTORY,
            database_path=DATABASE_PATH,
        )
        workflow_id = run.workflow_id
        result = run.result
    except ValidationError as error:
        raise SystemExit(
            "Workflow returned invalid or inconsistent data; no result accepted.\n"
            + str(error.errors(include_input=False, include_url=False))
        ) from None
    except (ValueError, PermissionError) as error:
        raise SystemExit(f"Workflow rejected: {error}") from None

    # 2. Display the result and the separate proposal review command.
    print(f"Workflow ID: {workflow_id}")
    display_investigation_result(result=result, workflow_id=workflow_id)

    # 3. Optionally evaluate policy accuracy, without authorizing a change.
    if evaluate_policy_claims:
        review = evaluate_policy(
            claims=result.investigation.model_dump_json(), model=model
        )
        print("\nPolicy faithfulness review (model judgment):")
        print(review.model_dump_json(indent=2))

    print(
        "\nInvestigation used read-only business tools; proposal storage is reported above."
    )
    print("\nExpected outcomes for manual review (not an automated grade):")
    for expected in selected_scenario.expected:
        print(f"- {expected}")


def main():
    # 1. Parse the requested CLI operation and its options.
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios, default=None)
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--reset-demo", choices=scenarios, metavar="SCENARIO")
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Confirm deletion of all saved investigations, proposals, approvals, and executions",
    )
    parser.add_argument(
        "--evaluate-policy",
        action="store_true",
        help="Make an additional model call to review policy claims",
    )
    parser.add_argument(
        "--review", metavar="PROPOSAL_ID", help="Display a saved proposal"
    )
    parser.add_argument(
        "--run",
        metavar="WORKFLOW_ID",
        help="Investigation history identifying the shared demo",
    )
    parser.add_argument(
        "--employee", help="Simulated reviewer identity; not authentication"
    )
    args = parser.parse_args()

    # 2. Handle listing or reviewer operations before starting an investigation.
    if args.list_scenarios:
        for name, scenario in scenarios.items():
            print(f"{name}: {scenario.expected[0]}")
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
        try:
            reset_demo(
                database_path=DATABASE_PATH,
                runs_directory=RUNS_DIRECTORY,
                scenario_id=args.reset_demo,
            )
        except (DemoBusyError, ValueError) as error:
            raise SystemExit(str(error)) from None
        print(f"Demo reset to {args.reset_demo}. Saved demo work cleared.")
        return

    if args.confirm_reset:
        parser.error("--confirm-reset requires --reset-demo")

    try:
        with demo_operation(database_path=DATABASE_PATH):
            run_command(args=args, parser=parser, scenarios=scenarios)
    except DemoBusyError as error:
        raise SystemExit(str(error)) from None


def run_command(
    *,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    scenarios: dict[str, Scenario],
) -> None:
    """Dispatch a CLI read or investigation while reset is excluded."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    if args.review:
        if not args.employee or not args.run:
            parser.error("Review requires --run and --employee (simulated identity)")
        if args.evaluate_policy:
            parser.error("--evaluate-policy applies only to new investigations")

        try:
            review_saved_proposal(
                proposal_id=args.review,
                workflow_id=args.run,
                employee_id=args.employee,
            )
        except (ValueError, PermissionError) as error:
            raise SystemExit(f"Review rejected: {error}") from None

        return

    if args.employee or args.run:
        parser.error("--employee and --run are only used with --review")

    setup = read_demo_setup(DATABASE_PATH)
    if setup is None:
        parser.error("Reset the demo first: --reset-demo baseline --confirm-reset")
    scenario_id = args.scenario or setup.scenario_id
    selected_scenario = scenarios[scenario_id]

    # 3. Run the selected investigation.
    run_investigation(
        scenario_id=scenario_id,
        selected_scenario=selected_scenario,
        evaluate_policy_claims=args.evaluate_policy,
    )


if __name__ == "__main__":
    main()
