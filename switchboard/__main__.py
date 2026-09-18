"""Investigate, save, and pause for review. Run: uv run python -m switchboard"""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import ValidationError

from switchboard.agent import build_agent, create_model
from switchboard.integrations.change_management import get_proposal
from switchboard.integrations.database import PROPOSALS_DATABASE, seed_database
from switchboard.models import EndpointChangeResult, InvestigationResult, Proposal
from switchboard.policy_evaluation import evaluate_policy
from switchboard.scenarios import apply_scenario, load_scenarios
from switchboard.tools import InvestigationContext, employee_session
from switchboard.workflow import EndpointChangeContext, workflow

RUNS_DIRECTORY = PROPOSALS_DATABASE.parent / "workflows"


def create_checkpointer(connection: sqlite3.Connection) -> SqliteSaver:
    """Allow our validated record types when restoring saved graph state."""
    return SqliteSaver(
        connection,
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=[InvestigationResult, Proposal]
        ),
    )


def review_saved_workflow(*, workflow_id: str, employee_id: str, resume: bool) -> None:
    """Use a simulated reviewer session; never accept identity from resume content."""
    # 1. Validate the workflow ID and locate its persisted records.
    try:
        run_directory = RUNS_DIRECTORY / str(UUID(workflow_id))
    except ValueError:
        raise ValueError("Invalid workflow ID") from None
    manifest_path = run_directory / "run.json"
    if not manifest_path.exists():
        raise ValueError("Workflow unavailable")
    manifest = json.loads(manifest_path.read_text())
    proposals_path = Path(manifest["proposals_database_path"])
    database_path = run_directory / "business.db"
    config: RunnableConfig = {"configurable": {"thread_id": str(UUID(workflow_id))}}

    # 2. Restore the graph checkpoint and locate its proposal.
    with closing(
        sqlite3.connect(run_directory / "checkpoints.db", check_same_thread=False)
    ) as connection:
        graph = workflow.compile(checkpointer=create_checkpointer(connection))
        state = graph.get_state(config)
        proposal = state.values.get("proposal")
        if proposal is None:
            raise ValueError("Workflow has no proposal to review")
        # 3. Authorize the reviewer before displaying proposal details.
        reviewer_context = InvestigationContext(
            database_path=database_path, employee_id=employee_id
        )
        with employee_session(reviewer_context) as session:
            stored = get_proposal(
                session=session, proposal_id=proposal.id, database_path=proposals_path
            )
        print(stored.model_dump_json(indent=2))
        # 4. Stop for view-only requests or require a pending review pause.
        if not resume:
            print("\nViewing does not resume, approve, or execute the proposal.")
            return
        if state.next != ("review_proposal",):
            raise ValueError("Workflow is not waiting for review; nothing resumed")
        # 5. Resume with an acknowledgment and a separately bound reviewer identity.
        result = graph.invoke(
            Command(resume={"action": "acknowledge_review"}),
            config=config,
            context=EndpointChangeContext(
                agent=None,
                investigation_context=InvestigationContext(
                    database_path=database_path,
                    employee_id=manifest["requester_employee_id"],
                ),
                proposals_database_path=proposals_path,
                reviewer_employee_id=employee_id,
            ),
        )
        # 6. Validate the completed result and report that no approval occurred.
        completed = EndpointChangeResult.model_validate(result)
        print(f"\nReview acknowledged by {completed.reviewed_by_employee_id}.")
        print("Proposal remains pending approval. No configuration changes executed.")


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
    review_mode = parser.add_mutually_exclusive_group()
    review_mode.add_argument(
        "--review", metavar="WORKFLOW_ID", help="Display a saved proposal"
    )
    review_mode.add_argument(
        "--resume", metavar="WORKFLOW_ID", help="Acknowledge review; does not approve"
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
    if args.review or args.resume:
        if not args.employee:
            parser.error("Review and resume require --employee (simulated identity)")
        if args.evaluate_policy:
            parser.error("--evaluate-policy applies only to new investigations")
        try:
            review_saved_workflow(
                workflow_id=args.review or args.resume,
                employee_id=args.employee,
                resume=bool(args.resume),
            )
        except (ValueError, PermissionError) as error:
            raise SystemExit(f"Review rejected: {error}") from None
        return
    if args.employee:
        parser.error("--employee is only used with --review or --resume")
    selected_scenario = scenarios[args.scenario]

    # 3. Create isolated, durable records for this scenario run.
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
                "scenario_id": args.scenario,
                "requester_employee_id": scenario["requester_employee_id"],
                "proposals_database_path": str(PROPOSALS_DATABASE.resolve()),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Workflow ID: {workflow_id}")

    # 4. Supply trusted dependencies and persist graph progress in SQLite.
    workflow_context = EndpointChangeContext(
        agent=build_agent(model=model, now=scenario["now"]),
        investigation_context=InvestigationContext(
            database_path=database_path, employee_id=scenario["requester_employee_id"]
        ),
        proposals_database_path=PROPOSALS_DATABASE,
    )
    try:
        with closing(
            sqlite3.connect(run_directory / "checkpoints.db", check_same_thread=False)
        ) as connection:
            graph = workflow.compile(checkpointer=create_checkpointer(connection))
            raw_result = graph.invoke(
                {"request": scenario["request"]},
                context=workflow_context,
                config={
                    "configurable": {"thread_id": workflow_id},
                    "run_name": f"investigation-{args.scenario}",
                    "metadata": {"scenario_id": args.scenario},
                },
            )
        # Interrupt metadata is separate from the workflow's validated result.
        interrupts = raw_result.pop("__interrupt__", ())
        result = EndpointChangeResult.model_validate(raw_result)
    except ValidationError as error:
        raise SystemExit(
            "Workflow returned invalid or inconsistent data; no result accepted.\n"
            + str(error.errors(include_input=False, include_url=False))
        ) from None
    except (ValueError, PermissionError) as error:
        raise SystemExit(f"Workflow rejected: {error}") from None

    # 5. Display the proposal, investigation, and pause status.
    if result.proposal is not None:
        if result.was_created:
            print(f"\nProposal created: {result.proposal.id}. Pending approval.")
        else:
            print(
                f"\nProposal already exists: {result.proposal.id}. No duplicate created."
            )
    for message in result.messages:
        for call in getattr(message, "tool_calls", []):
            print(f"Tool: {call['name']} {json.dumps(call['args'])}")
    print("\n" + result.investigation.model_dump_json(indent=2))
    if interrupts:
        print("\nPaused for review. You can close this process and review later:")
        print(
            f"uv run python -m switchboard --review {workflow_id} --employee emp-priya"
        )
        print(
            f"uv run python -m switchboard --resume {workflow_id} --employee emp-priya"
        )

    # 6. Optionally evaluate policy accuracy, without authorizing a change.
    if args.evaluate_policy:
        review = evaluate_policy(
            claims=result.investigation.model_dump_json(), model=model
        )
        print("\nPolicy faithfulness review (model judgment):")
        print(review.model_dump_json(indent=2))
    print("\nVerified: business records unchanged.")
    print("\nExpected outcomes for manual review (not an automated grade):")
    for expected in selected_scenario.expected:
        print(f"- {expected}")


if __name__ == "__main__":
    main()
