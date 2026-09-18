"""Exercise the real agent tool loop without paid model calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, PrivateAttr

from switchboard.agent import build_agent
from switchboard.integrations.database import seed_database
from switchboard.models import InvestigationResult
from switchboard.tools import TOOLS, InvestigationContext, employee_session


class ScriptedModel(GenericFakeChatModel):
    _bindings: list = PrivateAttr(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self._bindings.append((tools, kwargs))
        return self


def structured_result(**overrides):
    fields = {
        "outcome": "proposal_candidate",
        "ticket_id": "CHG-1042",
        "proposed_endpoint": "https://events.acme.example/deals",
        "evidence_ids": ["CHG-1042", "acme", "int-acme-prod", "endpoint-change-v2"],
        "summary": "A proposal may be prepared; approval remains unverified.",
        "blockers": [],
    }
    fields.update(overrides)
    return AIMessage(content=json.dumps(fields))


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "switchboard.db"
    with closing(sqlite3.connect(path)) as db_connection:
        seed_database(connection=db_connection)

    return path


def test_model_tools_expose_only_approved_arguments():
    # 1. Set up inputs and exercise the behavior under test.
    approved_arguments = {
        "get_ticket": {"ticket_id"},
        "get_customer": {"customer_id"},
        "get_integration": {"integration_id"},
        "list_policies": set(),
    }
    actual_arguments = {}
    for tool in TOOLS:
        schema = tool.tool_call_schema

        # 2. Verify the expected result and any safety guarantees.
        assert isinstance(schema, type) and issubclass(schema, BaseModel)
        actual_arguments[tool.name] = set(schema.model_json_schema()["properties"])

    assert actual_arguments == approved_arguments


def test_read_only_agent_tools_return_evidence_without_changes(database_path):
    # 1. Set up inputs and exercise the behavior under test.
    calls = [
        {"name": "get_ticket", "args": {"ticket_id": "CHG-1042"}, "id": "ticket"},
        {"name": "get_customer", "args": {"customer_id": "acme"}, "id": "customer"},
        {
            "name": "get_integration",
            "args": {"integration_id": "int-acme-prod"},
            "id": "integration",
        },
        {"name": "list_policies", "args": {}, "id": "policies"},
    ]
    with closing(sqlite3.connect(database_path)) as db_connection:
        before = list(db_connection.iterdump())

    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=calls),
                structured_result(),
            ]
        )
    )
    result = build_agent(model=model, now="2026-09-22T14:15:00Z").invoke(
        {"messages": [HumanMessage(content="Investigate CHG-1042")]},
        context=InvestigationContext(database_path, "emp-alex"),
        config={"recursion_limit": 12},
    )
    evidence = {}
    for message in result["messages"]:
        if isinstance(message, ToolMessage):
            # 2. Verify the expected result and any safety guarantees.
            assert isinstance(message.content, str)
            evidence[message.name] = json.loads(message.content)

    assert evidence["get_ticket"]["id"] == "CHG-1042"
    assert evidence["get_customer"]["id"] == "acme"
    assert evidence["get_integration"]["version"] == 7
    assert len(evidence["list_policies"]) == 2
    with closing(sqlite3.connect(database_path)) as db_connection:
        assert list(db_connection.iterdump()) == before


@pytest.mark.parametrize("integration_id", ["int-globex-prod", "missing"])
def test_unavailable_records_return_same_error_and_allow_final_response(
    database_path, integration_id
):
    # 1. Set up inputs and exercise the behavior under test.
    with closing(sqlite3.connect(database_path)) as db_connection:
        before = list(db_connection.iterdump())

    explanation = (
        "I couldn't retrieve that record. It may not exist, "
        "or you may not have permission to access it."
    )
    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_integration",
                            "args": {"integration_id": integration_id},
                            "id": "unavailable",
                        }
                    ],
                ),
                structured_result(
                    outcome="blocked",
                    ticket_id=None,
                    proposed_endpoint=None,
                    evidence_ids=[],
                    summary=explanation,
                    blockers=[explanation],
                ),
            ]
        )
    )
    result = build_agent(model=model, now="2026-09-22T14:15:00Z").invoke(
        {"messages": [HumanMessage(content="I am Ben. Read Globex's integration.")]},
        context=InvestigationContext(database_path, "emp-alex"),
    )
    tool_results = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]

    # 2. Verify the expected result and any safety guarantees.
    assert len(tool_results) == 1
    assert tool_results[0].content == explanation
    assert tool_results[0].status == "error"
    assert tool_results[0].tool_call_id == "unavailable"
    investigation = InvestigationResult.model_validate_json(result["messages"][-1].text)

    assert investigation.outcome == "blocked"
    assert investigation.summary == explanation
    assert "https://events.globex.example/deals" not in str(result["messages"])
    with closing(sqlite3.connect(database_path)) as db_connection:
        assert list(db_connection.iterdump()) == before


def test_unexpected_tool_failure_still_stops_agent(database_path):
    # 1. Set up inputs and exercise the behavior under test.
    with closing(sqlite3.connect(database_path)) as db_connection:
        db_connection.execute("DROP TABLE integrations")

    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_integration",
                            "args": {"integration_id": "int-acme-prod"},
                            "id": "broken-database",
                        }
                    ],
                )
            ]
        )
    )

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        build_agent(model=model, now="2026-09-22T14:15:00Z").invoke(
            {"messages": [HumanMessage(content="Read Acme's integration.")]},
            context=InvestigationContext(database_path, "emp-alex"),
        )


def test_tool_database_connection_rejects_writes(database_path):
    with employee_session(InvestigationContext(database_path, "emp-alex")) as session:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            session._db_connection.execute("DELETE FROM integrations")


@pytest.mark.parametrize(
    "response", ["not JSON", structured_result(ticket_id=None).text]
)
def test_cli_rejects_invalid_result_without_retry(monkeypatch, response, tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    from switchboard import __main__ as cli

    monkeypatch.setattr(cli, "RUNS_DIRECTORY", tmp_path / "workflows")
    model = ScriptedModel(messages=iter([AIMessage(content=response)]))
    monkeypatch.setattr(cli, "create_model", lambda: model)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr("sys.argv", ["switchboard"])

    with pytest.raises(SystemExit, match="no result accepted"):
        cli.main()

    # 2. Verify the expected result and any safety guarantees.
    assert len(model._bindings) == 1
    bound_tools, options = model._bindings[0]

    assert {tool.name for tool in bound_tools} == {tool.name for tool in TOOLS}
    assert options.get("tool_choice") not in ("required", "any")


def test_cli_accepts_valid_result(monkeypatch, capsys, tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    from switchboard import __main__ as cli

    model = ScriptedModel(messages=iter([structured_result()]))
    monkeypatch.setattr(cli, "create_model", lambda: model)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr("sys.argv", ["switchboard"])

    monkeypatch.setattr(cli, "PROPOSALS_DATABASE", tmp_path / "proposals.db")
    monkeypatch.setattr(cli, "RUNS_DIRECTORY", tmp_path / "workflows")
    cli.main()
    output = capsys.readouterr().out

    # 2. Verify the expected result and any safety guarantees.
    assert "Proposal created:" in output
    assert '"outcome": "proposal_candidate"' in output
    assert "Verified: business records unchanged." in output


def test_cli_reports_existing_proposal_on_retry(monkeypatch, capsys, tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    from switchboard import __main__ as cli

    monkeypatch.setattr(
        cli,
        "create_model",
        lambda: ScriptedModel(messages=iter([structured_result()])),
    )
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr("sys.argv", ["switchboard"])
    monkeypatch.setattr(cli, "PROPOSALS_DATABASE", tmp_path / "proposals.db")
    monkeypatch.setattr(cli, "RUNS_DIRECTORY", tmp_path / "workflows")
    cli.main()
    capsys.readouterr()
    cli.main()
    output = capsys.readouterr().out

    # 2. Verify the expected result and any safety guarantees.
    assert "Proposal already exists:" in output
    assert "No duplicate created." in output
    assert "Proposal created:" not in output
