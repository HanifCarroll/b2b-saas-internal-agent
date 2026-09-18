"""Saved proposals can be reviewed without an agent or a graph checkpoint."""

import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from test_agent import ScriptedModel, structured_result

from switchboard import __main__ as cli


@pytest.fixture
def completed_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "RUNS_DIRECTORY", tmp_path / "workflows")
    monkeypatch.setattr(cli, "DATABASE_PATH", tmp_path / "switchboard.db")
    from switchboard.demo import reset_demo

    reset_demo(
        database_path=cli.DATABASE_PATH,
        runs_directory=cli.RUNS_DIRECTORY,
        scenario_id="baseline",
    )
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(
        cli, "create_model", lambda: ScriptedModel(messages=iter([structured_result()]))
    )
    monkeypatch.setattr(sys, "argv", ["switchboard"])
    cli.main()

    assert "Investigation complete" in capsys.readouterr().out
    assert not (next(cli.RUNS_DIRECTORY.iterdir()) / "checkpoints.db").exists()
    run_directory = next(cli.RUNS_DIRECTORY.iterdir())
    return run_directory


def test_review_in_fresh_process_preserves_records_without_model(
    completed_run,
):
    # 1. Set up inputs and exercise the behavior under test.
    business_path = cli.DATABASE_PATH
    with closing(sqlite3.connect(business_path)) as connection:
        before = list(connection.iterdump())

    with closing(sqlite3.connect(cli.DATABASE_PATH)) as connection:
        proposal_id = connection.execute("SELECT id FROM proposals").fetchone()[0]
        proposals_before = list(connection.iterdump())

    code = """
import sys
from pathlib import Path
from switchboard import __main__ as cli
cli.RUNS_DIRECTORY = Path(sys.argv[1])
def unexpected_model():
    raise AssertionError("Review must not create a model")
cli.create_model = unexpected_model
sys.argv = ["switchboard", "--review", sys.argv[3], "--run", sys.argv[2], "--employee", "emp-priya"]
cli.main()
"""
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(completed_run.parent),
            completed_run.name,
            proposal_id,
        ],
        capture_output=True,
        text=True,
    )

    # 2. Verify the expected result and any safety guarantees.
    assert process.returncode == 0, process.stderr
    assert proposal_id in process.stdout
    assert "Viewing does not approve" in process.stdout
    with closing(sqlite3.connect(business_path)) as connection:
        assert list(connection.iterdump()) == before

    with closing(sqlite3.connect(cli.DATABASE_PATH)) as connection:
        assert connection.execute("SELECT status FROM proposals").fetchall() == [
            ("pending_approval",)
        ]
        assert list(connection.iterdump()) == proposals_before


@pytest.mark.parametrize("denial", ["cross-customer", "inactive", "assignment-revoked"])
def test_denied_reviewer_cannot_read(completed_run, denial):
    # 1. Set up inputs and exercise the behavior under test.
    employee_id = "emp-ben" if denial == "cross-customer" else "emp-priya"
    with (
        closing(sqlite3.connect(cli.DATABASE_PATH)) as connection,
        connection,
    ):
        if denial == "inactive":
            connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-priya'")
        elif denial == "assignment-revoked":
            connection.execute(
                "DELETE FROM assignments WHERE employee_id = 'emp-priya'"
            )

    with closing(sqlite3.connect(cli.DATABASE_PATH)) as connection:
        proposal_id = connection.execute("SELECT id FROM proposals").fetchone()[0]

    with pytest.raises(PermissionError, match="Record unavailable"):
        cli.review_saved_proposal(
            proposal_id=proposal_id,
            workflow_id=completed_run.name,
            employee_id=employee_id,
        )


def test_review_rechecks_access_each_time(completed_run, capsys):
    # 1. An assigned reviewer can retrieve the persisted proposal.
    with closing(sqlite3.connect(cli.DATABASE_PATH)) as connection:
        proposal_id = connection.execute("SELECT id FROM proposals").fetchone()[0]

    cli.review_saved_proposal(
        proposal_id=proposal_id, workflow_id=completed_run.name, employee_id="emp-priya"
    )

    assert proposal_id in capsys.readouterr().out

    # 2. Revoking access prevents another read, even after a successful review.
    with (
        closing(sqlite3.connect(cli.DATABASE_PATH)) as connection,
        connection,
    ):
        connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-priya'")

    with pytest.raises(PermissionError, match="Record unavailable"):
        cli.review_saved_proposal(
            proposal_id=proposal_id,
            workflow_id=completed_run.name,
            employee_id="emp-priya",
        )

    assert capsys.readouterr().out == ""
