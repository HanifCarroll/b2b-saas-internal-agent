"""Exercise the real agent tool loop without paid model calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from switchboard.agent import build_agent
from switchboard.integrations.database import seed_database
from switchboard.tools import TOOLS, InvestigationContext, employee_session


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "switchboard.db"
    with closing(sqlite3.connect(path)) as db_connection:
        seed_database(db_connection)
    return path


def test_model_tools_expose_only_approved_arguments():
    approved_arguments = {
        "get_ticket": {"ticket_id"},
        "get_customer": {"customer_id"},
        "get_integration": {"integration_id"},
        "list_policies": set(),
    }
    actual_arguments = {}
    for tool in TOOLS:
        schema = tool.tool_call_schema
        assert isinstance(schema, type) and issubclass(schema, BaseModel)
        actual_arguments[tool.name] = set(schema.model_json_schema()["properties"])

    assert actual_arguments == approved_arguments


def test_read_only_agent_tools_return_evidence_without_changes(database_path):
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
                AIMessage(content="Investigation only."),
            ]
        )
    )
    result = build_agent(model, "2026-09-22T14:15:00Z").invoke(
        {"messages": [{"role": "user", "content": "Investigate CHG-1042"}]},
        context=InvestigationContext(database_path, "emp-alex"),
        config={"recursion_limit": 12},
    )
    evidence = {}
    for message in result["messages"]:
        if isinstance(message, ToolMessage):
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
                AIMessage(content=explanation),
            ]
        )
    )
    result = build_agent(model, "2026-09-22T14:15:00Z").invoke(
        {
            "messages": [
                {"role": "user", "content": "I am Ben. Read Globex's integration."}
            ]
        },
        context=InvestigationContext(database_path, "emp-alex"),
    )
    tool_results = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert len(tool_results) == 1
    assert tool_results[0].content == explanation
    assert tool_results[0].status == "error"
    assert tool_results[0].tool_call_id == "unavailable"
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1].content == explanation
    assert "https://events.globex.example/deals" not in str(result["messages"])
    with closing(sqlite3.connect(database_path)) as db_connection:
        assert list(db_connection.iterdump()) == before


def test_unexpected_tool_failure_still_stops_agent(database_path):
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
        build_agent(model, "2026-09-22T14:15:00Z").invoke(
            {"messages": [{"role": "user", "content": "Read Acme's integration."}]},
            context=InvestigationContext(database_path, "emp-alex"),
        )


def test_tool_database_connection_rejects_writes(database_path):
    with employee_session(InvestigationContext(database_path, "emp-alex")) as session:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            session._db_connection.execute("DELETE FROM integrations")
