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
        "SELECT s.name, r.temperature, r.humidity, r.timestamp "
        "FROM Sensors s "
        "JOIN SensorReadings r ON r.reading_id = ("
        "    SELECT reading_id FROM SensorReadings "
        "    WHERE sensor_id = s.sensor_id "
        "    ORDER BY timestamp DESC, reading_id DESC LIMIT 1"
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
