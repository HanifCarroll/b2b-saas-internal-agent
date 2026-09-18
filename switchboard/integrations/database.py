"""Shared SQLite setup for the local business-system simulations."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import TypeAdapter

from switchboard.models import Customer, Employee, Integration, Ticket

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
PROPOSALS_DATABASE = FIXTURES.parent / "local" / "proposals.db"


def initialize_proposal_database(database_path: Path = PROPOSALS_DATABASE) -> None:
    """Create durable proposal storage without resetting existing proposals.

    Business records live in separate simulated systems, so their IDs are references,
    not foreign keys. Application validation must check them before saving.
    """
    # 1. Ensure the local storage directory exists.
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # 2. Create the table without replacing existing proposals.
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY NOT NULL,
                proposed_by_employee_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                requester_contact_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                integration_id TEXT NOT NULL,
                environment TEXT NOT NULL CHECK(environment IN ('sandbox', 'production')),
                current_endpoint TEXT NOT NULL,
                proposed_endpoint TEXT NOT NULL,
                expected_configuration_version INTEGER NOT NULL CHECK(expected_configuration_version >= 1),
                created_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status = 'pending_approval')
            )
            """
        )


def seed_database(*, connection: sqlite3.Connection, data_dir: Path = FIXTURES) -> None:
    """Initialize an empty database from fixtures; never reset existing records."""
    # 1. Validate every fixture before creating or inserting records.
    if connection.in_transaction:
        raise ValueError("Seed requires a connection without an active transaction")
    fixtures = {}
    for table, model in (
        ("customers", Customer),
        ("employees", Employee),
        ("integrations", Integration),
        ("tickets", Ticket),
    ):
        content = (data_dir / f"{table}.json").read_text()
        TypeAdapter(list[model]).validate_json(content)
        # Preserve source URLs and timestamps exactly after validating their shape.
        fixtures[table] = json.loads(content)
    # 2. Create the related tables in one transaction.
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
        connection.execute("BEGIN")
        connection.execute(
            "CREATE TABLE customers (id TEXT PRIMARY KEY, body TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE employees (id TEXT PRIMARY KEY, active INTEGER NOT NULL CHECK(active IN (0,1)), role TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE assignments (employee_id TEXT REFERENCES employees(id), customer_id TEXT REFERENCES customers(id), PRIMARY KEY(employee_id, customer_id))"
        )
        for table in ("integrations", "tickets"):
            connection.execute(
                f"CREATE TABLE {table} (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), body TEXT NOT NULL)"
            )
        connection.execute(
            "CREATE TABLE policies (id TEXT PRIMARY KEY, content TEXT NOT NULL)"
        )
        # 3. Insert business records and employee customer assignments.
        for record in fixtures["customers"]:
            connection.execute(
                "INSERT INTO customers VALUES (?, ?)",
                (record["id"], json.dumps(record)),
            )
        for record in fixtures["employees"]:
            connection.execute(
                "INSERT INTO employees VALUES (?, ?, ?)",
                (record["id"], record["active"], record["role"]),
            )
            connection.executemany(
                "INSERT INTO assignments VALUES (?, ?)",
                [(record["id"], customer) for customer in record["customer_ids"]],
            )
        for table in ("integrations", "tickets"):
            for record in fixtures[table]:
                connection.execute(
                    f"INSERT INTO {table} VALUES (?, ?, ?)",
                    (record["id"], record["customer_id"], json.dumps(record)),
                )
        # 4. Insert policy documents before committing the transaction.
        for path in sorted((data_dir / "policies").glob("*.md")):
            connection.execute(
                "INSERT INTO policies VALUES (?, ?)", (path.stem, path.read_text())
            )
