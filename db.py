import sqlite3

from flask import g

DATABASE = "smart_store.db"

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def get_customers():
    db = get_db()
    cur = db.execute(
        "SELECT customer_id, first_name, last_name, address, phone, email "
        "FROM Customers ORDER BY last_name, first_name"
    )
    return cur.fetchall()


def add_customer(first_name, last_name, address, phone=None, email=None):
    db = get_db()
    db.execute(
        "INSERT INTO Customers (first_name, last_name, address, phone, email) "
        "VALUES (?, ?, ?, ?, ?)",
        (first_name, last_name, address, phone, email),
    )
    db.commit()


def get_customer_by_email(email):
    if not email:
        return None
    db = get_db()
    return db.execute("SELECT customer_id FROM Customers WHERE email = ?", (email,)).fetchone()


def get_customer_by_phone(phone):
    if not phone:
        return None
    db = get_db()
    return db.execute("SELECT customer_id FROM Customers WHERE phone = ?", (phone,)).fetchone()


def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource("db/schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        db.commit()
