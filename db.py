import re
import secrets
import sqlite3
from pathlib import Path

from flask import g

DATABASE = str(Path(__file__).resolve().parent / "smart_store.db")

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
        "SELECT customer_id, first_name, last_name, address, phone, email, "
        "membership_number, total_points "
        "FROM Customers ORDER BY last_name, first_name"
    )
    return cur.fetchall()


def generate_membership_number(db):
    while True:
        membership_number = f"CUST-{secrets.token_hex(4).upper()}"
        exists = db.execute(
            "SELECT 1 FROM Customers WHERE membership_number = ?",
            (membership_number,),
        ).fetchone()
        if not exists:
            return membership_number


def add_customer(first_name, last_name, address, phone=None, email=None):
    db = get_db()
    db.execute(
        "INSERT INTO Customers "
        "(first_name, last_name, address, phone, email, membership_number) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            first_name,
            last_name,
            address,
            phone,
            email,
            generate_membership_number(db),
        ),
    )
    db.commit()

# PRODUCT METHODS
def get_product(product_id):
    db = get_db()

    cur = db.execute(
        "SELECT product_id, name, category, upc, upc AS barcode, epc, SDK, "
        "price, quantity, company "
        "FROM Products WHERE product_id = ?",
        (product_id,),
    )
    return cur.fetchone()


def get_product_by_barcode(barcode):
    db = get_db()

    cur = db.execute(
        "SELECT product_id, name, category, upc, upc AS barcode, epc, SDK, "
        "price, quantity, company "
        "FROM Products WHERE upc = ?",
        (barcode,),
    )
    return cur.fetchone()


def add_product(
    name,
    price,
    quantity,
    barcode=None,
    SDK=None,
    company=None,
    category="Uncategorized",
    epc=None,
    upc=None,
):
    upc = upc or barcode
    db = get_db()
    db.execute(
        "INSERT INTO Products "
        "(name, category, upc, epc, SDK, price, quantity, company) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, category, upc, epc, SDK, price, quantity, company),
    )
    db.commit()


def edit_product(
    product_id,
    name=None,
    barcode=None,
    SDK=None,
    price=None,
    quantity=None,
    company=None,
    category=None,
    epc=None,
    upc=None,
):
    existing = get_product(product_id)
    if existing is None:
        return False

    upc = upc or barcode
    upc = existing["upc"] if upc is None else upc
    name = existing["name"] if name is None else name
    category = existing["category"] if category is None else category
    epc = existing["epc"] if epc is None else epc
    SDK = existing["SDK"] if SDK is None else SDK
    price = existing["price"] if price is None else price
    quantity = existing["quantity"] if quantity is None else quantity
    company = existing["company"] if company is None else company

    # Allows us to use this method to increase or decrease quantity as well
    if isinstance(quantity, str):
        if "+" in quantity:
            quantity = existing["quantity"] + int(re.sub(r"\D", "", quantity))
        elif "-" in quantity:
            quantity = existing["quantity"] - int(re.sub(r"\D", "", quantity))

    db = get_db()
    db.execute(
        "UPDATE Products SET name = ?, category = ?, upc = ?, epc = ?, SDK = ?, "
        "price = ?, quantity = ?, company = ? WHERE product_id = ?",
        (name, category, upc, epc, SDK, price, quantity, company, product_id),
    )
    db.commit()
    return True


def add_product_reception(product_id, quantity_received, supplier=None):
    db = get_db()
    db.execute(
        "INSERT INTO ProductReceptions "
        "(product_id, quantity_received, supplier) VALUES (?, ?, ?)",
        (product_id, quantity_received, supplier),
    )
    db.execute(
        "UPDATE Products SET quantity = quantity + ? WHERE product_id = ?",
        (quantity_received, product_id),
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


def get_or_create_sensor(name, location):
    db = get_db()
    sensor = db.execute("SELECT sensor_id FROM Sensors WHERE name = ?", (name,)).fetchone()
    if sensor:
        return sensor["sensor_id"]
    cur = db.execute(
        "INSERT INTO Sensors (name, location, temp_threshold, humid_threshold) "
        "VALUES (?, ?, ?, ?)",
        (name, location, 99.0, 100.0),
    )
    db.commit()
    return cur.lastrowid


def set_sensor_thresholds(name, temp_threshold, humid_threshold):
    db = get_db()
    sensor = db.execute("SELECT sensor_id FROM Sensors WHERE name = ?", (name,)).fetchone()
    if sensor:
        db.execute(
            "UPDATE Sensors SET temp_threshold = ?, humid_threshold = ? "
            "WHERE sensor_id = ?",
            (temp_threshold, humid_threshold, sensor["sensor_id"]),
        )
    else:
        db.execute(
            "INSERT INTO Sensors (name, location, temp_threshold, humid_threshold) "
            "VALUES (?, ?, ?, ?)",
            (name, name, temp_threshold, humid_threshold),
        )
    db.commit()


def get_sensor_thresholds(sensor_id):
    db = get_db()
    return db.execute(
        "SELECT temp_threshold, humid_threshold FROM Sensors WHERE sensor_id = ?",
        (sensor_id,),
    ).fetchone()


def create_alert(reading_id, alert_type):
    db = get_db()
    cur = db.execute(
        "INSERT INTO Alerts (reading_id, alert_type) VALUES (?, ?)",
        (reading_id, alert_type),
    )
    db.commit()
    return cur.lastrowid


def get_pending_alerts():
    db = get_db()
    cur = db.execute(
        "SELECT a.alert_id, s.name AS sensor_name, a.alert_type, r.temperature, r.humidity, "
        "       s.temp_threshold, s.humid_threshold "
        "FROM Alerts a "
        "JOIN SensorReadings r ON r.reading_id = a.reading_id "
        "JOIN Sensors s ON s.sensor_id = r.sensor_id "
        "WHERE a.resolved = 0 "
        "ORDER BY a.alert_id"
    )
    return cur.fetchall()


def mark_alerts_sent(alert_ids):
    if not alert_ids:
        return
    db = get_db()
    placeholders = ",".join("?" for _ in alert_ids)
    db.execute(
        f"UPDATE Alerts SET resolved = 1 WHERE alert_id IN ({placeholders})",
        tuple(alert_ids),
    )
    db.commit()


def add_sensor_reading(sensor_id, temperature, humidity):
    db = get_db()
    cur = db.execute(
        "INSERT INTO SensorReadings (sensor_id, temperature, humidity) VALUES (?, ?, ?)",
        (sensor_id, temperature, humidity),
    )
    db.commit()
    return cur.lastrowid


def get_latest_readings():
    db = get_db()
    cur = db.execute(
        "SELECT r.reading_id, s.name, r.temperature, r.humidity, r.timestamp "
        "FROM Sensors s "
        "JOIN SensorReadings r ON r.reading_id = ("
        "    SELECT reading_id FROM SensorReadings "
        "    WHERE sensor_id = s.sensor_id "
        "    ORDER BY reading_id DESC LIMIT 1"
        ") "
        "ORDER BY s.name"
    )
    return cur.fetchall()


def migrate_sensor_thresholds(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(Sensors)")}
    if "temp_min" not in columns and "temp_max" not in columns:
        return

    if "temp_threshold" not in columns:
        db.execute(
            "ALTER TABLE Sensors ADD COLUMN temp_threshold REAL NOT NULL DEFAULT 99.0"
        )
    if "humid_threshold" not in columns:
        db.execute(
            "ALTER TABLE Sensors ADD COLUMN humid_threshold REAL NOT NULL DEFAULT 100.0"
        )

    db.execute(
        "UPDATE Sensors SET temp_threshold = temp_max, humid_threshold = humid_max"
    )
    db.execute("ALTER TABLE Sensors DROP COLUMN temp_min")
    db.execute("ALTER TABLE Sensors DROP COLUMN temp_max")
    db.execute("ALTER TABLE Sensors DROP COLUMN humid_min")
    db.execute("ALTER TABLE Sensors DROP COLUMN humid_max")


def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource("db/schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        migrate_sensor_thresholds(db)
        db.commit()


def get_active_recipient():
    row = get_db().execute(
        "SELECT value FROM AppSettings WHERE name = 'active_recipient'"
    ).fetchone()
    return row["value"] if row else None


def set_active_recipient(email):
    database = get_db()
    database.execute(
        "INSERT INTO AppSettings (name, value) VALUES ('active_recipient', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value", (email,)
    )
    database.commit()
