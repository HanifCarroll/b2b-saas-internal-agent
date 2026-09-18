"""Shared SQLite setup for the local business-system simulations."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import TypeAdapter

from switchboard.models import Customer, Employee, Integration, Ticket

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
DATABASE_PATH = FIXTURES.parent / "local" / "switchboard.db"


def initialize_proposal_database(database_path: Path = DATABASE_PATH) -> None:
    """Create proposal and approval storage without resetting existing records.

    The demo seeds these tables alongside business records. This helper also
    supports focused storage tests; it never resets existing records.
    """
    # 1. Ensure the local storage directory exists.
    database_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Create the table without replacing existing proposals.
    with closing(sqlite3.connect(database_path)) as connection, connection:
        create_change_tables(connection)


def create_change_tables(connection: sqlite3.Connection) -> None:
    """Create proposal and approval tables on the business connection."""
    # 1. Store the immutable proposal snapshot.
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
            recovery_plan TEXT NOT NULL CHECK(recovery_plan = 'manual_intervention'),
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status = 'pending_approval')
        )
        """
    )

    # 2. Keep one approval per proposal.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY NOT NULL,
            proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(id),
            approved_by_employee_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def seed_database(*, connection: sqlite3.Connection, data_dir: Path = FIXTURES) -> None:
    """Initialize an empty database from fixtures; never reset existing records."""
    # 1. Validate every fixture before creating or inserting records.
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
    connection.execute("SAVEPOINT seed_records")
    try:
        create_change_tables(connection)
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

        # Receipts share the configuration database so a future write can commit both.
        # Business functions validate proposal and approval references before writing.
        connection.execute(
            """
            CREATE TABLE executions (
                id TEXT PRIMARY KEY NOT NULL,
                proposal_id TEXT NOT NULL UNIQUE,
                executed_by_employee_id TEXT NOT NULL REFERENCES employees(id),
                approval_id TEXT,
                executed_at TEXT NOT NULL,
                previous_configuration_version INTEGER NOT NULL
                    CHECK(previous_configuration_version >= 1),
                resulting_configuration_version INTEGER NOT NULL
                    CHECK(resulting_configuration_version = previous_configuration_version + 1)
            )
            """
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

    except BaseException:
        connection.execute("ROLLBACK TO seed_records")
        connection.execute("RELEASE seed_records")
        raise
    else:
        connection.execute("RELEASE seed_records")
