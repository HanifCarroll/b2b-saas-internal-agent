"""Investigate and save proposals, or review a saved proposal. Run: uv run python -m switchboard"""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from pydantic import ValidationError

from switchboard.agent import build_agent, create_model
from switchboard.integrations.change_management import get_proposal
from switchboard.integrations.database import PROPOSALS_DATABASE, seed_database
from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import evaluate_policy
from switchboard.scenarios import Scenario, apply_scenario, load_scenarios
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow import EndpointChangeContext, endpoint_change_graph

RUNS_DIRECTORY = PROPOSALS_DATABASE.parent / "workflows"


def review_saved_proposal(
    *, proposal_id: str, workflow_id: str, employee_id: str
) -> None:
    """Display a proposal using the selected scenario's current employee records."""
    # 1. Locate the scenario database without restoring graph state.
    try:
        run_directory = RUNS_DIRECTORY / str(UUID(workflow_id))
    except ValueError:
        raise ValueError("Invalid workflow ID") from None

    manifest_path = run_directory / "run.json"
    database_path = run_directory / "business.db"
    if not manifest_path.is_file() or not database_path.is_file():
        raise ValueError("Scenario run unavailable")

    manifest = json.loads(manifest_path.read_text())

    # 2. Bind reviewer identity and check access through the business function.
    reviewer_context = InvestigationContext(
        database_path=database_path, employee_id=employee_id
    )
    with employee_session(reviewer_context) as session:
        proposal = get_proposal(
            session=session,
            proposal_id=proposal_id,
            database_path=Path(manifest["proposals_database_path"]),
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
    # 1. Create isolated, durable records for this scenario run.
    model = create_model()
    workflow_id = str(uuid4())
    run_directory = RUNS_DIRECTORY / workflow_id
    run_directory.mkdir(parents=True)
    database_path = run_directory / "business.db"
    with closing(sqlite3.connect(database_path)) as db_connection:
        seed_database(connection=db_connection)
        scenario = apply_scenario(
            db_connection=db_connection, scenario=selected_scenario
        )

    (run_directory / "run.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "requester_employee_id": scenario["requester_employee_id"],
                "proposals_database_path": str(PROPOSALS_DATABASE.resolve()),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Workflow ID: {workflow_id}")

    # 2. Supply trusted dependencies and run the investigation to completion.
    workflow_context = EndpointChangeContext(
        agent=build_agent(model=model, now=scenario["now"]),
        investigation_context=InvestigationContext(
            database_path=database_path, employee_id=scenario["requester_employee_id"]
        ),
        proposals_database_path=PROPOSALS_DATABASE,
    )
    try:
        raw_result = endpoint_change_graph.invoke(
            {"request": scenario["request"]},
            context=workflow_context,
            config={
                "run_name": f"investigation-{scenario_id}",
                "metadata": {"scenario_id": scenario_id, "workflow_id": workflow_id},
            },
        )
        result = EndpointChangeResult.model_validate(raw_result)
    except ValidationError as error:
        raise SystemExit(
            "Workflow returned invalid or inconsistent data; no result accepted.\n"
            + str(error.errors(include_input=False, include_url=False))
        ) from None
    except (ValueError, PermissionError) as error:
        raise SystemExit(f"Workflow rejected: {error}") from None

    # 3. Display the result and the separate proposal review command.
    display_investigation_result(result=result, workflow_id=workflow_id)

    # 4. Optionally evaluate policy accuracy, without authorizing a change.
    if evaluate_policy_claims:
        review = evaluate_policy(
            claims=result.investigation.model_dump_json(), model=model
        )
        print("\nPolicy faithfulness review (model judgment):")
        print(review.model_dump_json(indent=2))

    print("\nVerified: business records unchanged.")
    print("\nExpected outcomes for manual review (not an automated grade):")
    for expected in selected_scenario.expected:
        print(f"- {expected}")


def main():
    # 1. Parse the requested CLI operation and its options.
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios, default="baseline")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument(
        "--evaluate-policy",
        action="store_true",
        help="Make an additional model call to review policy claims",
    )
    parser.add_argument(
        "--review", metavar="PROPOSAL_ID", help="Display a saved proposal"
    )
    parser.add_argument(
        "--run", metavar="WORKFLOW_ID", help="Scenario run supplying employee records"
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

    selected_scenario = scenarios[args.scenario]

    # 3. Run the selected investigation.
    run_investigation(
        scenario_id=args.scenario,
        selected_scenario=selected_scenario,
        evaluate_policy_claims=args.evaluate_policy,
    )


if __name__ == "__main__":
    main()
