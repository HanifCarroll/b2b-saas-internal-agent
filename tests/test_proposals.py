"""Validate against business records and persist without changing configuration."""

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import HttpUrl

from switchboard.integrations.change_management import save_proposal
from switchboard.integrations.database import seed_database
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import InvestigationResult
from switchboard.proposals import validate_proposal
from switchboard.scenarios import apply_scenario, load_scenarios


@pytest.fixture
def connection():
    with closing(sqlite3.connect(":memory:")) as connection:
        seed_database(connection)
        yield connection


def candidate(endpoint="https://events.acme.example/deals"):
    return InvestigationResult(
        outcome="proposal_candidate",
        ticket_id="CHG-1042",
        proposed_endpoint=HttpUrl(endpoint),
        evidence_ids=["CHG-1042"],
        summary="Candidate, not approval.",
        blockers=[],
    )


def test_save_is_durable_and_retries_return_existing_proposal(connection, tmp_path):
    session = EmployeeSession(connection, "emp-alex")
    before = list(connection.iterdump())
    path = tmp_path / "proposals.db"
    proposal = validate_proposal(candidate(), session)
    assert proposal.requester_contact_id == "contact-jordan"
    assert proposal.expected_configuration_version == 7
    assert proposal.proposed_by_employee_id == "emp-alex"
    saved = save_proposal(proposal, session, path)
    retry = save_proposal(validate_proposal(candidate(), session), session, path)
    assert saved == retry
    with closing(sqlite3.connect(path)) as storage:
        assert storage.execute("SELECT count(*) FROM proposals").fetchone()[0] == 1
    assert list(connection.iterdump()) == before


@pytest.mark.parametrize(
    ("scenario", "endpoint", "message"),
    [
        ("unauthorized-contact", "https://events.acme.example/deals", "authorized"),
        ("unregistered-destination", "https://new.acme.example/deals", "registered"),
        ("baseline", "https://other.acme.example/deals", "match the ticket"),
    ],
)
def test_validator_rejects_unsupported_candidates(
    connection, scenario, endpoint, message
):
    apply_scenario(connection, load_scenarios()[scenario])
    with pytest.raises(ValueError, match=message):
        validate_proposal(candidate(endpoint), EmployeeSession(connection, "emp-alex"))


def test_blocked_result_is_rejected(connection):
    result = InvestigationResult(
        outcome="blocked",
        ticket_id=None,
        proposed_endpoint=None,
        evidence_ids=[],
        summary="Missing evidence",
        blockers=["Missing ticket"],
    )
    with pytest.raises(ValueError, match="not a proposal candidate"):
        validate_proposal(result, EmployeeSession(connection, "emp-alex"))


@pytest.mark.parametrize("employee", ["emp-ben", "missing"])
def test_validator_enforces_employee_access(connection, employee):
    with pytest.raises(PermissionError):
        validate_proposal(candidate(), EmployeeSession(connection, employee))


@pytest.mark.parametrize("change", ["version", "inactive", "identity", "contact"])
def test_save_rechecks_records_and_identity(connection, tmp_path, change):
    session = EmployeeSession(connection, "emp-alex")
    proposal = validate_proposal(candidate(), session)
    if change == "version":
        row = connection.execute(
            "SELECT body FROM integrations WHERE id = 'int-acme-prod'"
        ).fetchone()
        record = json.loads(row[0])
        record["version"] += 1
        connection.execute(
            "UPDATE integrations SET body = ? WHERE id = 'int-acme-prod'",
            (json.dumps(record),),
        )
    elif change == "inactive":
        connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")
    elif change == "contact":
        apply_scenario(connection, load_scenarios()["unauthorized-contact"])
    else:
        proposal = proposal.model_copy(update={"proposed_by_employee_id": "emp-ben"})
    path = tmp_path / "proposals.db"
    with pytest.raises((ValueError, PermissionError)):
        save_proposal(proposal, session, path)
    assert not path.exists()


def test_closed_window_does_not_block_proposal_preparation(connection):
    apply_scenario(connection, load_scenarios()["outside-window"])
    proposal = validate_proposal(candidate(), EmployeeSession(connection, "emp-alex"))
    assert proposal.status == "pending_approval"
