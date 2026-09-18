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
