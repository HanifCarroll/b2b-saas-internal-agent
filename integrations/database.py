"""Shared SQLite setup for the local business-system simulations."""

import json
import sqlite3
from pathlib import Path

from pydantic import TypeAdapter

from models import Customer, Employee, Integration, Ticket

DATA = Path(__file__).resolve().parent.parent / "data"


def seed_database(connection: sqlite3.Connection, data_dir: Path = DATA) -> None:
    """Initialize an empty database from fixtures; never reset existing records."""
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
        for path in sorted((data_dir / "policies").glob("*.md")):
            connection.execute(
                "INSERT INTO policies VALUES (?, ?)", (path.stem, path.read_text())
            )
