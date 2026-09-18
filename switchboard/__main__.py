"""Read-only ticket investigation. Run: uv run python -m switchboard"""

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from switchboard.agent import build_agent, create_model
from switchboard.integrations.database import PROPOSALS_DATABASE, seed_database
from switchboard.models import EndpointChangeResult
from switchboard.policy_evaluation import evaluate_policy
from switchboard.scenarios import apply_scenario, load_scenarios
from switchboard.tools import InvestigationContext
from switchboard.workflow import EndpointChangeContext, endpoint_change_graph


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
        # 2. Seed the temporary business database and apply the scenario.
        database_path = Path(directory) / "switchboard.db"
        with closing(sqlite3.connect(database_path)) as db_connection:
            seed_database(db_connection)
            scenario = apply_scenario(db_connection, selected_scenario)

        # 3. Build the agent and trusted workflow context.
        agent = build_agent(model, scenario["now"])
        context = InvestigationContext(
            database_path=database_path,
            employee_id=scenario["requester_employee_id"],
        )
        workflow_context = EndpointChangeContext(
            agent=agent,
            investigation_context=context,
            proposals_database_path=PROPOSALS_DATABASE,
        )

        # 4. Run the workflow, validate its output, and report proposal status.
        try:
            raw_result = endpoint_change_graph.invoke(
                {"request": scenario["request"]},
                context=workflow_context,
                config={
                    "run_name": f"investigation-{args.scenario}",
                    "metadata": {"scenario_id": args.scenario},
                },
            )
            result = EndpointChangeResult.model_validate(raw_result)
        except ValidationError as error:
            raise SystemExit(
                "Workflow returned invalid or inconsistent data; "
                "no result accepted.\n"
                + str(error.errors(include_input=False, include_url=False))
            ) from None
        except (ValueError, PermissionError) as error:
            raise SystemExit(f"Workflow rejected: {error}") from None
        else:
            investigation = result.investigation
            proposal = result.proposal

            if proposal is not None:
                if result.was_created:
                    print(f"\nProposal created: {proposal.id}. Pending approval.")
                else:
                    print(
                        f"\nProposal already exists: {proposal.id}. "
                        "No duplicate created."
                    )

        # 5. Display tool calls and the validated investigation.
        for message in result.messages:
            for call in getattr(message, "tool_calls", []):
                print(f"Tool: {call['name']} {json.dumps(call['args'])}")
        print("\n" + investigation.model_dump_json(indent=2))

        # 6. Optionally evaluate policy accuracy with a separate model call.
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
