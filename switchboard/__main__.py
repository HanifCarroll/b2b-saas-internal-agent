"""Read-only ticket investigation. Run: uv run python -m switchboard"""

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from switchboard.agent import build_agent, create_model
from switchboard.integrations.change_management import save_proposal
from switchboard.integrations.database import PROPOSALS_DATABASE, seed_database
from switchboard.models import InvestigationResult
from switchboard.policy_evaluation import evaluate_policy
from switchboard.proposals import validate_proposal
from switchboard.scenarios import apply_scenario, load_scenarios
from switchboard.tools import InvestigationContext, employee_session


def main():
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios, default="baseline")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument(
        "--evaluate-policy",
        action="store_true",
        help="Make an additional model call to review policy claims",
    )
    args = parser.parse_args()
    if args.list_scenarios:
        for name, scenario in scenarios.items():
            print(f"{name}: {scenario.expected[0]}")
        return
    selected_scenario = scenarios[args.scenario]

    # 1. Setup: load credentials, scenario, and model settings.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    model = create_model()

    with tempfile.TemporaryDirectory() as directory:
        # 2. Seed: create a temporary database and capture its initial state.
        database_path = Path(directory) / "switchboard.db"
        with closing(sqlite3.connect(database_path)) as db_connection:
            seed_database(db_connection)
            scenario = apply_scenario(db_connection, selected_scenario)
            database_before = list(db_connection.iterdump())

        # 3. Investigate: bind the employee context and run the read-only agent.
        agent = build_agent(model, scenario["now"])
        context = InvestigationContext(
            database_path=database_path,
            employee_id=scenario["requester_employee_id"],
        )
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=scenario["request"])]},
                context=context,
                config={
                    "recursion_limit": 12,
                    "run_name": f"investigation-{args.scenario}",
                    "metadata": {"scenario_id": args.scenario},
                },
            )
        finally:
            # 4. Verify even if the model or a tool fails.
            with closing(sqlite3.connect(database_path)) as db_connection:
                database_after = list(db_connection.iterdump())
            if database_after != database_before:
                raise RuntimeError("Investigation changed business records")

        # 5. Validate the final JSON before accepting or displaying the result.
        try:
            investigation = InvestigationResult.model_validate_json(
                result["messages"][-1].text
            )
        except ValidationError as error:
            raise SystemExit(
                "Investigation returned invalid JSON or inconsistent fields; "
                "no result accepted. Business records are unchanged.\n"
                + str(error.errors(include_input=False, include_url=False))
            ) from None

        # 6. Validate and save a proposal if the outcome is proposal_candidate.
        if investigation.outcome == "proposal_candidate":
            try:
                with employee_session(context) as session:
                    proposal = validate_proposal(investigation, session)
                    proposal, was_created = save_proposal(
                        proposal, session, PROPOSALS_DATABASE
                    )
            except (ValueError, PermissionError) as error:
                raise SystemExit(f"Proposal rejected; nothing saved: {error}") from None
            else:
                if was_created:
                    print(f"\nProposal created: {proposal.id}. Pending approval.")
                else:
                    print(
                        f"\nProposal already exists: {proposal.id}. No duplicate created."
                    )

        # 7. Display tool calls and the validated investigation.
        for message in result["messages"]:
            for call in getattr(message, "tool_calls", []):
                print(f"Tool: {call['name']} {json.dumps(call['args'])}")
        print("\n" + investigation.model_dump_json(indent=2))

        # 8. Optionally evaluate policy accuracy with a separate model call.
        if args.evaluate_policy:
            review = evaluate_policy(investigation.model_dump_json(), model)
            print("\nPolicy faithfulness review (model judgment):")
            print(review.model_dump_json(indent=2))

        print("\nVerified: business records unchanged.")
        print("\nExpected outcomes for manual review (not an automated grade):")
        for expected in selected_scenario.expected:
            print(f"- {expected}")


if __name__ == "__main__":
    main()
