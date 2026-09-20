import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from switchboard import api
from switchboard.api import RequestContext


@pytest.fixture(autouse=True)
def demo_auth_mode(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "demo")


def client_for(storage, *, employee_id: str = "emp-alex") -> TestClient:
    api.app.dependency_overrides[api.get_request_context] = lambda: RequestContext(
        identity_mode="demo",
        employee_id=employee_id,
        workspace_id=storage.workspace_id,
        storage=storage,
    )
    return TestClient(api.app)


class StubInvestigator:
    def __init__(self, report: dict):
        self.report = report

    def invoke(self, *_args, **_kwargs):
        return {"messages": [AIMessage(content=json.dumps(self.report))]}


def proposal_candidate_report() -> dict:
    return {
        "outcome": "proposal_candidate",
        "ticket_id": "CHG-1042",
        "proposed_endpoint": "https://events.acme.example/deals",
        "evidence_ids": [
            "CHG-1042",
            "acme",
            "int-acme-prod",
            "endpoint-change-v2",
        ],
        "findings": {
            "overview": "Current records support preparing the requested change.",
            "decision_criteria": [],
            "recommendation": "Prepare the proposal for independent review.",
        },
        "blockers": [],
    }


def policy_issue_response() -> str:
    return json.dumps(
        {
            "issues": [
                {
                    "claim": "Rollback is never allowed.",
                    "policy_id": "endpoint-change-v2",
                    "policy_excerpt": (
                        "If verification fails, restore the old endpoint only when the "
                        "approved plan permits it and no intervening change makes restoration unsafe."
                    ),
                    "issue_kind": "invented_absolute_prohibition",
                    "explanation": "The policy permits a conditional restoration.",
                }
            ]
        }
    )


def blocked_report() -> dict:
    return {
        "outcome": "blocked",
        "ticket_id": "CHG-1042",
        "proposed_endpoint": None,
        "evidence_ids": ["CHG-1042", "endpoint-change-v2"],
        "findings": {
            "overview": "The integration record could not be retrieved.",
            "decision_criteria": [
                {
                    "name": "Destination registration",
                    "status": "unavailable",
                    "required_before": "proposal",
                    "explanation": "The integration record was unavailable.",
                    "policy_id": "endpoint-change-v2",
                    "evidence_ids": [],
                }
            ],
            "recommendation": "Restore access and investigate again.",
        },
        "blockers": [
            {
                "kind": "missing_evidence",
                "summary": "Integration evidence is unavailable.",
                "resolution": "Restore access to the integration record.",
            }
        ],
    }


def test_ticket_and_identity_routes_use_the_request_workspace(storage):
    with client_for(storage) as client:
        identity = client.get("/api/me")
        tickets = client.get("/api/tickets")
    api.app.dependency_overrides.clear()

    assert identity.status_code == 200
    assert identity.json() == {
        "employee_id": "emp-alex",
        "name": "Alex Rivera",
        "role": "implementation_engineer",
    }
    assert tickets.status_code == 200
    assert tickets.json()[0]["requester"]["name"] == "Jordan Lee"


def test_inaccessible_ticket_is_indistinguishable_from_missing(storage):
    with client_for(storage, employee_id="emp-ben") as client:
        inaccessible = client.get("/api/tickets/CHG-1042")
        missing = client.get("/api/tickets/missing")
    api.app.dependency_overrides.clear()

    assert inaccessible.status_code == 404
    assert missing.status_code == 404
    assert inaccessible.json() == missing.json() == {"detail": "Ticket unavailable"}


def test_demo_case_catalog_remains_available(storage):
    api.app.dependency_overrides[api.get_request_context] = lambda: RequestContext(
        identity_mode="demo",
        employee_id="emp-alex",
        workspace_id=storage.workspace_id,
        storage=storage,
    )
    with TestClient(api.app) as client:
        response = client.get("/api/demo/cases")
    api.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "valid-request",
        "unsafe-destination",
        "pending-approval",
        "ready-to-execute",
    ]


def test_investigation_is_validated_before_the_proposal_is_saved(storage, monkeypatch):
    policy_model = GenericFakeChatModel(
        messages=iter([AIMessage(content='{"issues": []}')])
    )
    monkeypatch.setattr(api, "create_model", lambda: policy_model)
    monkeypatch.setattr(
        "switchboard.investigation.runner.build_agent",
        lambda **_kwargs: StubInvestigator(proposal_candidate_report()),
    )

    with client_for(storage) as client:
        response = client.post("/api/investigations", json={"ticket_id": "CHG-1042"})
    api.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["result"]["report_validation"] == {
        "policy_ids": ["endpoint-change-v1", "endpoint-change-v2"],
        "evaluation_count": 1,
        "revision_count": 0,
    }
    assert len(storage.list_runs(ticket_id="CHG-1042")) == 1
    assert len(storage.list_pending_proposals()) == 1


def test_failed_report_validation_saves_neither_run_nor_proposal(storage, monkeypatch):
    report = proposal_candidate_report()
    report["findings"]["overview"] = "Rollback is never allowed."
    policy_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(content=policy_issue_response()),
                AIMessage(content=json.dumps(report["findings"])),
                AIMessage(content=policy_issue_response()),
            ]
        )
    )
    monkeypatch.setattr(api, "create_model", lambda: policy_model)
    monkeypatch.setattr(
        "switchboard.investigation.runner.build_agent",
        lambda **_kwargs: StubInvestigator(report),
    )

    with client_for(storage) as client:
        response = client.post("/api/investigations", json={"ticket_id": "CHG-1042"})
    api.app.dependency_overrides.clear()

    assert response.status_code == 502
    assert len(storage.list_runs(ticket_id="CHG-1042")) == 0
    assert len(storage.list_pending_proposals()) == 0


def test_validated_blocked_investigation_is_saved_without_a_proposal(
    storage, monkeypatch
):
    policy_model = GenericFakeChatModel(
        messages=iter([AIMessage(content='{"issues": []}')])
    )
    monkeypatch.setattr(api, "create_model", lambda: policy_model)
    monkeypatch.setattr(
        "switchboard.investigation.runner.build_agent",
        lambda **_kwargs: StubInvestigator(blocked_report()),
    )

    with client_for(storage) as client:
        response = client.post("/api/investigations", json={"ticket_id": "CHG-1042"})
    api.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["result"]["investigation"]["outcome"] == "blocked"
    assert response.json()["result"]["proposal"] is None
    assert len(storage.list_runs(ticket_id="CHG-1042")) == 1
    assert len(storage.list_pending_proposals()) == 0


def test_manual_policy_review_endpoint_is_removed(storage):
    with client_for(storage) as client:
        response = client.post(
            "/api/investigations/00000000-0000-0000-0000-000000000001/policy-review"
        )
    api.app.dependency_overrides.clear()

    assert response.status_code == 404


def test_executed_proposal_can_be_verified_and_reviewed(storage_bridge):
    storage = storage_bridge.storage(
        workspace_id="00000000-0000-0000-0000-000000000001"
    )
    with client_for(storage) as client:
        prepared = client.post("/api/demo/cases/ready-to-execute/prepare").json()
        proposal_path, query = prepared["path"].split("?")
        proposal_id = proposal_path.rsplit("/", 1)[-1]
        run_id = query.removeprefix("run=")
        base = f"/api/runs/{run_id}/proposals/{proposal_id}"

        execution = client.post(f"{base}/execution")
        verification = client.post(f"{base}/verification")
        review = client.get(base)
        ticket = client.get("/api/tickets/CHG-1042")
    api.app.dependency_overrides.clear()

    assert execution.status_code == 200
    assert verification.status_code == 200
    assert verification.json()["was_created"] is True
    assert verification.json()["verification"]["outcome"] == "delivered"
    assert review.json()["current_status"]["code"] == "delivery_verified"
    assert review.json()["verification"] == verification.json()["verification"]
    assert ticket.json()["status"] == "closed"
