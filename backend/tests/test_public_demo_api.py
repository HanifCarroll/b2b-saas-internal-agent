"""Public demo HTTP requests are cookie-isolated and persona-scoped."""

import pytest
from fastapi.testclient import TestClient

from switchboard import api


@pytest.fixture
def public_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "demo")
    monkeypatch.setattr(api, "DEMO_WORKSPACES_DIRECTORY", tmp_path / "workspaces")
    return TestClient(api.app), TestClient(api.app)


def test_first_request_sets_private_workspace_cookie_and_lists_demo_choices(
    public_demo,
):
    first, _ = public_demo

    response = first.get("/api/demo/cases")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "valid-request",
        "unsafe-destination",
        "pending-approval",
        "ready-to-execute",
    ]
    cookie = response.headers["set-cookie"].lower()
    assert "switchboard-demo-workspace=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_preparing_case_isolated_by_cookie_and_switches_to_known_persona(public_demo):
    first, second = public_demo
    first.get("/api/demo/cases")
    second.get("/api/demo/cases")

    prepared = first.post("/api/demo/cases/pending-approval/prepare")

    assert prepared.status_code == 200
    assert prepared.json()["persona_id"] == "emp-priya"
    assert prepared.json()["path"].startswith("/approvals/")
    assert (
        len(
            first.get(
                "/api/approvals", headers={"X-Demo-Persona-Id": "emp-priya"}
            ).json()
        )
        == 1
    )
    assert (
        second.get("/api/approvals", headers={"X-Demo-Persona-Id": "emp-priya"}).json()
        == []
    )


def test_unknown_persona_is_rejected_without_exposing_workspace_records(public_demo):
    first, _ = public_demo

    response = first.get("/api/tickets", headers={"X-Demo-Persona-Id": "missing"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Demo persona unavailable"}
