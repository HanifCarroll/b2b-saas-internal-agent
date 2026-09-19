"""Synthetic scenario setup for the local demo and investigation evals."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import AwareDatetime, Field, HttpUrl, TypeAdapter

from switchboard.integrations.database import seed_database
from switchboard.models import Record, Text, Ticket

SCENARIOS = Path(__file__).resolve().parent.parent / "data" / "scenarios"


class TicketUpdates(Record):
    requested_endpoint: HttpUrl | None = None
    body: Text | None = None
    requester_contact_id: Text | None = None


class Scenario(Record):
    now: AwareDatetime | None = None
    request: Text | None = None
    ticket_updates: TicketUpdates = Field(default_factory=TicketUpdates)


def load_scenarios() -> dict[str, Scenario]:
    content = (SCENARIOS / "investigations.json").read_text()
    return TypeAdapter(dict[str, Scenario]).validate_json(content)


def apply_scenario(*, db_connection: sqlite3.Connection, scenario: Scenario) -> dict:
    """Apply setup changes only to fresh demo or test records."""
    # 1. Start from baseline inputs and apply clock or request overrides.
    inputs = json.loads((SCENARIOS / "baseline.json").read_text())
    if scenario.now is not None:
        inputs["now"] = scenario.now.isoformat()
    if scenario.request is not None:
        inputs["request"] = scenario.request

    # 2. Read and validate any ticket changes before writing them.
    updates = scenario.ticket_updates.model_dump(mode="json", exclude_none=True)
    if updates:
        row = db_connection.execute(
            "SELECT body FROM tickets WHERE id = ?", (inputs["ticket_id"],)
        ).fetchone()
        if row is None:
            raise ValueError("Scenario ticket is missing")

        ticket = json.loads(row[0])
        ticket.update(updates)
        content = json.dumps(ticket)
        Ticket.model_validate_json(content)

        # 3. Persist only the scenario ticket changes in a transaction.
        db_connection.execute("SAVEPOINT scenario_setup")
        try:
            db_connection.execute(
                "UPDATE tickets SET body = ? WHERE id = ?",
                (content, inputs["ticket_id"]),
            )
        except BaseException:
            db_connection.execute("ROLLBACK TO scenario_setup")
            db_connection.execute("RELEASE scenario_setup")
            raise
        else:
            db_connection.execute("RELEASE scenario_setup")

    return inputs


def initialize_demo_database(
    *, database_path: Path, scenario_id: str, selected_scenario: Scenario
) -> dict:
    """Initialize once; refuse scenario changes rather than overwrite shared records."""
    # 1. Serialize initialization and keep fixtures, scenario changes, and metadata atomic.
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        initialized = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'demo_setup'"
        ).fetchone()
        if initialized is None:
            seed_database(connection=connection)
            scenario = apply_scenario(
                db_connection=connection, scenario=selected_scenario
            )
            connection.execute(
                """
                CREATE TABLE demo_setup (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    scenario_id TEXT NOT NULL,
                    inputs TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO demo_setup VALUES (1, ?, ?)",
                (scenario_id, json.dumps(scenario)),
            )
        else:
            saved = connection.execute(
                "SELECT scenario_id, inputs FROM demo_setup WHERE id = 1"
            ).fetchone()
            if saved is None or saved[0] != scenario_id:
                raise ValueError("Reset the demo before selecting a different scenario")
            scenario = json.loads(saved[1])

    # 2. Reuse the stored inputs without reapplying scenario mutations.
    return scenario
