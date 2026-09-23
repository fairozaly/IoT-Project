from pathlib import Path
import sqlite3
from typing import Any

DATABASE_PATH = "data/smartstore.db"

def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database() -> None:
    with get_connection() as connection:
        with open("db/schema.sql", "r") as file:
            schema = file.read()

        connection.executescript(schema)

def list_customers() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT customer_id, first_name, last_name, email
            FROM customers
            ORDER BY customer_id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]

def create_customer(first_name: str, last_name: str, email: str) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO customers (first_name, last_name, email)
            VALUES (?, ?, ?)
            """,
            (first_name, last_name, email),
        )
        row = connection.execute(
            """
            SELECT customer_id, first_name, last_name, email
            FROM customers
            WHERE customer_id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)