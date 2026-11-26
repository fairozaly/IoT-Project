import sqlite3
import tempfile
import unittest
from pathlib import Path

import db as db_module
from app import create_app


class InventoryAndReportTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smart-store-report-test-")
        self.database_path = str(Path(self.temp_dir.name) / "store.sqlite3")
        self.app = create_app({
            "TESTING": True,
            "START_SERVICES": False,
            "DATABASE": self.database_path,
            "SECRET_KEY": "report-test-secret",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db_module.close_connection(None)
        self.temp_dir.cleanup()

    def csrf_headers(self):
        token = self.client.get("/api/csrf-token").get_json()["csrf_token"]
        return {"X-CSRF-Token": token}

    def test_checkout_preserves_sold_epc_and_records_financials(self):
        with self.app.app_context():
            db = db_module.get_db()
            db_module.add_product(
                "Tagged Coffee", 10.00, 0, barcode="5555555555555",
                company="Test Supplier", category="Drinks", cost_price=4.00,
            )
            product = db_module.get_product_by_barcode("5555555555555")
            result = db_module.receive_scanned_tag(product["product_id"], "ABCDEF123456")
            self.assertEqual(result["status"], "received")

        added = self.client.post(
            "/api/cart/items",
            json={"product_id": product["product_id"], "quantity": 1, "epc": "ABCDEF123456"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(added.status_code, 200)
        complete = self.client.post("/checkout/complete", headers=self.csrf_headers())
        self.assertEqual(complete.status_code, 302)

        with self.app.app_context():
            db = db_module.get_db()
            tag = db.execute(
                "SELECT status, transaction_id FROM ProductTags WHERE epc = ?",
                ("ABCDEF123456",),
            ).fetchone()
            self.assertEqual(tag["status"], "sold")
            self.assertIsNotNone(tag["transaction_id"])
            self.assertEqual(
                db.execute(
                    "SELECT quantity FROM Products WHERE product_id = ?",
                    (product["product_id"],),
                ).fetchone()[0],
                0,
            )
            transaction = db.execute(
                "SELECT subtotal_amount, gst_amount, qst_amount, total_amount, "
                "cost_amount, profit_amount FROM Transactions WHERE transaction_id = ?",
                (tag["transaction_id"],),
            ).fetchone()
            self.assertEqual(tuple(round(value, 2) for value in transaction),
                             (10.00, 0.50, 1.00, 11.50, 4.00, 6.00))
            events = db.execute(
                "SELECT status FROM ProductTagEvents WHERE tag_id = "
                "(SELECT tag_id FROM ProductTags WHERE epc = ?) ORDER BY event_id",
                ("ABCDEF123456",),
            ).fetchall()
            self.assertEqual([event["status"] for event in events], ["in_stock", "sold"])

    def test_removed_epc_remains_traceable_and_is_excluded_from_stock(self):
        with self.app.app_context():
            db_module.add_product(
                "Tagged Soap", 5.00, 0, barcode="5555555555556",
                company="Test Supplier", category="Care",
            )
            product = db_module.get_product_by_barcode("5555555555556")
            db_module.receive_scanned_tag(product["product_id"], "ABCDEF123458")
            tag = db_module.get_db().execute(
                "SELECT tag_id FROM ProductTags WHERE epc = ?", ("ABCDEF123458",)
            ).fetchone()
            self.assertTrue(db_module.delete_product_tag(product["product_id"], tag["tag_id"]))
            current = db_module.get_db().execute(
                "SELECT status FROM ProductTags WHERE tag_id = ?", (tag["tag_id"],)
            ).fetchone()
            self.assertEqual(current["status"], "removed")
            self.assertEqual(db_module.get_product(product["product_id"])["quantity"], 0)

    def test_existing_schema_migrates_without_losing_epcs(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.sqlite3")
        legacy = sqlite3.connect(legacy_path)
        legacy.executescript("""
            CREATE TABLE Products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, category TEXT NOT NULL, upc TEXT NOT NULL UNIQUE,
                SDK TEXT UNIQUE, price REAL NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
                company TEXT NOT NULL
            );
            CREATE TABLE ProductTags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL, epc TEXT NOT NULL UNIQUE,
                registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO Products (name, category, upc, price, quantity, company)
            VALUES ('Legacy Item', 'Test', '5555555555557', 2.00, 1, 'Legacy Supplier');
            INSERT INTO ProductTags (product_id, epc) VALUES (1, 'ABCDEF123459');
            CREATE TABLE Transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                total_amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'completed'
            );
            CREATE TABLE TransactionItems (
                transaction_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL, price_at_sale REAL NOT NULL
            );
            CREATE TABLE AppSettings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        legacy.commit()
        legacy.close()

        migration_app = create_app({
            "TESTING": True,
            "START_SERVICES": False,
            "DATABASE": legacy_path,
            "SECRET_KEY": "migration-test-secret",
        })
        with migration_app.app_context():
            db = db_module.get_db()
            tag = db.execute(
                "SELECT epc, status FROM ProductTags WHERE epc = 'ABCDEF123459'"
            ).fetchone()
            self.assertEqual(tuple(tag), ("ABCDEF123459", "in_stock"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ProductTagEvents").fetchone()[0], 1)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(Transactions)")}
            self.assertTrue({"subtotal_amount", "gst_amount", "qst_amount", "profit_amount"} <= columns)
        with migration_app.app_context():
            db_module.close_connection(None)

    def test_sales_report_exposes_tax_cost_profit_and_csv_columns(self):
        with self.app.app_context():
            db = db_module.get_db()
            db.execute(
                "INSERT INTO Transactions (transaction_date, total_amount, subtotal_amount, gst_amount, "
                "qst_amount, tax_amount, cost_amount, profit_amount) "
                "VALUES (CURRENT_TIMESTAMP, 11.50, 10, .50, 1, 1.50, 4, 6)"
            )
            transaction_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db_module.add_product("Report Item", 10, 0, barcode="5555555555558", company="Reports")
            product = db_module.get_product_by_barcode("5555555555558")
            db.execute(
                "INSERT INTO TransactionItems (transaction_id, product_id, quantity, price_at_sale, cost_at_sale) "
                "VALUES (?, ?, 1, 10, 4)", (transaction_id, product["product_id"])
            )
            db.commit()
            staff = db.execute(
                "INSERT INTO Users (email, password_hash, customer_id) VALUES ('reports@example.com', 'x', NULL)"
            ).lastrowid
            db.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = staff
            session["email"] = "reports@example.com"
        response = self.client.get("/reports?report=sales")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GST", response.data)
        self.assertIn(b"Profit", response.data)
        csv = self.client.get("/reports?report=sales&format=csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn(b"Cost (CAD)", csv.data)
        self.assertIn(b"Profit (CAD)", csv.data)


if __name__ == "__main__":
    unittest.main()
