"""Review pauses survive process exit and do not authorize configuration changes."""

import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from langgraph.types import Command
from test_agent import ScriptedModel, structured_result

from switchboard import __main__ as cli
from switchboard.tools import InvestigationContext
from switchboard.workflow import EndpointChangeContext, workflow


@pytest.fixture
def paused_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "RUNS_DIRECTORY", tmp_path / "workflows")
    monkeypatch.setattr(cli, "PROPOSALS_DATABASE", tmp_path / "proposals.db")
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(
        cli, "create_model", lambda: ScriptedModel(messages=iter([structured_result()]))
    )
    monkeypatch.setattr(sys, "argv", ["switchboard"])
    cli.main()
    assert "Paused for review" in capsys.readouterr().out
    run_directory = next(cli.RUNS_DIRECTORY.iterdir())
    return run_directory


def test_resume_in_fresh_process_preserves_records_and_does_not_repeat_model(
    paused_run,
):
    # 1. Set up inputs and exercise the behavior under test.
    business_path = paused_run / "business.db"
    with closing(sqlite3.connect(business_path)) as connection:
        before = list(connection.iterdump())
    code = """
import sys
from pathlib import Path
from switchboard import __main__ as cli
cli.RUNS_DIRECTORY = Path(sys.argv[1])
def unexpected_model():
    raise AssertionError("Resume must not create a model")
cli.create_model = unexpected_model
sys.argv = ["switchboard", "--resume", sys.argv[2], "--employee", "emp-priya"]
cli.main()
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(paused_run.parent), paused_run.name],
        capture_output=True,
        text=True,
    )
    # 2. Verify the expected result and any safety guarantees.
    assert process.returncode == 0, process.stderr
    assert "Review acknowledged by emp-priya" in process.stdout
    assert "remains pending approval" in process.stdout
    with closing(sqlite3.connect(business_path)) as connection:
        assert list(connection.iterdump()) == before
    with closing(sqlite3.connect(cli.PROPOSALS_DATABASE)) as connection:
        assert connection.execute("SELECT status FROM proposals").fetchall() == [
            ("pending_approval",)
        ]
    with pytest.raises(ValueError, match="not waiting for review"):
        cli.review_saved_workflow(
            workflow_id=paused_run.name, employee_id="emp-priya", resume=True
        )


@pytest.mark.parametrize("denial", ["cross-customer", "inactive", "assignment-revoked"])
def test_denied_reviewer_cannot_resume(paused_run, denial):
    # 1. Set up inputs and exercise the behavior under test.
    employee_id = "emp-ben" if denial == "cross-customer" else "emp-priya"
    with closing(sqlite3.connect(paused_run / "business.db")) as connection, connection:
        if denial == "inactive":
            connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-priya'")
        elif denial == "assignment-revoked":
            connection.execute(
                "DELETE FROM assignments WHERE employee_id = 'emp-priya'"
            )
    with pytest.raises(PermissionError, match="Record unavailable"):
        cli.review_saved_workflow(
            workflow_id=paused_run.name, employee_id=employee_id, resume=True
        )
    with closing(
        sqlite3.connect(paused_run / "checkpoints.db", check_same_thread=False)
    ) as connection:
        graph = workflow.compile(checkpointer=cli.create_checkpointer(connection))
        state = graph.get_state({"configurable": {"thread_id": paused_run.name}})
        # 2. Verify the expected result and any safety guarantees.
        assert state.next == ("review_proposal",)
        assert "reviewed_by_employee_id" not in state.values


def test_view_does_not_resume(paused_run, capsys):
    # 1. Set up inputs and exercise the behavior under test.
    cli.review_saved_workflow(
        workflow_id=paused_run.name, employee_id="emp-priya", resume=False
    )
    # 2. Verify the expected result and any safety guarantees.
    assert "Viewing does not resume" in capsys.readouterr().out
    cli.review_saved_workflow(
        workflow_id=paused_run.name, employee_id="emp-priya", resume=True
    )
    assert "Review acknowledged" in capsys.readouterr().out


def test_graph_rechecks_reviewer_access_without_cli_guard(paused_run):
    # 1. Set up inputs and exercise the behavior under test.
    with closing(
        sqlite3.connect(paused_run / "checkpoints.db", check_same_thread=False)
    ) as connection:
        graph = workflow.compile(checkpointer=cli.create_checkpointer(connection))
        with pytest.raises(PermissionError, match="Record unavailable"):
            graph.invoke(
                Command(resume={"action": "acknowledge_review"}),
                config={"configurable": {"thread_id": paused_run.name}},
                context=EndpointChangeContext(
                    agent=None,
                    investigation_context=InvestigationContext(
                        database_path=paused_run / "business.db", employee_id="emp-alex"
                    ),
                    proposals_database_path=cli.PROPOSALS_DATABASE,
                    reviewer_employee_id="emp-ben",
                ),
            )
        # 2. Verify the expected result and any safety guarantees.
        assert (
            "reviewed_by_employee_id"
            not in graph.get_state(
                {"configurable": {"thread_id": paused_run.name}}
            ).values
        )
