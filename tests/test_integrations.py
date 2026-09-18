"""Run with: uv run pytest -v

Pytest supplies arguments marked with @pytest.fixture. Each test gets fresh
records and a fresh database; changes in one test cannot affect another.
"""

import json
import shutil
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from switchboard.integrations.configuration_service import get_integration
from switchboard.integrations.customer_registry import get_customer
from switchboard.integrations.database import FIXTURES, seed_database
from switchboard.integrations.employee_directory import EmployeeSession
from switchboard.integrations.policy_library import list_policies
from switchboard.integrations.support_desk import get_ticket
from switchboard.models import Customer, Integration, Ticket


@pytest.fixture
def database():
    """A fresh database containing the normal Switchboard records."""
    with closing(sqlite3.connect(":memory:")) as connection:
        seed_database(connection=connection)
        yield connection


@pytest.fixture
def sample_records():
    """Editable copies of the JSON records, without changing project files."""
    return {
        table: json.loads((FIXTURES / f"{table}.json").read_text())
        for table in ("employees", "customers", "integrations", "tickets")
    }


def assert_seed_rejected(tmp_path, records, *, invalid_field):
    """Load modified records and check both the validation error and empty DB."""
    data_dir = tmp_path / "data"
    shutil.copytree(FIXTURES, data_dir)
    for table, rows in records.items():
        (data_dir / f"{table}.json").write_text(json.dumps(rows))

    with closing(sqlite3.connect(":memory:")) as connection:
        with pytest.raises(ValidationError) as error:
            seed_database(connection=connection, data_dir=data_dir)

        # Pydantic identifies the first record (index 0) and the invalid field.
        assert error.value.errors()[0]["loc"][:2] == (0, invalid_field)
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_missing_fixture_files_leave_database_empty(tmp_path):
    with closing(sqlite3.connect(":memory:")) as connection:
        with pytest.raises(FileNotFoundError):
            seed_database(connection=connection, data_dir=tmp_path)

        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_employee_active_must_be_a_boolean(sample_records, tmp_path):
    sample_records["employees"][0]["active"] = "true"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="active")


def test_employee_role_must_be_recognized(sample_records, tmp_path):
    sample_records["employees"][0]["role"] = "admin"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="role")


def test_employee_id_cannot_be_whitespace(sample_records, tmp_path):
    sample_records["employees"][0]["id"] = " "

    assert_seed_rejected(tmp_path, sample_records, invalid_field="id")


def test_registered_destination_requires_a_valid_url(sample_records, tmp_path):
    sample_records["customers"][0]["registered_destinations"][0]["url"] = "bad-url"

    assert_seed_rejected(
        tmp_path, sample_records, invalid_field="registered_destinations"
    )


def test_change_window_requires_a_valid_time(sample_records, tmp_path):
    sample_records["customers"][0]["production_change_window"]["start"] = "25:00"

    assert_seed_rejected(
        tmp_path, sample_records, invalid_field="production_change_window"
    )


def test_integration_environment_must_be_recognized(sample_records, tmp_path):
    sample_records["integrations"][0]["environment"] = "unknown"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="environment")


def test_integration_version_must_be_an_integer(sample_records, tmp_path):
    sample_records["integrations"][0]["version"] = "7"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="version")


def test_integration_version_must_be_positive(sample_records, tmp_path):
    sample_records["integrations"][0]["version"] = 0

    assert_seed_rejected(tmp_path, sample_records, invalid_field="version")


def test_ticket_creation_time_must_be_a_datetime(sample_records, tmp_path):
    sample_records["tickets"][0]["created_at"] = "not-a-date"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="created_at")


def test_ticket_creation_time_requires_a_timezone(sample_records, tmp_path):
    sample_records["tickets"][0]["created_at"] = "2026-09-22T13:30:00"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="created_at")


def test_ticket_requires_a_subject(sample_records, tmp_path):
    del sample_records["tickets"][0]["subject"]

    assert_seed_rejected(tmp_path, sample_records, invalid_field="subject")


def test_ticket_rejects_unrecognized_fields(sample_records, tmp_path):
    sample_records["tickets"][0]["unexpected_field"] = "value"

    assert_seed_rejected(tmp_path, sample_records, invalid_field="unexpected_field")


def test_alex_can_read_acme_ticket(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    ticket = get_ticket(session=alex, ticket_id="CHG-1042")

    assert isinstance(ticket, Ticket)
    assert ticket.integration_id == "int-acme-prod"


def test_alex_can_read_acme_customer(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    customer = get_customer(session=alex, customer_id="acme")

    assert isinstance(customer, Customer)
    assert customer.name == "Acme Services"


def test_alex_can_read_acme_production_configuration(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    integration = get_integration(session=alex, integration_id="int-acme-prod")

    assert isinstance(integration, Integration)
    assert integration.version == 7


def test_alex_can_read_acme_sandbox_configuration(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    integration = get_integration(session=alex, integration_id="int-acme-sandbox")

    assert integration.environment == "sandbox"


def test_policy_library_includes_current_and_superseded_versions(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    policies = {policy["id"]: policy["content"] for policy in list_policies(alex)}

    assert len(policies) == 2
    assert "status: superseded" in policies["endpoint-change-v1"]
    assert "status: approved" in policies["endpoint-change-v2"]


def test_alex_cannot_read_globex_customer(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    with pytest.raises(PermissionError):
        get_customer(session=alex, customer_id="globex")


def test_alex_cannot_read_globex_configuration(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="int-globex-prod")


def test_missing_integration_is_unavailable(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="missing")


def test_sql_in_record_id_cannot_bypass_access_checks(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="int-acme-prod' OR 1=1 --")


def test_ben_can_read_globex_configuration(database):
    ben = EmployeeSession(db_connection=database, employee_id="emp-ben")

    integration = get_integration(session=ben, integration_id="int-globex-prod")

    assert integration.customer_id == "globex"


def test_ben_cannot_read_acme_ticket(database):
    ben = EmployeeSession(db_connection=database, employee_id="emp-ben")

    with pytest.raises(PermissionError):
        get_ticket(session=ben, ticket_id="CHG-1042")


def test_unknown_employee_cannot_read_policies(database):
    unknown_employee = EmployeeSession(db_connection=database, employee_id="unknown")

    with pytest.raises(PermissionError):
        list_policies(unknown_employee)


def test_successful_and_denied_reads_leave_database_unchanged(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    before = list(database.iterdump())

    get_ticket(session=alex, ticket_id="CHG-1042")
    get_customer(session=alex, customer_id="acme")
    get_integration(session=alex, integration_id="int-acme-prod")
    list_policies(alex)

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="int-globex-prod")

    # 2. Verify the expected result and any safety guarantees.
    assert list(database.iterdump()) == before


def test_seeding_existing_database_is_rejected_without_changes(database):
    before = list(database.iterdump())

    with pytest.raises(sqlite3.OperationalError):
        seed_database(connection=database)

    assert list(database.iterdump()) == before


def test_ticket_read_rejects_invalid_stored_datetime(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    record = get_ticket(session=alex, ticket_id="CHG-1042").model_dump(mode="json")
    record["created_at"] = "invalid"
    database.execute(
        "UPDATE tickets SET body = ? WHERE id = ?",
        (json.dumps(record), "CHG-1042"),
    )

    with pytest.raises(ValidationError):
        get_ticket(session=alex, ticket_id="CHG-1042")


def test_customer_read_rejects_invalid_stored_name(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    record = get_customer(session=alex, customer_id="acme").model_dump(mode="json")
    record["name"] = 123
    database.execute(
        "UPDATE customers SET body = ? WHERE id = ?",
        (json.dumps(record), "acme"),
    )

    with pytest.raises(ValidationError):
        get_customer(session=alex, customer_id="acme")


def test_configuration_read_rejects_invalid_stored_version(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    record = get_integration(session=alex, integration_id="int-acme-prod").model_dump(
        mode="json"
    )
    record["version"] = 0
    database.execute(
        "UPDATE integrations SET body = ? WHERE id = ?",
        (json.dumps(record), "int-acme-prod"),
    )

    with pytest.raises(ValidationError):
        get_integration(session=alex, integration_id="int-acme-prod")


def test_configuration_read_does_not_expose_extra_credential_field(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    record = get_integration(session=alex, integration_id="int-acme-prod").model_dump(
        mode="json"
    )
    record["credential"] = "test-secret"
    database.execute(
        "UPDATE integrations SET body = ? WHERE id = ?",
        (json.dumps(record), "int-acme-prod"),
    )

    integration = get_integration(session=alex, integration_id="int-acme-prod")

    # 2. Verify the expected result and any safety guarantees.
    assert "credential" not in integration.model_dump()


def test_existing_session_uses_updated_support_role(database):
    # 1. Set up inputs and exercise the behavior under test.
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    database.execute(
        "UPDATE employees SET role = 'support_specialist' WHERE id = 'emp-alex'"
    )

    # 2. Verify the expected result and any safety guarantees.
    assert get_ticket(session=alex, ticket_id="CHG-1042").status == "open"

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="int-acme-prod")


def test_existing_session_rejects_unrecognized_role(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    database.execute("UPDATE employees SET role = 'unknown_role' WHERE id = 'emp-alex'")

    with pytest.raises(PermissionError):
        get_ticket(session=alex, ticket_id="CHG-1042")


def test_existing_session_loses_access_when_employee_is_deactivated(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    database.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")

    with pytest.raises(PermissionError):
        list_policies(alex)

    with pytest.raises(PermissionError):
        get_integration(session=alex, integration_id="int-acme-prod")


def test_existing_session_loses_access_when_customer_assignment_is_removed(database):
    alex = EmployeeSession(db_connection=database, employee_id="emp-alex")
    database.execute("DELETE FROM assignments WHERE employee_id = 'emp-alex'")

    with pytest.raises(PermissionError):
        get_ticket(session=alex, ticket_id="CHG-1042")


def test_records_persist_after_reopening_database_in_read_only_mode(tmp_path):
    # 1. Set up inputs and exercise the behavior under test.
    path = tmp_path / "switchboard.db"
    with closing(sqlite3.connect(path)) as connection:
        seed_database(connection=connection)
        original = list(connection.iterdump())

    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        alex = EmployeeSession(db_connection=connection, employee_id="emp-alex")
        integration = get_integration(session=alex, integration_id="int-acme-prod")

        # 2. Verify the expected result and any safety guarantees.
        assert integration.version == 7
        assert list(connection.iterdump()) == original
