"""Validate scenario setup independently of live model reasoning."""

import json
import sqlite3
from contextlib import closing

import pytest

from switchboard.integrations.database import FIXTURES, seed_database
from switchboard.scenarios import apply_scenario, load_scenarios


@pytest.mark.parametrize("name", list(load_scenarios()))
def test_scenario_changes_only_its_intended_inputs(name):
    # 1. Set up inputs and exercise the behavior under test.
    scenario = load_scenarios()[name]
    source_before = {
        path: path.read_bytes() for path in FIXTURES.rglob("*") if path.is_file()
    }
    with closing(sqlite3.connect(":memory:")) as db_connection:
        seed_database(connection=db_connection)
        integrations_before = db_connection.execute(
            "SELECT * FROM integrations"
        ).fetchall()
        ticket_before = json.loads(
            db_connection.execute("SELECT body FROM tickets").fetchone()[0]
        )
        inputs = apply_scenario(db_connection=db_connection, scenario=scenario)
        ticket_after = json.loads(
            db_connection.execute("SELECT body FROM tickets").fetchone()[0]
        )

        # 2. Verify the expected result and any safety guarantees.
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


def test_shared_setup_reuses_records_and_rejects_scenario_switch(tmp_path):
    from switchboard.scenarios import initialize_demo_database

    path = tmp_path / "switchboard.db"
    scenarios = load_scenarios()
    inputs = initialize_demo_database(
        database_path=path,
        scenario_id="baseline",
        selected_scenario=scenarios["baseline"],
    )
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "UPDATE tickets SET body = json_set(body, '$.subject', 'Changed after investigation')"
        )

    assert (
        initialize_demo_database(
            database_path=path,
            scenario_id="baseline",
            selected_scenario=scenarios["baseline"],
        )
        == inputs
    )
    with closing(sqlite3.connect(path)) as connection:
        before = list(connection.iterdump())
        assert (
            "Changed after investigation"
            in connection.execute("SELECT body FROM tickets LIMIT 1").fetchone()[0]
        )

    with pytest.raises(ValueError, match="Reset the demo"):
        initialize_demo_database(
            database_path=path,
            scenario_id="unregistered-destination",
            selected_scenario=scenarios["unregistered-destination"],
        )

    with closing(sqlite3.connect(path)) as connection:
        assert list(connection.iterdump()) == before


def test_failed_shared_setup_rolls_back_all_tables(tmp_path, monkeypatch):
    from switchboard import scenarios

    path = tmp_path / "switchboard.db"

    def fail(**kwargs):
        raise ValueError("Setup interrupted")

    monkeypatch.setattr(scenarios, "apply_scenario", fail)
    with pytest.raises(ValueError, match="Setup interrupted"):
        scenarios.initialize_demo_database(
            database_path=path,
            scenario_id="baseline",
            selected_scenario=scenarios.load_scenarios()["baseline"],
        )

    with closing(sqlite3.connect(path)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            == []
        )
