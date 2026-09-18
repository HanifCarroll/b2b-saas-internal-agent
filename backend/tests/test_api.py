"""Exercise the actual HTTP review and approval boundary without LLM calls."""

import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_proposals import candidate

from switchboard import api
from switchboard.integrations.change_management import save_proposal
from switchboard.integrations.database import seed_database
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import InvestigationFindings
from switchboard.proposals import validate_proposal


@pytest.fixture
def review_api(tmp_path, monkeypatch):
    run_id = str(uuid4())
    directory = tmp_path / run_id
    directory.mkdir()
    storage = tmp_path / "proposals.db"
    with closing(sqlite3.connect(directory / "business.db")) as connection:
        seed_database(connection=connection)
        session = EmployeeSession(db_connection=connection, employee_id="emp-alex")
        proposal, _ = save_proposal(
            proposal=validate_proposal(investigation=candidate(), session=session),
            session=session,
            database_path=storage,
        )

    (directory / "run.json").write_text(
        json.dumps({"proposals_database_path": str(storage)})
    )
    monkeypatch.setattr(api, "RUNS_DIRECTORY", tmp_path)
    return TestClient(api.app), f"/api/runs/{run_id}/proposals/{proposal.id}", directory


def test_review_approve_refresh_and_retry(review_api):
    client, url, _ = review_api
    headers = {"X-Employee-Id": "emp-priya"}
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["approval"] is None

    approval = client.post(url + "/approval", headers=headers)
    assert approval.status_code == 200
    assert approval.json()["approved_by_employee_id"] == "emp-priya"
    assert client.get(url, headers=headers).json()["approval"] == approval.json()
    assert client.post(url + "/approval", headers=headers).json() == approval.json()


@pytest.mark.parametrize("employee", ["emp-ben", "missing"])
def test_inaccessible_and_missing_proposals_have_same_response(review_api, employee):
    client, url, _ = review_api
    headers = {"X-Employee-Id": employee}
    response = client.get(url, headers=headers)
    missing = client.get(url.rsplit("/", 1)[0] + "/missing", headers=headers)
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    assert client.post(url + "/approval", headers=headers).status_code == 403


def test_self_approval_and_revoked_access_are_rejected(review_api):
    client, url, directory = review_api
    assert (
        client.post(
            url + "/approval", headers={"X-Employee-Id": "emp-alex"}
        ).status_code
        == 403
    )
    with closing(sqlite3.connect(directory / "business.db")) as connection, connection:
        connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-priya'")

    assert client.get(url, headers={"X-Employee-Id": "emp-priya"}).status_code == 404
    assert (
        client.post(
            url + "/approval", headers={"X-Employee-Id": "emp-priya"}
        ).status_code
        == 403
    )


def test_identity_header_is_required(review_api):
    client, url, _ = review_api
    assert client.get(url).status_code == 422
    assert client.post(url + "/approval").status_code == 422


@pytest.fixture
def investigation_api(tmp_path, monkeypatch):
    from test_agent import ScriptedModel, structured_result

    monkeypatch.setattr(api, "RUNS_DIRECTORY", tmp_path / "runs")
    monkeypatch.setattr(api, "PROPOSALS_DATABASE", tmp_path / "proposals.db")
    monkeypatch.setattr(api, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(
        api, "create_model", lambda: ScriptedModel(messages=iter([structured_result()]))
    )
    return TestClient(api.app)


def test_investigation_history_and_approval_handoff(investigation_api):
    client = investigation_api
    headers = {"X-Employee-Id": "emp-alex"}
    response = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    )
    assert response.status_code == 200
    run = response.json()
    assert run["result"]["was_created"] is True
    assert (
        client.get(f"/api/investigations/{run['run_id']}", headers=headers).json()
        == run
    )
    assert (
        client.get("/api/investigations", headers=headers).json()[0]["run_id"]
        == run["run_id"]
    )
    assert (
        client.get("/api/investigations", headers={"X-Employee-Id": "emp-ben"}).json()
        == []
    )
    assert (
        client.get(
            f"/api/investigations/{run['run_id']}",
            headers={"X-Employee-Id": "emp-priya"},
        ).status_code
        == 404
    )

    proposal_url = (
        f"/api/runs/{run['run_id']}/proposals/{run['result']['proposal']['id']}"
    )
    assert (
        client.post(
            proposal_url + "/approval", headers={"X-Employee-Id": "emp-priya"}
        ).status_code
        == 200
    )
    assert client.get(proposal_url, headers=headers).json()["approval"] is not None

    with (
        closing(
            sqlite3.connect(api.RUNS_DIRECTORY / run["run_id"] / "business.db")
        ) as connection,
        connection,
    ):
        connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-alex'")
    assert (
        client.get(f"/api/investigations/{run['run_id']}", headers=headers).status_code
        == 404
    )


def test_invalid_demo_choices_do_not_call_model(investigation_api, monkeypatch):
    def unexpected_model():
        raise AssertionError("Must reject before model creation")

    monkeypatch.setattr(api, "create_model", unexpected_model)
    client = investigation_api
    assert (
        client.post(
            "/api/investigations",
            json={"scenario_id": "unknown"},
            headers={"X-Employee-Id": "emp-alex"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/investigations",
            json={"scenario_id": "baseline"},
            headers={"X-Employee-Id": "unknown"},
        ).status_code
        == 403
    )


def test_blocked_investigation_is_saved_without_proposal(
    investigation_api, monkeypatch
):
    from langchain_core.messages import AIMessage
    from test_agent import ScriptedModel

    from switchboard.models import InvestigationResult

    blocked = InvestigationResult(
        outcome="blocked",
        ticket_id="CHG-1042",
        proposed_endpoint=None,
        evidence_ids=["CHG-1042"],
        findings=InvestigationFindings(
            overview="Destination is not registered.",
            checks=[],
            policy_requirements=[],
            gaps=[],
            recommendation="Review the evidence before proceeding.",
        ),
        blockers=["Unregistered destination"],
    )
    monkeypatch.setattr(
        api,
        "create_model",
        lambda: ScriptedModel(
            messages=iter([AIMessage(content=blocked.model_dump_json())])
        ),
    )
    response = investigation_api.post(
        "/api/investigations",
        json={"scenario_id": "baseline"},
        headers={"X-Employee-Id": "emp-alex"},
    )
    assert response.status_code == 200
    assert response.json()["current_status"]["code"] == "blocked"
    assert response.json()["result"]["proposal"] is None
    assert not api.PROPOSALS_DATABASE.exists()


def test_policy_review_is_separate_and_persisted(investigation_api, monkeypatch):
    from switchboard.policy_evaluation import PolicyReview

    client = investigation_api
    headers = {"X-Employee-Id": "emp-alex"}
    run = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()
    monkeypatch.setattr(
        api, "evaluate_policy", lambda **kwargs: PolicyReview(issues=[])
    )
    url = f"/api/investigations/{run['run_id']}"
    response = client.post(url + "/policy-review", headers=headers)
    assert response.status_code == 200
    refreshed = client.get(url, headers=headers).json()
    assert refreshed["policy_review"] == response.json()
    assert refreshed["result"] == run["result"]


def test_model_failure_returns_safe_error(investigation_api, monkeypatch):
    def fail():
        raise RuntimeError("Private provider error")

    monkeypatch.setattr(api, "create_model", fail)
    response = investigation_api.post(
        "/api/investigations",
        json={"scenario_id": "baseline"},
        headers={"X-Employee-Id": "emp-alex"},
    )
    assert response.status_code == 502
    assert "Private provider error" not in response.text


def test_blocked_inaccessible_ticket_remains_in_own_history(
    investigation_api, monkeypatch
):
    from langchain_core.messages import AIMessage
    from test_agent import ScriptedModel

    from switchboard.models import InvestigationResult

    blocked = InvestigationResult(
        outcome="blocked",
        ticket_id="unavailable-ticket",
        proposed_endpoint=None,
        evidence_ids=[],
        findings=InvestigationFindings(
            overview="Record unavailable.",
            checks=[],
            policy_requirements=[],
            gaps=[],
            recommendation="Review the evidence before proceeding.",
        ),
        blockers=["Could not retrieve record"],
    )
    monkeypatch.setattr(
        api,
        "create_model",
        lambda: ScriptedModel(
            messages=iter([AIMessage(content=blocked.model_dump_json())])
        ),
    )
    headers = {"X-Employee-Id": "emp-alex"}
    run = investigation_api.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()
    assert (
        investigation_api.get(
            f"/api/investigations/{run['run_id']}", headers=headers
        ).status_code
        == 200
    )
    assert (
        len(investigation_api.get("/api/investigations", headers=headers).json()) == 1
    )


def test_environment_loads_once_at_startup(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "load_dotenv", lambda path: calls.append(path))
    with TestClient(api.app) as client:
        assert len(calls) == 1
        for _ in range(2):
            response = client.get("/api/demo-options")
            assert response.status_code == 200
            assert response.json()["employees"]
        assert len(calls) == 1


def test_policy_review_rechecks_access_before_saving(investigation_api, monkeypatch):
    from switchboard.policy_evaluation import PolicyReview

    client = investigation_api
    headers = {"X-Employee-Id": "emp-alex"}
    run = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()
    directory = api.RUNS_DIRECTORY / run["run_id"]

    def revoke_during_evaluation(**kwargs):
        with (
            closing(sqlite3.connect(directory / "business.db")) as connection,
            connection,
        ):
            connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-alex'")
        return PolicyReview(issues=[])

    monkeypatch.setattr(api, "evaluate_policy", revoke_during_evaluation)
    response = client.post(
        f"/api/investigations/{run['run_id']}/policy-review", headers=headers
    )
    assert response.status_code == 404
    assert not (directory / "policy-review.json").exists()


def test_missing_runs_have_safe_http_errors(investigation_api):
    client = investigation_api
    run_id = uuid4()
    headers = {"X-Employee-Id": "emp-alex"}
    for path in (
        f"/api/investigations/{run_id}",
        f"/api/runs/{run_id}/proposals/missing",
    ):
        assert client.get(path, headers=headers).status_code == 404


def test_tool_calls_survive_save_reload_and_http(investigation_api, monkeypatch):
    from langchain_core.messages import AIMessage
    from test_agent import ScriptedModel, structured_result

    call = {
        "name": "get_ticket",
        "args": {"ticket_id": "CHG-1042"},
        "id": "ticket-call",
        "type": "tool_call",
    }
    monkeypatch.setattr(
        api,
        "create_model",
        lambda: ScriptedModel(
            messages=iter(
                [
                    AIMessage(content="", tool_calls=[call]),
                    structured_result(),
                ]
            )
        ),
    )
    headers = {"X-Employee-Id": "emp-alex"}
    response = investigation_api.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    )
    assert response.status_code == 200
    run = response.json()
    saved_path = api.RUNS_DIRECTORY / run["run_id"] / "result.json"
    refreshed = investigation_api.get(
        f"/api/investigations/{run['run_id']}", headers=headers
    ).json()
    for result in (
        run["result"],
        json.loads(saved_path.read_text()),
        refreshed["result"],
    ):
        assert [c for m in result["messages"] for c in m.get("tool_calls", [])] == [
            call
        ]
        tool_result = next(m for m in result["messages"] if m["type"] == "tool")
        assert tool_result["tool_call_id"] == "ticket-call"
        assert tool_result["status"] == "success"
        assert result["investigation"]["findings"]["recommendation"]


def test_current_status_tracks_approval_without_rewriting_investigation(
    investigation_api,
):
    client = investigation_api
    headers = {"X-Employee-Id": "emp-alex"}
    run = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()
    assert run["current_status"]["code"] == "awaiting_approval"
    path = api.RUNS_DIRECTORY / run["run_id"] / "result.json"
    original = path.read_bytes()
    url = f"/api/runs/{run['run_id']}/proposals/{run['result']['proposal']['id']}"
    assert (
        client.post(
            url + "/approval", headers={"X-Employee-Id": "emp-priya"}
        ).status_code
        == 200
    )
    refreshed = client.get(
        f"/api/investigations/{run['run_id']}", headers=headers
    ).json()
    assert refreshed["current_status"]["code"] == "approval_recorded"
    assert refreshed["result"] == run["result"]
    assert path.read_bytes() == original
    assert (
        client.get(url, headers=headers).json()["current_status"]
        == refreshed["current_status"]
    )
    reused = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()
    assert reused["result"]["was_created"] is False
    assert reused["current_status"]["code"] == "approval_recorded"


def test_unavailable_approval_is_not_reported_as_awaiting_approval(
    investigation_api, monkeypatch
):
    from switchboard import workflow_status

    client = investigation_api
    headers = {"X-Employee-Id": "emp-alex"}
    run = client.post(
        "/api/investigations", json={"scenario_id": "baseline"}, headers=headers
    ).json()

    def unavailable(**kwargs):
        raise PermissionError("Record unavailable")

    monkeypatch.setattr(workflow_status, "get_proposal_review", unavailable)
    response = client.get(f"/api/investigations/{run['run_id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["current_status"]["code"] == "unavailable"


def test_sandbox_status_does_not_request_independent_approval(review_api):
    from switchboard.models import Proposal
    from switchboard.workflow_status import proposal_status

    client, url, _ = review_api
    record = client.get(url, headers={"X-Employee-Id": "emp-alex"}).json()["proposal"]
    record["environment"] = "sandbox"
    proposal = Proposal.model_validate_json(json.dumps(record))
    status = proposal_status(proposal=proposal, approval=None)
    assert status.code == "approval_not_required"
    assert "Execution is not implemented" in status.next_action
