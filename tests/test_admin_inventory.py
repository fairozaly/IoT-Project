import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

import db as db_module
from app import create_app


class AdminInventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smart-store-admin-test-")
        self.database_path = str(Path(self.temp_dir.name) / "store.sqlite3")
        self.app = create_app({
            "TESTING": True,
            "START_SERVICES": False,
            "DATABASE": self.database_path,
            "SECRET_KEY": "admin-test-secret",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db = db_module.get_db()
            db_module.add_product(
                "Test Coffee", 4.50, 7, barcode="0000000000002",
                company="Test Supplier", category="Drinks",
            )
            customer = db.execute(
                "INSERT INTO Customers (first_name, last_name, address, email) "
                "VALUES (?, ?, ?, ?)",
                ("Test", "Customer", "1 Main Street", "customer@example.com"),
            )
            self.customer_id = customer.lastrowid
            customer_user = db.execute(
                "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, ?)",
                ("customer@example.com", generate_password_hash("password123", method="pbkdf2:sha256"), self.customer_id),
            )
            self.customer_user_id = customer_user.lastrowid
            admin = db.execute(
                "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, NULL)",
                ("admin@example.com", generate_password_hash("password123", method="pbkdf2:sha256")),
            )
            self.admin_user_id = admin.lastrowid
            db.commit()

    def tearDown(self):
        with self.app.app_context():
            db_module.close_connection(None)
        self.temp_dir.cleanup()

    def sign_in_session(self, user_id, email, customer_id=None):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id
            session["email"] = email
            session["customer_id"] = customer_id

    def csrf_headers(self):
        return {"X-CSRF-Token": self.client.get("/api/csrf-token").get_json()["csrf_token"]}

    def test_inventory_endpoint_is_staff_only_and_reports_current_status(self):
        self.sign_in_session(self.admin_user_id, "admin@example.com")
        response = self.client.get("/api/inventory")
        self.assertEqual(response.status_code, 200)
        item = response.get_json()["items"][0]
        self.assertEqual(item["quantity"], 7)
        self.assertEqual(item["status"], "in_stock")
        self.assertEqual(item["tag_count"], 0)

        self.sign_in_session(self.customer_user_id, "customer@example.com", self.customer_id)
        self.assertEqual(self.client.get("/api/inventory").status_code, 403)

    def test_admin_dashboard_shows_sales_profit_state_and_fridge_summary(self):
        self.sign_in_session(self.admin_user_id, "admin@example.com")
        with self.app.app_context():
            db = db_module.get_db()
            transaction = db.execute(
                "INSERT INTO Transactions (total_amount, transaction_date, status) "
                "VALUES (?, ?, 'completed')",
                (4.50, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")),
            )
            db.execute(
                "INSERT INTO TransactionItems (transaction_id, product_id, quantity, price_at_sale) "
                "VALUES (?, 1, 1, 4.50)", (transaction.lastrowid,),
            )
            db.commit()

        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Today's sales", response.data)
        self.assertIn(b"$4.50", response.data)
        self.assertIn(b"Today's profit", response.data)
        self.assertIn(b"$4.50", response.data)
        self.assertIn(b"Current fridge summary", response.data)

    def test_role_changes_preserve_customer_profile_and_block_self_changes(self):
        self.sign_in_session(self.admin_user_id, "admin@example.com")
        promote = self.client.post(
            f"/admin/users/{self.customer_user_id}/role",
            data={"action": "promote"}, headers=self.csrf_headers(),
        )
        self.assertEqual(promote.status_code, 302)
        with self.app.app_context():
            db = db_module.get_db()
            self.assertIsNone(db.execute(
                "SELECT customer_id FROM Users WHERE user_id = ?", (self.customer_user_id,)
            ).fetchone()[0])
            self.assertIsNotNone(db.execute(
                "SELECT customer_id FROM Customers WHERE customer_id = ?", (self.customer_id,)
            ).fetchone())

        demote = self.client.post(
            f"/admin/users/{self.customer_user_id}/role",
            data={"action": "demote"}, headers=self.csrf_headers(),
        )
        self.assertEqual(demote.status_code, 302)
        with self.app.app_context():
            db = db_module.get_db()
            self.assertEqual(db.execute(
                "SELECT customer_id FROM Users WHERE user_id = ?", (self.customer_user_id,)
            ).fetchone()[0], self.customer_id)

        self_change = self.client.post(
            f"/admin/users/{self.admin_user_id}/role",
            data={"action": "demote"}, headers=self.csrf_headers(), follow_redirects=True,
        )
        self.assertEqual(self_change.status_code, 200)
        self.assertIn(b"cannot change your own administrator access", self_change.data)

    def test_customer_email_change_validates_and_updates_linked_login(self):
        self.sign_in_session(self.admin_user_id, "admin@example.com")
        invalid = self.client.post(
            f"/customers/{self.customer_id}/email",
            data={"email": "not-an-email"}, headers=self.csrf_headers(),
        )
        self.assertEqual(invalid.status_code, 302)

        changed = self.client.post(
            f"/customers/{self.customer_id}/email",
            data={"email": "renamed@example.com"}, headers=self.csrf_headers(),
        )
        self.assertEqual(changed.status_code, 302)
        with self.app.app_context():
            db = db_module.get_db()
            self.assertEqual(db.execute(
                "SELECT email FROM Customers WHERE customer_id = ?", (self.customer_id,)
            ).fetchone()[0], "renamed@example.com")
            self.assertEqual(db.execute(
                "SELECT email FROM Users WHERE user_id = ?", (self.customer_user_id,)
            ).fetchone()[0], "renamed@example.com")


if __name__ == "__main__":
    unittest.main()
