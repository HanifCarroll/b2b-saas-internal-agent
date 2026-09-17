"""Read-only ticket investigation. Run: uv run python -m switchboard"""

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from switchboard.agent import build_agent, create_model
from switchboard.integrations.database import seed_database
from switchboard.scenarios import apply_scenario, load_scenarios
from switchboard.tools import InvestigationContext


def main():
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios, default="baseline")
    parser.add_argument("--list-scenarios", action="store_true")
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
                {"messages": [{"role": "user", "content": scenario["request"]}]},
                context=context,
                config={
                    "recursion_limit": 12,
                    "run_name": f"investigation-{args.scenario}",
                    "metadata": {"scenario_id": args.scenario},
                },
            )
        except PermissionError:
            print("Investigation stopped: access denied or record unavailable.")
            result = None
        finally:
            # 4. Verify even if the model or a tool fails.
            with closing(sqlite3.connect(database_path)) as db_connection:
                database_after = list(db_connection.iterdump())
            if database_after != database_before:
                raise RuntimeError("Investigation changed business records")

        # 5. Display: show tool calls, the final report, and the verification result.
        if result is not None:
            for message in result["messages"]:
                for call in getattr(message, "tool_calls", []):
                    print(f"Tool: {call['name']} {json.dumps(call['args'])}")
            print("\n" + result["messages"][-1].text)

        print("\nVerified: business records unchanged.")
        print("\nExpected outcomes for manual review (not an automated grade):")
        for expected in selected_scenario.expected:
            print(f"- {expected}")


if __name__ == "__main__":
    main()
