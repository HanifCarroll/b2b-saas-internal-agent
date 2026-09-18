"""Run review-access scenarios without an LLM, approval, or graph resumption."""

import json
import sqlite3
from contextlib import closing

import pytest
from test_proposals import candidate

from switchboard.integrations.change_management import get_proposal, save_proposal
from switchboard.integrations.database import seed_database
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.proposals import validate_proposal
from switchboard.scenarios import SCENARIOS

REVIEW_SCENARIOS = json.loads((SCENARIOS / "reviews.json").read_text())


@pytest.mark.parametrize(
    "scenario", REVIEW_SCENARIOS.values(), ids=REVIEW_SCENARIOS.keys()
)
def test_review_scenario(scenario, tmp_path):
    path = tmp_path / "proposals.db"
    with closing(sqlite3.connect(":memory:")) as connection:
        seed_database(connection=connection)
        author = EmployeeSession(db_connection=connection, employee_id="emp-alex")
        proposal, _ = save_proposal(
            proposal=validate_proposal(investigation=candidate(), session=author),
            session=author,
            database_path=path,
        )
        reviewer_id = scenario["reviewer_employee_id"]
        if "role_override" in scenario:
            connection.execute(
                "UPDATE employees SET role = ? WHERE id = ?",
                (scenario["role_override"], reviewer_id),
            )
        if scenario.get("deactivate_reviewer"):
            connection.execute(
                "UPDATE employees SET active = 0 WHERE id = ?", (reviewer_id,)
            )
        if scenario.get("revoke_assignment"):
            connection.execute(
                "DELETE FROM assignments WHERE employee_id = ? AND customer_id = 'acme'",
                (reviewer_id,),
            )
        if scenario.get("advance_configuration_version"):
            row = connection.execute(
                "SELECT body FROM integrations WHERE id = 'int-acme-prod'"
            ).fetchone()
            integration = json.loads(row[0])
            integration["version"] += 1
            connection.execute(
                "UPDATE integrations SET body = ? WHERE id = 'int-acme-prod'",
                (json.dumps(integration),),
            )
        reviewer = EmployeeSession(db_connection=connection, employee_id=reviewer_id)
        proposal_id = "missing" if scenario.get("missing_proposal") else proposal.id
        business_before = list(connection.iterdump())
        storage_before = path.read_bytes()
        if scenario["expected_access"] == "allowed":
            result = get_proposal(
                session=reviewer, proposal_id=proposal_id, database_path=path
            )
            assert result == proposal
            assert result.status == "pending_approval"
        else:
            assert scenario["expected_access"] == "denied"
            with pytest.raises(PermissionError, match="^Record unavailable$"):
                get_proposal(
                    session=reviewer, proposal_id=proposal_id, database_path=path
                )
        assert list(connection.iterdump()) == business_before
        assert path.read_bytes() == storage_before
