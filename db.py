import re
import sqlite3
from pathlib import Path

from flask import current_app, g
from validation_security import normalize_quebec_phone

DATABASE = str(Path(__file__).resolve().parent / "smart_store.db")

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        # Keep the existing file as the production default, while allowing
        # Flask test apps (and local tools) to provide an isolated database.
        database_path = current_app.config.get("DATABASE", DATABASE)
        db = g._database = sqlite3.connect(database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
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


def delete_customer(customer_id):
    db = get_db()
    try:
        result = db.execute(
            "DELETE FROM Customers WHERE customer_id = ?", (customer_id,)
        )
        db.commit()
        return result.rowcount > 0
    except sqlite3.IntegrityError:
        db.rollback()
        return False


def add_customer(first_name, last_name, address, phone=None, email=None):
    normalized_phone = normalize_quebec_phone(phone) if phone else None
    if phone and normalized_phone is None:
        raise ValueError("phone must be a valid Quebec phone number")
    db = get_db()
    db.execute(
        "INSERT INTO Customers "
        "(first_name, last_name, address, phone, email) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            first_name,
            last_name,
            address,
            normalized_phone,
            email,
        ),
    )
    db.commit()

# PRODUCT METHODS
def get_product(product_id):
    db = get_db()

    cur = db.execute(
        "SELECT product_id, name, category, upc, upc AS barcode, SDK, "
        "price, cost_price, taxable, quantity, company, image_url "
        "FROM Products WHERE product_id = ?",
        (product_id,),
    )
    return cur.fetchone()


def get_product_by_barcode(barcode):
    db = get_db()

    cur = db.execute(
        "SELECT product_id, name, category, upc, upc AS barcode, SDK, "
        "price, cost_price, taxable, quantity, company, image_url "
        "FROM Products WHERE upc = ?",
        (barcode,),
    )
    return cur.fetchone()


DEFAULT_LOW_STOCK_THRESHOLD = 5


def get_category_stock_thresholds():
    return get_db().execute(
        """
        SELECT DISTINCT p.category, COALESCE(t.threshold, ?) AS threshold
        FROM Products p LEFT JOIN CategoryStockThresholds t USING (category)
        ORDER BY p.category
        """, (DEFAULT_LOW_STOCK_THRESHOLD,),
    ).fetchall()


def set_category_stock_threshold(category, threshold):
    db = get_db()
    with db:
        result = db.execute(
            """
            INSERT INTO CategoryStockThresholds (category, threshold)
            SELECT ?, ? WHERE EXISTS (SELECT 1 FROM Products WHERE category = ?)
            ON CONFLICT (category) DO UPDATE SET threshold = excluded.threshold
            """, (category, threshold, category),
        )
    return result.rowcount > 0


def get_products():
    db = get_db()
    return db.execute(
        "SELECT product_id, name, category, upc, upc AS barcode, SDK, "
        "price, quantity, company, image_url, "
        "(SELECT COUNT(*) FROM ProductTags t WHERE t.product_id = Products.product_id "
        "AND t.status = 'in_stock') AS tag_count "
        "FROM Products ORDER BY name"
    ).fetchall()


def delete_product(product_id):
    db = get_db()
    try:
        db.execute("DELETE FROM Products WHERE product_id = ?", (product_id,))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        db.rollback()
        return False


def add_product(
    name,
    price,
    quantity,
    barcode=None,
    SDK=None,
    company=None,
    category="Uncategorized",
    upc=None,
    image_url=None,
    cost_price=0,
    taxable=1,
):
    upc = upc or barcode
    db = get_db()
    db.execute(
        "INSERT INTO Products "
        "(name, category, upc, SDK, price, cost_price, taxable, quantity, company, image_url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, category, upc, SDK, price, cost_price, int(bool(taxable)), quantity, company, image_url),
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
    upc=None,
    image_url=None,
    cost_price=None,
    taxable=None,
):
    existing = get_product(product_id)
    if existing is None:
        return False

    upc = upc or barcode
    upc = existing["upc"] if upc is None else upc
    name = existing["name"] if name is None else name
    category = existing["category"] if category is None else category
    SDK = existing["SDK"] if SDK is None else SDK
    price = existing["price"] if price is None else price
    quantity = existing["quantity"] if quantity is None else quantity
    company = existing["company"] if company is None else company
    image_url = existing["image_url"] if image_url is None else image_url
    cost_price = existing["cost_price"] if cost_price is None else cost_price
    taxable = existing["taxable"] if taxable is None else int(bool(taxable))

    # Allows us to use this method to increase or decrease quantity as well
    if isinstance(quantity, str):
        if "+" in quantity:
            quantity = existing["quantity"] + int(re.sub(r"\D", "", quantity))
        elif "-" in quantity:
            quantity = existing["quantity"] - int(re.sub(r"\D", "", quantity))

    db = get_db()
    db.execute(
        "UPDATE Products SET name = ?, category = ?, upc = ?, SDK = ?, "
        "price = ?, cost_price = ?, taxable = ?, quantity = ?, company = ?, image_url = ? "
        "WHERE product_id = ?",
        (name, category, upc, SDK, price, cost_price, taxable, quantity, company, image_url, product_id),
    )
    db.commit()
    return True


def get_product_tags(product_id):
    return get_db().execute(
        "SELECT tag_id, epc, registered_at, status, sold_at, removed_at, transaction_id "
        "FROM ProductTags WHERE product_id = ? AND status = 'in_stock' "
        "ORDER BY tag_id DESC", (product_id,)
    ).fetchall()


def get_product_tag_history(product_id):
    """Return every EPC and its current state for audit/report consumers."""
    return get_db().execute(
        "SELECT tag_id, epc, registered_at, status, sold_at, removed_at, transaction_id "
        "FROM ProductTags WHERE product_id = ? ORDER BY tag_id DESC", (product_id,)
    ).fetchall()


def normalize_epc(epc):
    epc = (epc or "").strip().upper()
    if not re.fullmatch(r"(?:[0-9A-F]{2}){1,12}", epc):
        raise ValueError("EPC must contain an even number of hexadecimal characters (2–24).")
    return epc


def get_product_by_epc(epc):
    return get_db().execute(
        "SELECT p.*, p.upc AS barcode FROM Products p "
        "JOIN ProductTags t ON t.product_id = p.product_id "
        "WHERE t.epc = ? AND t.status = 'in_stock'",
        (epc.strip().upper(),),
    ).fetchone()


def sync_tagged_product_quantity(database, product_id):
    """Keep quantity aligned with active EPCs when a product has tags."""
    database.execute(
        "UPDATE Products SET quantity = ("
        "SELECT COUNT(*) FROM ProductTags "
        "WHERE product_id = ? AND status = 'in_stock') "
        "WHERE product_id = ? AND EXISTS ("
        "SELECT 1 FROM ProductTags WHERE product_id = ?)",
        (product_id, product_id, product_id),
    )


def record_tag_event(database, tag_id, status, transaction_id=None, note=None):
    database.execute(
        "INSERT INTO ProductTagEvents (tag_id, status, transaction_id, note) "
        "VALUES (?, ?, ?, ?)", (tag_id, status, transaction_id, note),
    )


def delete_product_tag(product_id, tag_id):
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT (SELECT quantity FROM Products WHERE product_id = ?) AS quantity, "
            "COUNT(*) AS tags FROM ProductTags "
            "WHERE product_id = ? AND status = 'in_stock'",
            (product_id, product_id),
        ).fetchone()
        result = database.execute(
            "UPDATE ProductTags SET status = 'removed', removed_at = CURRENT_TIMESTAMP, "
            "sold_at = NULL, transaction_id = NULL "
            "WHERE product_id = ? AND tag_id = ? AND status = 'in_stock'",
            (product_id, tag_id),
        )
        if result.rowcount:
            record_tag_event(database, tag_id, "removed", note="Removed from inventory")
            sync_tagged_product_quantity(database, product_id)
        database.commit()
    except Exception:
        database.rollback()
        raise
    return result.rowcount > 0


def receive_scanned_tag(product_id, epc, supplier=None):
    epc = normalize_epc(epc)
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        product = database.execute(
            "SELECT quantity FROM Products WHERE product_id = ?", (product_id,)
        ).fetchone()
        if product is None:
            database.rollback()
            return {"status": "missing_product", "epc": epc}
        existing = database.execute(
            "SELECT product_id, status FROM ProductTags WHERE epc = ?", (epc,)
        ).fetchone()
        if existing is not None:
            database.rollback()
            status = "already_registered" if existing["product_id"] == product_id else "conflict"
            return {"status": status, "epc": epc}
        database.execute(
            "INSERT INTO ProductTags (product_id, epc) VALUES (?, ?)",
            (product_id, epc),
        )
        tag_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]
        record_tag_event(database, tag_id, "in_stock", note="Received into inventory")
        database.execute(
            "INSERT INTO ProductReceptions "
            "(product_id, quantity_received, supplier) VALUES (?, 1, ?)",
            (product_id, supplier),
        )
        database.execute(
            "UPDATE Products SET quantity = quantity + 1 WHERE product_id = ?",
            (product_id,),
        )
        database.commit()
    except Exception:
        database.rollback()
        raise
    return {"status": "received", "epc": epc, "quantity": product["quantity"] + 1}


def receive_scanned_tags(product_id, epcs, supplier=None):
    epcs = list(dict.fromkeys(normalize_epc(epc) for epc in epcs))
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        product = database.execute(
            "SELECT quantity FROM Products WHERE product_id = ?", (product_id,)
        ).fetchone()
        if product is None:
            database.rollback()
            return {"status": "missing_product", "received": []}
        placeholders = ",".join("?" for _ in epcs)
        existing = {
            row["epc"]: row["product_id"]
            for row in database.execute(
                f"SELECT epc, product_id FROM ProductTags WHERE epc IN ({placeholders})",
                epcs,
            )
        }
        received = [epc for epc in epcs if epc not in existing]
        already_registered = [
            epc for epc in epcs if existing.get(epc) == product_id
        ]
        conflicts = [
            epc for epc in epcs
            if epc in existing and existing[epc] != product_id
        ]
        reception = None
        if received:
            database.executemany(
                "INSERT INTO ProductTags (product_id, epc) VALUES (?, ?)",
                [(product_id, epc) for epc in received],
            )
            new_tags = database.execute(
                f"SELECT tag_id, epc FROM ProductTags WHERE product_id = ? "
                f"AND epc IN ({','.join('?' for _ in received)})",
                (product_id, *received),
            ).fetchall()
            for tag in new_tags:
                record_tag_event(database, tag["tag_id"], "in_stock", note="Received into inventory")
            reception_id = database.execute(
                "INSERT INTO ProductReceptions "
                "(product_id, quantity_received, supplier) VALUES (?, ?, ?)",
                (product_id, len(received), supplier),
            ).lastrowid
            database.executemany(
                "INSERT INTO ReceivedTags (tag_id, reception_id) "
                "SELECT tag_id, ? FROM ProductTags WHERE product_id = ? AND epc = ?",
                [(reception_id, product_id, epc) for epc in received],
            )
            database.execute(
                "UPDATE Products SET quantity = quantity + ? WHERE product_id = ?",
                (len(received), product_id),
            )
            reception = dict(database.execute(
                "SELECT r.reception_id, p.name AS product_name, r.quantity_received, "
                "r.supplier, r.received_at FROM ProductReceptions r "
                "JOIN Products p USING (product_id) WHERE r.reception_id = ?",
                (reception_id,),
            ).fetchone())
        tag_count = database.execute(
            "SELECT COUNT(*) FROM ProductTags "
            "WHERE product_id = ? AND status = 'in_stock'", (product_id,)
        ).fetchone()[0]
        database.commit()
    except Exception:
        database.rollback()
        raise
    return {
        "status": "received" if received else "no_new_tags",
        "received": received,
        "already_registered": already_registered,
        "conflicts": conflicts,
        "count": len(received),
        "quantity": product["quantity"] + len(received),
        "tag_count": tag_count,
        "reception": reception,
    }


def undo_received_tag(reception_id, epc):
    database = get_db()
    with database:
        database.execute("BEGIN IMMEDIATE")
        tag = database.execute(
            """
            SELECT t.tag_id, t.product_id, t.status, p.quantity, r.quantity_received
            FROM ReceivedTags rt
            JOIN ProductTags t USING (tag_id)
            JOIN ProductReceptions r USING (reception_id)
            JOIN Products p ON p.product_id = t.product_id
            WHERE rt.reception_id = ? AND t.epc = ?
            """, (reception_id, epc),
        ).fetchone()
        if tag is None or tag["status"] != "in_stock":
            return None

        product_id = tag["product_id"]
        database.execute(
            "UPDATE ProductTags SET status = 'removed', removed_at = CURRENT_TIMESTAMP "
            "WHERE tag_id = ?", (tag["tag_id"],)
        )
        record_tag_event(database, tag["tag_id"], "removed", note="Undid received tag")
        quantity_received = tag["quantity_received"] - 1
        if quantity_received:
            database.execute(
                "UPDATE ProductReceptions SET quantity_received = ? WHERE reception_id = ?",
                (quantity_received, reception_id),
            )
        else:
            database.execute(
                "DELETE FROM ProductReceptions WHERE reception_id = ?", (reception_id,)
            )
        sync_tagged_product_quantity(database, product_id)
        tag_count = database.execute(
            "SELECT COUNT(*) FROM ProductTags WHERE product_id = ? AND status = 'in_stock'",
            (product_id,),
        ).fetchone()[0]
        return {
            "product_id": product_id,
            "quantity": tag_count,
            "tag_count": tag_count,
            "quantity_received": quantity_received,
        }


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


def get_product_receptions(limit=20):
    db = get_db()
    return db.execute(
        "SELECT r.reception_id, p.name AS product_name, r.quantity_received, "
        "r.received_at, r.supplier "
        "FROM ProductReceptions r "
        "JOIN Products p ON p.product_id = r.product_id "
        "ORDER BY r.reception_id DESC LIMIT ?",
        (limit,),
    ).fetchall()



def update_customer_membership(customer_id, membership_number):
    membership_number = (membership_number or "").strip().upper()
    db = get_db()
    result = db.execute(
        "UPDATE Customers SET membership_number = ? WHERE customer_id = ?",
        (membership_number, customer_id),
    )
    db.commit()
    return result.rowcount > 0


def get_customer(customer_id):
    if customer_id is None:
        return None
    return get_db().execute(
        "SELECT customer_id, first_name, last_name, address, phone, email, "
        "membership_number, total_points FROM Customers WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()


def get_customer_by_membership_number(membership_number):
    if not membership_number:
        return None
    return get_db().execute(
        "SELECT customer_id, first_name, last_name, email, membership_number, total_points "
        "FROM Customers WHERE UPPER(membership_number) = ?",
        (membership_number.strip().upper(),),
    ).fetchone()


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


def get_fridge_thresholds():
    return get_db().execute(
        "SELECT name, temp_threshold, humid_threshold FROM Sensors "
        "WHERE name IN ('Frig1', 'Frig2', 'Fridge 3') ORDER BY sensor_id"
    ).fetchall()


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


def get_sensor_readings_for_period(start_timestamp, end_timestamp):
    """Return readings in a caller-defined UTC-naive timestamp period.

    A LEFT JOIN keeps sensors with no readings available for an explicit empty
    state. The application supplies bounds for the local calendar day and
    validates returned values before rendering them.
    """
    return get_db().execute(
        """
        SELECT s.sensor_id, s.name, s.location,
               r.reading_id, r.timestamp, r.temperature, r.humidity
        FROM Sensors s
        LEFT JOIN SensorReadings r
          ON r.sensor_id = s.sensor_id
         AND r.timestamp >= ?
         AND r.timestamp < ?
        ORDER BY s.name COLLATE NOCASE, r.timestamp, r.reading_id
        """,
        (start_timestamp, end_timestamp),
    ).fetchall()


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


def migrate_stock_to_tags(database):
    if database.execute(
        "SELECT 1 FROM AppSettings WHERE name = 'stock_tags_reconciled'"
    ).fetchone():
        return
    database.execute(
        "UPDATE Products SET quantity = ("
        "SELECT COUNT(*) FROM ProductTags t "
        "WHERE t.product_id = Products.product_id AND t.status = 'in_stock') "
        "WHERE EXISTS (SELECT 1 FROM ProductTags t2 WHERE t2.product_id = Products.product_id)"
    )
    database.execute(
        "INSERT INTO AppSettings (name, value) VALUES ('stock_tags_reconciled', '1')"
    )


def migrate_product_images(database):
    columns = {row["name"] for row in database.execute("PRAGMA table_info(Products)")}
    if "image_url" in columns:
        return
    database.execute("ALTER TABLE Products ADD COLUMN image_url TEXT")
    defaults = {
        "Pepsi": "/static/images/products/pepsi.jpg",
        "Water Bottle": "/static/images/products/water-bottle.jpg",
    }
    for name, image_url in defaults.items():
        database.execute(
            "UPDATE Products SET image_url = ? WHERE name = ?", (image_url, name)
        )


def migrate_financial_fields(database):
    """Add historical cost and tax snapshots without changing old receipts."""
    product_columns = {row["name"] for row in database.execute("PRAGMA table_info(Products)")}
    if "cost_price" not in product_columns:
        database.execute("ALTER TABLE Products ADD COLUMN cost_price REAL NOT NULL DEFAULT 0 CHECK (cost_price >= 0)")
    if "taxable" not in product_columns:
        database.execute("ALTER TABLE Products ADD COLUMN taxable INTEGER NOT NULL DEFAULT 1 CHECK (taxable IN (0, 1))")

    transaction_columns = {row["name"] for row in database.execute("PRAGMA table_info(Transactions)")}
    additions = (
        ("subtotal_amount", "REAL NOT NULL DEFAULT 0 CHECK (subtotal_amount >= 0)"),
        ("gst_amount", "REAL NOT NULL DEFAULT 0 CHECK (gst_amount >= 0)"),
        ("qst_amount", "REAL NOT NULL DEFAULT 0 CHECK (qst_amount >= 0)"),
        ("tax_amount", "REAL NOT NULL DEFAULT 0 CHECK (tax_amount >= 0)"),
        ("cost_amount", "REAL NOT NULL DEFAULT 0 CHECK (cost_amount >= 0)"),
        ("profit_amount", "REAL NOT NULL DEFAULT 0"),
        ("gst_rate", "REAL NOT NULL DEFAULT 0.05 CHECK (gst_rate >= 0)"),
        ("qst_rate", "REAL NOT NULL DEFAULT 0.09975 CHECK (qst_rate >= 0)"),
    )
    for name, definition in additions:
        if name not in transaction_columns:
            database.execute(f"ALTER TABLE Transactions ADD COLUMN {name} {definition}")
    database.execute(
        "UPDATE Transactions SET subtotal_amount = total_amount "
        "WHERE subtotal_amount = 0 AND total_amount > 0"
    )
    database.execute(
        "UPDATE Transactions SET profit_amount = subtotal_amount - cost_amount "
        "WHERE profit_amount = 0 AND subtotal_amount > 0"
    )

    item_columns = {row["name"] for row in database.execute("PRAGMA table_info(TransactionItems)")}
    for name, definition in (
        ("cost_at_sale", "REAL NOT NULL DEFAULT 0 CHECK (cost_at_sale >= 0)"),
        ("taxable_at_sale", "INTEGER NOT NULL DEFAULT 1 CHECK (taxable_at_sale IN (0, 1))"),
    ):
        if name not in item_columns:
            database.execute(f"ALTER TABLE TransactionItems ADD COLUMN {name} {definition}")


def migrate_product_tag_lifecycle(database):
    """Preserve EPC rows and add an append-only lifecycle event trail."""
    columns = {row["name"] for row in database.execute("PRAGMA table_info(ProductTags)")}
    if "status" not in columns:
        database.execute(
            "ALTER TABLE ProductTags ADD COLUMN status TEXT NOT NULL DEFAULT 'in_stock' "
            "CHECK (status IN ('in_stock', 'sold', 'removed'))"
        )
    if "sold_at" not in columns:
        database.execute("ALTER TABLE ProductTags ADD COLUMN sold_at TEXT")
    if "removed_at" not in columns:
        database.execute("ALTER TABLE ProductTags ADD COLUMN removed_at TEXT")
    if "transaction_id" not in columns:
        database.execute("ALTER TABLE ProductTags ADD COLUMN transaction_id INTEGER")
    database.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_tags_status "
        "ON ProductTags(product_id, status)"
    )
    database.execute("""
        CREATE TABLE IF NOT EXISTS ProductTagEvents (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('in_stock', 'sold', 'removed')),
            event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            transaction_id INTEGER,
            note TEXT,
            FOREIGN KEY (tag_id) REFERENCES ProductTags(tag_id) ON DELETE CASCADE
        )
    """)
    database.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_tag_events_tag_id "
        "ON ProductTagEvents(tag_id, event_at)"
    )
    database.execute(
        "INSERT INTO ProductTagEvents (tag_id, status, event_at, transaction_id, note) "
        "SELECT tag_id, status, COALESCE(removed_at, sold_at, registered_at), transaction_id, "
        "'Migrated current EPC state' FROM ProductTags t "
        "WHERE NOT EXISTS (SELECT 1 FROM ProductTagEvents e WHERE e.tag_id = t.tag_id)"
    )
    for row in database.execute("SELECT DISTINCT product_id FROM ProductTags"):
        sync_tagged_product_quantity(database, row["product_id"])


def migrate_product_tags(database):
    """Move legacy product EPCs without changing IDs or dependent records."""
    columns = {row["name"] for row in database.execute("PRAGMA table_info(Products)")}
    if "epc" not in columns:
        return
    # SQLite requires rebuilding a table to remove a UNIQUE/NOT NULL column.
    # Disable FK actions outside the transaction to preserve dependent records.
    database.commit()
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        database.execute("BEGIN IMMEDIATE")
        sequence = database.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'Products'"
        ).fetchone()
        database.execute(
            "INSERT INTO ProductTags (product_id, epc) "
            "SELECT product_id, UPPER(TRIM(epc)) FROM Products "
            "WHERE epc IS NOT NULL AND TRIM(epc) <> ''"
        )
        database.execute("""
            CREATE TABLE Products_new (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                upc TEXT NOT NULL UNIQUE CHECK (length(upc) <= 13),
                SDK TEXT UNIQUE,
                price REAL NOT NULL CHECK (price >= 0),
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                company TEXT NOT NULL
            )
        """)
        database.execute(
            "INSERT INTO Products_new (product_id, name, category, upc, SDK, price, quantity, company) "
            "SELECT product_id, name, category, upc, SDK, price, quantity, company FROM Products"
        )
        database.execute("DROP TABLE Products")
        database.execute("ALTER TABLE Products_new RENAME TO Products")
        if sequence:
            database.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'Products'", (sequence["seq"],))
        if database.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError("Product tag migration failed its foreign key check.")
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def migrate_optional_membership(database):
    if not any(row["name"] == "membership_number" and row["notnull"]
               for row in database.execute("PRAGMA table_info(Customers)")):
        return

    database.execute("PRAGMA foreign_keys = OFF")
    try:
        with database:
            database.execute("BEGIN IMMEDIATE")
            if not any(row["name"] == "membership_number" and row["notnull"]
                       for row in database.execute("PRAGMA table_info(Customers)")):
                return
            sequence = database.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'Customers'"
            ).fetchone()
            database.execute("""
                CREATE TABLE Customers_new (
                    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    address TEXT NOT NULL,
                    phone TEXT UNIQUE,
                    email TEXT UNIQUE,
                    membership_number TEXT UNIQUE,
                    total_points INTEGER NOT NULL DEFAULT 0 CHECK (total_points >= 0)
                )
            """)
            database.execute("""
                INSERT INTO Customers_new
                    (customer_id, first_name, last_name, address, phone, email, membership_number, total_points)
                SELECT customer_id, first_name, last_name, address, phone, email, membership_number, total_points
                FROM Customers
            """)
            database.execute("DROP TABLE Customers")
            database.execute("ALTER TABLE Customers_new RENAME TO Customers")
            if sequence:
                database.execute("DELETE FROM sqlite_sequence WHERE name = 'Customers'")
                database.execute(
                    "INSERT INTO sqlite_sequence (name, seq) VALUES ('Customers', ?)",
                    (sequence["seq"],),
                )
            if database.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("Customer migration failed its foreign key check.")
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def migrate_phone_numbers(database):
    """Canonicalize legacy phones and remove values that are not Quebec-valid."""
    rows = database.execute(
        "SELECT customer_id, phone FROM Customers WHERE phone IS NOT NULL"
    ).fetchall()
    for row in rows:
        normalized = normalize_quebec_phone(row["phone"])
        if normalized is None:
            # Invalid legacy values cannot remain in a strictly validated field.
            database.execute(
                "UPDATE Customers SET phone = NULL WHERE customer_id = ?",
                (row["customer_id"],),
            )
            continue
        if normalized != row["phone"]:
            conflict = database.execute(
                "SELECT customer_id FROM Customers WHERE phone = ? AND customer_id <> ?",
                (normalized, row["customer_id"]),
            ).fetchone()
            if conflict:
                database.execute(
                    "UPDATE Customers SET phone = NULL WHERE customer_id = ?",
                    (row["customer_id"],),
                )
            else:
                database.execute(
                    "UPDATE Customers SET phone = ? WHERE customer_id = ?",
                    (normalized, row["customer_id"]),
                )


def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource("db/schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        migrate_optional_membership(db)
        migrate_phone_numbers(db)
        migrate_product_tags(db)
        migrate_product_images(db)
        migrate_financial_fields(db)
        migrate_product_tag_lifecycle(db)
        migrate_stock_to_tags(db)
        migrate_sensor_thresholds(db)
        db.executemany(
            "INSERT INTO Sensors (name, location, temp_threshold, humid_threshold) "
            "SELECT ?, ?, 25.0, 70.0 WHERE NOT EXISTS (SELECT 1 FROM Sensors WHERE name = ?)",
            [(name, name, name) for name in ("Frig1", "Frig2", "Fridge 3")],
        )
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
