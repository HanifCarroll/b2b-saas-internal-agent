"""Validate against business records and persist without changing configuration."""

import json
import sqlite3
from contextlib import closing

import pytest
from pydantic import HttpUrl

from switchboard.integrations.change_management import get_proposal, save_proposal
from switchboard.integrations.database import seed_database
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.models import InvestigationFindings, InvestigationResult
from switchboard.proposals import validate_proposal
from switchboard.scenarios import apply_scenario, load_scenarios


@pytest.fixture
def connection():
    with closing(sqlite3.connect(":memory:")) as connection:
        seed_database(connection=connection)
        yield connection


def candidate(endpoint="https://events.acme.example/deals"):
    return InvestigationResult(
        outcome="proposal_candidate",
        ticket_id="CHG-1042",
        proposed_endpoint=HttpUrl(endpoint),
        evidence_ids=["CHG-1042"],
        findings=InvestigationFindings(
            overview="Candidate, not approval.",
            checks=[],
            policy_requirements=[],
            gaps=[],
            next_step="Review the evidence before proceeding.",
        ),
        blockers=[],
    )


def test_save_is_durable_and_retries_return_existing_proposal(connection, tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    session = EmployeeSession(db_connection=connection, employee_id="emp-alex")
    before = list(connection.iterdump())
    path = tmp_path / "proposals.db"
    proposal = validate_proposal(investigation=candidate(), session=session)

    # 2. Verify the expected result and any safety guarantees.
    assert proposal.requester_contact_id == "contact-jordan"
    assert proposal.expected_configuration_version == 7
    assert proposal.proposed_by_employee_id == "emp-alex"
    saved, created = save_proposal(
        proposal=proposal, session=session, database_path=path
    )
    retry, retry_created = save_proposal(
        proposal=validate_proposal(investigation=candidate(), session=session),
        session=session,
        database_path=path,
    )

    assert created is True
    assert retry_created is False
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
    # 1. Set up inputs and exercise the behavior under test.
    apply_scenario(db_connection=connection, scenario=load_scenarios()[scenario])

    with pytest.raises(ValueError, match=message):
        validate_proposal(
            investigation=candidate(endpoint),
            session=EmployeeSession(db_connection=connection, employee_id="emp-alex"),
        )


def test_blocked_result_is_rejected(connection):
    # 1. Set up inputs and exercise the behavior under test.
    result = InvestigationResult(
        outcome="blocked",
        ticket_id=None,
        proposed_endpoint=None,
        evidence_ids=[],
        findings=InvestigationFindings(
            overview="Missing evidence",
            checks=[],
            policy_requirements=[],
            gaps=[],
            next_step="Review the evidence before proceeding.",
        ),
        blockers=["Missing ticket"],
    )

    with pytest.raises(ValueError, match="not a proposal candidate"):
        validate_proposal(
            investigation=result,
            session=EmployeeSession(db_connection=connection, employee_id="emp-alex"),
        )


@pytest.mark.parametrize("employee", ["emp-ben", "missing"])
def test_validator_enforces_employee_access(connection, employee):
    with pytest.raises(PermissionError):
        validate_proposal(
            investigation=candidate(),
            session=EmployeeSession(db_connection=connection, employee_id=employee),
        )


@pytest.mark.parametrize("change", ["version", "inactive", "identity", "contact"])
def test_save_rechecks_records_and_identity(connection, tmp_path, change):
    # 1. Set up inputs and exercise the behavior under test.
    session = EmployeeSession(db_connection=connection, employee_id="emp-alex")
    proposal = validate_proposal(investigation=candidate(), session=session)
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
        apply_scenario(
            db_connection=connection, scenario=load_scenarios()["unauthorized-contact"]
        )
    else:
        proposal = proposal.model_copy(update={"proposed_by_employee_id": "emp-ben"})

    path = tmp_path / "proposals.db"

    with pytest.raises((ValueError, PermissionError)):
        save_proposal(proposal=proposal, session=session, database_path=path)

    # 2. Verify the expected result and any safety guarantees.
    assert not path.exists()


def test_closed_window_does_not_block_proposal_preparation(connection):
    # 1. Set up inputs and exercise the behavior under test.
    apply_scenario(
        db_connection=connection, scenario=load_scenarios()["outside-window"]
    )
    proposal = validate_proposal(
        investigation=candidate(),
        session=EmployeeSession(db_connection=connection, employee_id="emp-alex"),
    )

    # 2. Verify the expected result and any safety guarantees.
    assert proposal.status == "pending_approval"


@pytest.mark.parametrize(
    "role", ["support_specialist", "implementation_engineer", "technical_lead"]
)
def test_assigned_roles_can_read_proposal_after_configuration_changes(
    connection, tmp_path, role
):
    # 1. Set up inputs and exercise the behavior under test.
    session = EmployeeSession(db_connection=connection, employee_id="emp-alex")
    proposal, _ = save_proposal(
        proposal=validate_proposal(investigation=candidate(), session=session),
        session=session,
        database_path=tmp_path / "proposals.db",
    )
    connection.execute("UPDATE employees SET role = ? WHERE id = 'emp-priya'", (role,))
    connection.execute("DELETE FROM integrations")
    apply_scenario(
        db_connection=connection, scenario=load_scenarios()["unauthorized-contact"]
    )
    before = list(connection.iterdump())
    path = tmp_path / "proposals.db"
    stored_before = path.read_bytes()

    # 2. Verify the expected result and any safety guarantees.
    assert (
        get_proposal(
            session=EmployeeSession(db_connection=connection, employee_id="emp-priya"),
            proposal_id=proposal.id,
            database_path=path,
        )
        == proposal
    )
    assert list(connection.iterdump()) == before
    assert path.read_bytes() == stored_before


@pytest.mark.parametrize(
    "denial",
    [
        "missing",
        "cross_customer",
        "inactive",
        "unknown_employee",
        "unknown_role",
        "revoked_assignment",
    ],
)
def test_proposal_reads_hide_missing_and_inaccessible_records(
    connection, tmp_path, denial
):
    # 1. Set up inputs and exercise the behavior under test.
    path = tmp_path / "proposals.db"
    session = EmployeeSession(db_connection=connection, employee_id="emp-alex")
    proposal, _ = save_proposal(
        proposal=validate_proposal(investigation=candidate(), session=session),
        session=session,
        database_path=path,
    )
    proposal_id = proposal.id
    if denial == "missing":
        proposal_id = "missing"
    elif denial == "cross_customer":
        session = EmployeeSession(db_connection=connection, employee_id="emp-ben")
    elif denial == "inactive":
        connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")
    elif denial == "unknown_employee":
        session = EmployeeSession(db_connection=connection, employee_id="missing")
    elif denial == "unknown_role":
        connection.execute(
            "UPDATE employees SET role = 'unknown' WHERE id = 'emp-alex'"
        )
    else:
        connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-alex'")

    with pytest.raises(PermissionError, match="^Record unavailable$"):
        get_proposal(session=session, proposal_id=proposal_id, database_path=path)


def test_read_does_not_create_missing_proposal_database(connection, tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    path = tmp_path / "missing.db"

    with pytest.raises(PermissionError, match="^Record unavailable$"):
        get_proposal(
            session=EmployeeSession(db_connection=connection, employee_id="emp-alex"),
            proposal_id="missing",
            database_path=path,
        )

    # 2. Verify the expected result and any safety guarantees.
    assert not path.exists()
