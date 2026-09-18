"""Exercise workflow routing, proposal persistence, and read-only enforcement."""

import json
import sqlite3
from contextlib import closing
from unittest.mock import Mock

import pytest
from langgraph.runtime import Runtime
from test_agent import ScriptedModel, structured_result

from switchboard.agent import build_agent
from switchboard.integrations.database import seed_database
from switchboard.models import Proposal
from switchboard.tools import InvestigationContext
from switchboard.workflow import (
    EndpointChangeContext,
    endpoint_change_graph,
    investigate_request,
)


@pytest.mark.parametrize("changes_records", [False, True])
def test_investigation_checks_database_after_agent_failure(tmp_path, changes_records):
    path = tmp_path / "business.db"
    with closing(sqlite3.connect(path)) as connection:
        seed_database(connection=connection)

    def fail(*args, **kwargs):
        if changes_records:
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE employees SET active = 0")
        raise ValueError("Agent failed")

    agent = Mock()
    agent.invoke.side_effect = fail
    runtime = Runtime(
        context=EndpointChangeContext(
            agent=agent,
            investigation_context=InvestigationContext(path, "emp-alex"),
            proposals_database_path=tmp_path / "proposals.db",
        )
    )
    error_type = RuntimeError if changes_records else ValueError
    message = "changed business records" if changes_records else "Agent failed"
    with pytest.raises(error_type, match=message):
        investigate_request({"request": "Investigate CHG-1042"}, runtime)


@pytest.fixture
def workflow_context(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    path = tmp_path / "business.db"
    with closing(sqlite3.connect(path)) as connection:
        seed_database(connection=connection)

    def make_context(response):
        model = ScriptedModel(messages=iter([response]))
        return EndpointChangeContext(
            agent=build_agent(model=model, now="2026-09-22T14:15:00Z"),
            investigation_context=InvestigationContext(path, "emp-alex"),
            proposals_database_path=tmp_path / "proposals.db",
        )

    yield make_context

    # Both successful and rejected runs must leave business records untouched.
    with closing(sqlite3.connect(path)) as actual:
        with closing(sqlite3.connect(":memory:")) as expected:
            seed_database(connection=expected)
            assert list(actual.iterdump()) == list(expected.iterdump())


def test_candidate_routes_to_proposal_and_persists_it(workflow_context):
    response = structured_result()
    context = workflow_context(response)
    result = endpoint_change_graph.invoke(
        {"request": "Investigate CHG-1042"}, context=context
    )

    assert result["investigation"].outcome == "proposal_candidate"
    assert result["was_created"] is True
    assert result["__interrupt__"][0].value["proposal_id"] == result["proposal"].id
    assert result["messages"][-1].text == response.text
    proposal = result["proposal"]
    assert proposal.ticket_id == "CHG-1042"
    assert proposal.proposed_by_employee_id == "emp-alex"
    assert proposal.status == "pending_approval"
    with closing(sqlite3.connect(context.proposals_database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM proposals").fetchall()
    assert len(rows) == 1
    assert Proposal.model_validate_json(json.dumps(dict(rows[0]))) == proposal


def test_blocked_routes_to_end_without_saving(workflow_context):
    context = workflow_context(
        structured_result(
            outcome="blocked",
            ticket_id=None,
            proposed_endpoint=None,
            evidence_ids=[],
            summary="Required evidence is unavailable.",
            blockers=["Required evidence is unavailable."],
        )
    )
    result = endpoint_change_graph.invoke(
        {"request": "Investigate CHG-1042"}, context=context
    )

    assert result["investigation"].outcome == "blocked"
    assert "__interrupt__" not in result
    assert "proposal" not in result
    assert "was_created" not in result
    assert not context.proposals_database_path.exists()


def test_unsupported_candidate_fails_business_validation_without_saving(
    workflow_context,
):
    context = workflow_context(
        structured_result(proposed_endpoint="https://other.acme.example/deals")
    )
    with pytest.raises(ValueError, match="does not match the ticket request"):
        endpoint_change_graph.invoke(
            {"request": "Investigate CHG-1042"}, context=context
        )

    assert not context.proposals_database_path.exists()
