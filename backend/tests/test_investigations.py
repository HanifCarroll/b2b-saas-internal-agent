"""Exercise ticket-selected investigations without demo scenario state."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from test_agent import ScriptedModel, structured_result

from switchboard.integrations.database import seed_database
from switchboard.investigations import investigate_ticket


@pytest.fixture
def business_database(tmp_path):
    path = tmp_path / "switchboard.db"
    with closing(sqlite3.connect(path)) as connection:
        seed_database(connection=connection)
    return path


def test_accessible_ticket_can_be_investigated_without_active_scenario(
    business_database, tmp_path, monkeypatch
):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    run = investigate_ticket(
        ticket_id="CHG-1042",
        employee_id="emp-alex",
        model=ScriptedModel(messages=iter([structured_result()])),
        runs_directory=tmp_path / "runs",
        database_path=business_database,
        now=datetime(2026, 9, 22, 14, 15, tzinfo=timezone.utc),
    )

    manifest = json.loads(
        (tmp_path / "runs" / run.workflow_id / "run.json").read_text()
    )
    assert manifest["ticket_id"] == "CHG-1042"
    assert "scenario_id" not in manifest
    assert run.result.investigation.ticket_id == "CHG-1042"


def test_inaccessible_ticket_is_rejected_before_the_model_runs(
    business_database, tmp_path
):
    model = Mock(spec=BaseChatModel)
    model.invoke.side_effect = AssertionError("The model must not run")

    with pytest.raises(PermissionError, match="Record unavailable"):
        investigate_ticket(
            ticket_id="CHG-1042",
            employee_id="emp-ben",
            model=model,
            runs_directory=tmp_path / "runs",
            database_path=business_database,
            now=datetime(2026, 9, 22, 14, 15, tzinfo=timezone.utc),
        )

    assert not (tmp_path / "runs").exists()
    model.invoke.assert_not_called()
