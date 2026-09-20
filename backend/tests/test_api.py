import pytest
from fastapi.testclient import TestClient

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
