"""Validate scenario setup independently of live model reasoning."""

import json
import sqlite3
from contextlib import closing

import pytest

from switchboard.integrations.database import FIXTURES, seed_database
from switchboard.scenarios import apply_scenario, load_scenarios


@pytest.mark.parametrize("name", list(load_scenarios()))
def test_scenario_changes_only_its_intended_inputs(name):
    scenario = load_scenarios()[name]
    source_before = {
        path: path.read_bytes() for path in FIXTURES.rglob("*") if path.is_file()
    }
    with closing(sqlite3.connect(":memory:")) as db_connection:
        seed_database(db_connection)
        integrations_before = db_connection.execute(
            "SELECT * FROM integrations"
        ).fetchall()
        ticket_before = json.loads(
            db_connection.execute("SELECT body FROM tickets").fetchone()[0]
        )
        inputs = apply_scenario(db_connection, scenario)
        ticket_after = json.loads(
            db_connection.execute("SELECT body FROM tickets").fetchone()[0]
        )
        assert ticket_after == ticket_before | scenario.ticket_updates.model_dump(
            mode="json", exclude_none=True
        )
        assert (
            db_connection.execute("SELECT * FROM integrations").fetchall()
            == integrations_before
        )
        assert inputs["requester_employee_id"] == "emp-alex"
        assert "expected" not in inputs
        if scenario.request is not None:
            assert inputs["request"] == scenario.request
        if scenario.now is not None:
            assert inputs["now"] == scenario.now.isoformat()
    assert all(path.read_bytes() == content for path, content in source_before.items())


def test_unregistered_destination_really_is_not_registered():
    customers = json.loads((FIXTURES / "customers.json").read_text())
    acme = next(customer for customer in customers if customer["id"] == "acme")
    scenario = load_scenarios()["unregistered-destination"]
    destination = "https://new.acme.example/deals"
    assert destination in (scenario.ticket_updates.body or "")
    assert destination not in {item["url"] for item in acme["registered_destinations"]}


def test_unauthorized_contact_really_is_not_authorized():
    customers = json.loads((FIXTURES / "customers.json").read_text())
    acme = next(customer for customer in customers if customer["id"] == "acme")
    contact = load_scenarios()[
        "unauthorized-contact"
    ].ticket_updates.requester_contact_id
    assert contact not in {item["id"] for item in acme["authorized_contacts"]}
