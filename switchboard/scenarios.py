"""Reviewer-only scenario setup; expected outcomes never enter the agent prompt."""

import json
import sqlite3
from pathlib import Path

from pydantic import AwareDatetime, Field, HttpUrl, TypeAdapter

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
    expected: list[Text] = Field(min_length=1)


def load_scenarios() -> dict[str, Scenario]:
    content = (SCENARIOS / "investigations.json").read_text()
    return TypeAdapter(dict[str, Scenario]).validate_json(content)


def apply_scenario(*, db_connection: sqlite3.Connection, scenario: Scenario) -> dict:
    """Modify only the fresh test database, before the read-only run begins."""
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
        with db_connection:
            db_connection.execute(
                "UPDATE tickets SET body = ? WHERE id = ?",
                (content, inputs["ticket_id"]),
            )
    return inputs
