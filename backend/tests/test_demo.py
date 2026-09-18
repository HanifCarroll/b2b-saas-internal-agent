"""Explicit reset clears saved work and cannot overlap application operations."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from switchboard import __main__ as cli
from switchboard import api
from switchboard.demo import demo_operation, read_demo_setup, reset_demo


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "demo")
    path = tmp_path / "switchboard.db"
    runs = tmp_path / "workflows"
    for module in (api, cli):
        monkeypatch.setattr(module, "DATABASE_PATH", path)
        monkeypatch.setattr(module, "RUNS_DIRECTORY", runs)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    return path, runs, TestClient(api.app)


def test_investigation_requires_explicit_setup_without_model_call(demo, monkeypatch):
    path, _, client = demo

    def unexpected():
        raise AssertionError("Must not construct a model before setup")

    monkeypatch.setattr(api, "create_model", unexpected)
    assert client.get("/api/demo").json() == {"scenario_id": None}
    response = client.post(
        "/api/investigations",
        json={"scenario_id": "baseline"},
        headers={"X-Employee-Id": "emp-alex"},
    )
    assert response.status_code == 409
    assert not path.exists()


@pytest.mark.parametrize("confirm", [False, None, "true"])
def test_reset_requires_explicit_boolean_confirmation(demo, confirm):
    path, _, client = demo
    response = client.post(
        "/api/demo/reset", json={"scenario_id": "baseline", "confirm": confirm}
    )
    assert response.status_code == 422
    assert not path.exists()


def test_reset_clears_business_work_and_history(demo):
    path, runs, client = demo
    reset_demo(database_path=path, runs_directory=runs, scenario_id="baseline")
    history = runs / "old-run"
    history.mkdir(parents=True)
    (history / "result.json").write_text("{}")
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "UPDATE integrations SET body = json_set(body, '$.version', 99)"
        )
        # The reset must clear all workflow tables, not just configuration.
        from test_proposal import PROPOSAL

        from switchboard.models import Proposal

        proposal = Proposal.model_validate_json(json.dumps(PROPOSAL)).model_dump(
            mode="json"
        )
        names = ", ".join(proposal)
        placeholders = ", ".join(":" + key for key in proposal)
        connection.execute(
            f"INSERT INTO proposals ({names}) VALUES ({placeholders})", proposal
        )
        connection.execute(
            "INSERT INTO approvals VALUES ('approval-1', 'proposal-001', 'emp-priya', '2026-09-22T14:00:00Z')"
        )
        connection.execute(
            "INSERT INTO executions VALUES ('execution-1', 'proposal-001', 'emp-alex', 'approval-1', '2026-09-22T14:00:00Z', 7, 8)"
        )

    response = client.post(
        "/api/demo/reset",
        json={"scenario_id": "unregistered-destination", "confirm": True},
    )
    assert response.status_code == 200
    assert client.get("/api/demo").json()["scenario_id"] == "unregistered-destination"
    assert not runs.exists()
    with closing(sqlite3.connect(path)) as connection:
        for table in ("proposals", "approvals", "executions"):
            assert (
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
            )
        assert (
            connection.execute(
                "SELECT json_extract(body, '$.version') FROM integrations WHERE id = 'int-acme-prod'"
            ).fetchone()[0]
            == 7
        )
        assert (
            connection.execute(
                "SELECT json_extract(body, '$.requested_endpoint') FROM tickets WHERE id = 'CHG-1042'"
            ).fetchone()[0]
            == "https://new.acme.example/deals"
        )


def test_reset_is_rejected_while_an_operation_is_active_across_processes(demo):
    path, runs, client = demo
    reset_demo(database_path=path, runs_directory=runs, scenario_id="baseline")
    before = path.read_bytes()
    with demo_operation(database_path=path):
        response = client.post(
            "/api/demo/reset", json={"scenario_id": "baseline", "confirm": True}
        )
        assert response.status_code == 409
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; from switchboard.demo import reset_demo; "
                "import sys; reset_demo(database_path=Path(sys.argv[1]), runs_directory=Path(sys.argv[2]), scenario_id='baseline')",
                str(path),
                str(runs),
            ],
            capture_output=True,
            text=True,
        )
        assert process.returncode != 0
        assert "Demo is busy" in process.stderr
    assert path.read_bytes() == before


def test_operations_are_rejected_during_reset(demo):
    path, _, client = demo
    with demo_operation(database_path=path, reset=True):
        assert client.get("/api/demo").status_code == 409
        assert (
            client.get(
                "/api/investigations", headers={"X-Employee-Id": "emp-alex"}
            ).status_code
            == 409
        )


def test_failed_replacement_preserves_existing_demo(demo, monkeypatch):
    from switchboard import demo as operations

    path, runs, _ = demo
    reset_demo(database_path=path, runs_directory=runs, scenario_id="baseline")
    runs.mkdir()
    evidence = runs / "evidence.json"
    evidence.write_text("saved")
    before = path.read_bytes()

    def fail(**kwargs):
        raise ValueError("Invalid fixtures")

    monkeypatch.setattr(operations, "initialize_demo_database", fail)
    with pytest.raises(ValueError, match="Invalid fixtures"):
        reset_demo(database_path=path, runs_directory=runs, scenario_id="baseline")
    assert evidence.read_text() == "saved"
    assert path.read_bytes() == before


def test_cli_reset_requires_confirmation_and_reports_active_scenario(
    demo, monkeypatch, capsys
):
    path, _, _ = demo
    monkeypatch.setattr(sys, "argv", ["switchboard", "--reset-demo", "baseline"])
    with pytest.raises(SystemExit):
        cli.main()
    assert not path.exists()

    monkeypatch.setattr(
        sys, "argv", ["switchboard", "--reset-demo", "baseline", "--confirm-reset"]
    )
    cli.main()
    assert "Saved demo work cleared" in capsys.readouterr().out
    setup = read_demo_setup(path)
    assert setup is not None
    assert setup.scenario_id == "baseline"
