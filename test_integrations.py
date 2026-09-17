"""Run with: uv run pytest -v"""

import json
import shutil
import sqlite3
import tempfile
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

from integrations.configuration_service import get_integration
from integrations.customer_registry import get_customer
from integrations.database import DATA, seed_database
from integrations.employee_directory import EmployeeSession
from integrations.policy_library import list_policies
from integrations.support_desk import get_ticket
from models import Customer, Integration, Ticket


def test_failed_seed_leaves_database_empty():
    connection = sqlite3.connect(":memory:")
    try:
        with tempfile.TemporaryDirectory() as directory:
            with pytest.raises(FileNotFoundError):
                seed_database(connection, Path(directory))
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
    finally:
        connection.close()


@pytest.mark.parametrize(
    "table,field,value",
    (
        ("employees", "active", "true"),
        ("employees", "role", "admin"),
        ("employees", "id", " "),
        (
            "customers",
            "registered_destinations",
            [{"environment": "production", "url": "bad-url"}],
        ),
        (
            "customers",
            "production_change_window",
            {"weekday": "Tuesday", "start": "25:00", "end": "16:00", "timezone": "UTC"},
        ),
        ("integrations", "environment", "unknown"),
        ("integrations", "version", "7"),
        ("integrations", "version", 0),
        ("tickets", "created_at", "not-a-date"),
        ("tickets", "created_at", "2026-09-22T13:30:00"),
        ("tickets", "subject", None),
        ("tickets", "unexpected_field", "value"),
    ),
)
def test_invalid_fixtures_leave_database_empty(table, field, value):
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        shutil.copytree(DATA, data_dir)
        path = data_dir / f"{table}.json"
        records = json.loads(path.read_text())
        if value is None:
            del records[0][field]
        else:
            records[0][field] = value
        path.write_text(json.dumps(records))
        connection = sqlite3.connect(":memory:")
        try:
            with pytest.raises(ValidationError) as error:
                seed_database(connection, data_dir)
            assert error.value.errors()[0]["loc"][:2] == (0, field)
            assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
        finally:
            connection.close()


def test_reads_return_models_and_reject_invalid_stored_values():
    connection = sqlite3.connect(":memory:")
    try:
        seed_database(connection)
        alex = EmployeeSession(connection, "emp-alex")
        cases = (
            (
                "tickets",
                "CHG-1042",
                partial(get_ticket, alex),
                Ticket,
                "created_at",
                "invalid",
            ),
            ("customers", "acme", partial(get_customer, alex), Customer, "name", 123),
            (
                "integrations",
                "int-acme-prod",
                partial(get_integration, alex),
                Integration,
                "version",
                0,
            ),
        )
        for table, record_id, read, model, field, value in cases:
            assert isinstance(read(record_id), model)
            record = read(record_id).model_dump(mode="json")
            record[field] = value
            connection.execute(
                f"UPDATE {table} SET body = ? WHERE id = ?",
                (json.dumps(record), record_id),
            )
            with pytest.raises(ValidationError):
                read(record_id)
    finally:
        connection.close()


def test_read_only_access_and_persistence():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "switchboard.db"
        connection = sqlite3.connect(path)
        try:
            seed_database(connection)
            original = list(connection.iterdump())
            alex = EmployeeSession(connection, "emp-alex")
            assert get_ticket(alex, "CHG-1042").integration_id == "int-acme-prod"
            assert get_customer(alex, "acme").name == "Acme Services"
            assert get_integration(alex, "int-acme-prod").version == 7
            assert get_integration(alex, "int-acme-sandbox").environment == "sandbox"
            assert len(list_policies(alex)) == 2
            assert "status: superseded" in list_policies(alex)[0]["content"]
            assert "status: approved" in list_policies(alex)[1]["content"]
            for read, record_id in (
                (partial(get_customer, alex), "globex"),
                (partial(get_integration, alex), "int-globex-prod"),
                (partial(get_integration, alex), "missing"),
                (partial(get_integration, alex), "int-acme-prod' OR 1=1 --"),
            ):
                with pytest.raises(PermissionError):
                    read(record_id)
            ben = EmployeeSession(connection, "emp-ben")
            assert get_integration(ben, "int-globex-prod").customer_id == "globex"
            with pytest.raises(PermissionError):
                get_ticket(ben, "CHG-1042")
            with pytest.raises(PermissionError):
                list_policies(EmployeeSession(connection, "unknown"))
            assert list(connection.iterdump()) == original
            with pytest.raises(sqlite3.OperationalError):
                seed_database(connection)
            assert list(connection.iterdump()) == original
            record = get_integration(alex, "int-acme-prod").model_dump(mode="json")
            record["credential"] = "test-secret"
            connection.execute(
                "UPDATE integrations SET body = ? WHERE id = ?",
                (json.dumps(record), record["id"]),
            )
            assert "credential" not in get_integration(alex, record["id"]).model_dump()
            connection.execute(
                "UPDATE employees SET role = 'support_specialist' WHERE id = 'emp-alex'"
            )
            assert get_ticket(alex, "CHG-1042").status == "open"
            with pytest.raises(PermissionError):
                get_integration(alex, "int-acme-prod")
            connection.execute(
                "UPDATE employees SET role = 'unknown_role' WHERE id = 'emp-alex'"
            )
            with pytest.raises(PermissionError):
                get_ticket(alex, "CHG-1042")
            connection.execute(
                "UPDATE employees SET role = 'implementation_engineer', active = 0 WHERE id = 'emp-alex'"
            )
            with pytest.raises(PermissionError):
                list_policies(alex)
            with pytest.raises(PermissionError):
                get_integration(alex, "int-acme-prod")
            connection.execute("UPDATE employees SET active = 1 WHERE id = 'emp-alex'")
            connection.execute("DELETE FROM assignments WHERE employee_id = 'emp-alex'")
            with pytest.raises(PermissionError):
                get_ticket(alex, "CHG-1042")
            connection.rollback()
        finally:
            connection.close()
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            alex = EmployeeSession(connection, "emp-alex")
            assert get_integration(alex, "int-acme-prod").version == 7
            assert list(connection.iterdump()) == original
        finally:
            connection.close()
