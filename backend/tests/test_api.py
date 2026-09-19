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
