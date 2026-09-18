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
from switchboard.models import InvestigationFindings, Proposal
from switchboard.tools import InvestigationContext
from switchboard.workflow import (
    EndpointChangeContext,
    endpoint_change_graph,
    investigate_request,
)


def test_investigation_propagates_agent_failure(tmp_path):
    agent = Mock()
    agent.invoke.side_effect = ValueError("Agent failed")
    runtime = Runtime(
        context=EndpointChangeContext(
            agent=agent,
            investigation_context=InvestigationContext(
                tmp_path / "switchboard.db", "emp-alex"
            ),
        )
    )
    with pytest.raises(ValueError, match="Agent failed"):
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
        )

    yield make_context

    # Both successful and rejected runs must leave business records untouched.
    with closing(sqlite3.connect(path)) as actual:
        with closing(sqlite3.connect(":memory:")) as expected:
            seed_database(connection=expected)

            for table in (
                "customers",
                "employees",
                "assignments",
                "tickets",
                "integrations",
                "policies",
                "approvals",
                "executions",
            ):
                assert (
                    actual.execute(f"SELECT * FROM {table}").fetchall()
                    == expected.execute(f"SELECT * FROM {table}").fetchall()
                )


def test_candidate_routes_to_proposal_and_persists_it(workflow_context):
    # 1. Set up inputs and exercise the behavior under test.
    response = structured_result()
    context = workflow_context(response)
    result = endpoint_change_graph.invoke(
        {"request": "Investigate CHG-1042"}, context=context
    )

    # 2. Verify the expected result and any safety guarantees.
    assert result["investigation"].outcome == "proposal_candidate"
    assert result["was_created"] is True
    assert "__interrupt__" not in result
    assert result["messages"][-1].text == response.text
    proposal = result["proposal"]

    assert proposal.ticket_id == "CHG-1042"
    assert proposal.proposed_by_employee_id == "emp-alex"
    assert proposal.status == "pending_approval"
    with closing(
        sqlite3.connect(context.investigation_context.database_path)
    ) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM proposals").fetchall()

    assert len(rows) == 1
    assert Proposal.model_validate_json(json.dumps(dict(rows[0]))) == proposal


def test_blocked_routes_to_end_without_saving(workflow_context):
    # 1. Set up inputs and exercise the behavior under test.
    context = workflow_context(
        structured_result(
            outcome="blocked",
            ticket_id=None,
            proposed_endpoint=None,
            evidence_ids=[],
            findings=InvestigationFindings(
                overview="Required evidence is unavailable.",
                checks=[],
                policy_requirements=[],
                gaps=[],
                recommendation="Review the evidence before proceeding.",
            ),
            blockers=["Required evidence is unavailable."],
        )
    )
    result = endpoint_change_graph.invoke(
        {"request": "Investigate CHG-1042"}, context=context
    )

    # 2. Verify the expected result and any safety guarantees.
    assert result["investigation"].outcome == "blocked"
    assert "__interrupt__" not in result
    assert "proposal" not in result
    assert "was_created" not in result
    with closing(
        sqlite3.connect(context.investigation_context.database_path)
    ) as connection:
        assert connection.execute("SELECT count(*) FROM proposals").fetchone()[0] == 0


def test_unsupported_candidate_fails_business_validation_without_saving(
    workflow_context,
):
    # 1. Set up inputs and exercise the behavior under test.
    context = workflow_context(
        structured_result(proposed_endpoint="https://other.acme.example/deals")
    )

    with pytest.raises(ValueError, match="does not match the ticket request"):
        endpoint_change_graph.invoke(
            {"request": "Investigate CHG-1042"}, context=context
        )

    # 2. Verify the expected result and any safety guarantees.
    with closing(
        sqlite3.connect(context.investigation_context.database_path)
    ) as connection:
        assert connection.execute("SELECT count(*) FROM proposals").fetchone()[0] == 0
