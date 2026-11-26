import platform
import sqlite3
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import auth as auth_module
import db as db_module
import gpio_backend
from app import create_app
from validation_security import normalize_quebec_phone, valid_phone


class StoreSmokeTest(unittest.TestCase):
    """Small, dependency-free smoke coverage for the web application."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smart-store-test-")
        self.database_path = str(Path(self.temp_dir.name) / "store.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "START_SERVICES": False,
                "DATABASE": self.database_path,
                "SECRET_KEY": "smoke-test-secret",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db_module.close_connection(None)
        self.temp_dir.cleanup()

    def add_product(self, quantity=3):
        with self.app.app_context():
            db_module.add_product(
                "Test Water",
                1.25,
                quantity,
                barcode="0000000000001",
                company="Test Supplier",
                category="Drinks",
            )
            return db_module.get_product_by_barcode("0000000000001")

    def add_customer(self, email="customer@example.com", password="password123"):
        with self.app.app_context():
            database = db_module.get_db()
            customer = database.execute(
                "INSERT INTO Customers "
                "(first_name, last_name, address, phone, email, membership_number) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Test", "Customer", "1 Main Street", "555-0100", email, "MEMBER-1"),
            )
            customer_id = customer.lastrowid
            user = database.execute(
                "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, ?)",
                (
                    email,
                    generate_password_hash(password, method="pbkdf2:sha256"),
                    customer_id,
                ),
            )
            database.commit()
            return user.lastrowid, customer_id

    def add_staff(self, email="staff@example.com", password="password123"):
        with self.app.app_context():
            database = db_module.get_db()
            user = database.execute(
                "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, NULL)",
                (email, generate_password_hash(password, method="pbkdf2:sha256")),
            )
            database.commit()
            return user.lastrowid

    def sign_in_session(self, user_id, email, customer_id=None):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id
            session["email"] = email
            session["customer_id"] = customer_id

    def csrf_headers(self):
        """Get the session token through the public client contract."""
        response = self.client.get("/api/csrf-token")
        self.assertEqual(response.status_code, 200)
        token = response.get_json()["csrf_token"]
        self.assertIsInstance(token, str)
        self.assertGreaterEqual(len(token), 32)
        return {"X-CSRF-Token": token}

    def test_database_path_is_configurable_and_isolated(self):
        self.assertEqual(self.app.config["DATABASE"], self.database_path)
        self.assertNotEqual(Path(self.database_path).resolve(), Path(db_module.DATABASE).resolve())
        self.add_product()
        with self.app.app_context():
            self.assertEqual(len(db_module.get_products()), 1)
        self.assertFalse(Path(db_module.DATABASE).resolve() == Path(self.database_path).resolve())

    def test_services_are_disabled_during_app_creation(self):
        self.assertFalse(self.app.config["START_SERVICES"])
        self.assertNotIn("mqtt", self.app.extensions)

    def test_sensor_history_query_limits_timestamp_period(self):
        with self.app.app_context():
            sensor_id = db_module.get_or_create_sensor("History Sensor", "Test cooler")
            database = db_module.get_db()
            database.executemany(
                "INSERT INTO SensorReadings (sensor_id, timestamp, temperature, humidity) "
                "VALUES (?, ?, ?, ?)",
                [
                    (sensor_id, "2026-11-26 08:00:00", 4.5, 45.0),
                    (sensor_id, "2026-11-25 08:00:00", 99.9, 45.0),
                ],
            )
            database.commit()

            rows = db_module.get_sensor_readings_for_period(
                "2026-11-26 00:00:00", "2026-11-27 00:00:00"
            )

        readings = [row for row in rows if row["reading_id"] is not None]
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0]["temperature"], 4.5)

    def test_storage_history_renders_today_and_omits_bad_readings(self):
        user_id = self.add_staff(email="history-staff@example.com")
        self.sign_in_session(user_id, "history-staff@example.com")
        local_now = datetime.now().astimezone()
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        utc_now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
        malformed_timestamp = utc_start.strftime("%Y-%m-%d %H:%M:%S") + " invalid"

        with self.app.app_context():
            sensor_id = db_module.get_or_create_sensor("History Fridge", "Back room")
            database = db_module.get_db()
            database.executemany(
                "INSERT INTO SensorReadings (sensor_id, timestamp, temperature, humidity) "
                "VALUES (?, ?, ?, ?)",
                [
                    (sensor_id, utc_now.strftime("%Y-%m-%d %H:%M:%S"), 4.5, 45.0),
                    (sensor_id, malformed_timestamp, "not-a-number", 45.0),
                    (sensor_id, (utc_now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), 99.9, 45.0),
                ],
            )
            database.commit()

        response = self.client.get("/storage-history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Today's recorded temperatures", response.data)
        self.assertIn(b"History Fridge", response.data)
        self.assertIn(b"4.5", response.data)
        self.assertIn(b"malformed reading omitted", response.data)
        self.assertNotIn(b"99.9", response.data)

    def test_public_redirects_and_checkout_render(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root.headers["Location"], "/checkout")

        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn(b"Self-checkout", checkout.data)

        signup = self.client.get("/signup")
        self.assertEqual(signup.status_code, 302)
        self.assertEqual(signup.headers["Location"], "/signin")

    def test_legacy_signup_never_creates_staff_account(self):
        before = self.count_users()
        for method in ("get", "post"):
            kwargs = {"data": {"email": "new-staff@example.com", "password": "password123"}}
            if method == "post":
                kwargs["headers"] = self.csrf_headers()
            response = getattr(self.client, method)("/signup", **kwargs)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/signin")
        self.assertEqual(self.count_users(), before)

    def test_signin_rejects_bad_credentials_and_accepts_staff(self):
        self.add_staff()
        invalid = self.client.post(
            "/signin",
            data={"email": "staff@example.com", "password": "wrong"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn(b"Email or password is incorrect", invalid.data)

        valid = self.client.post(
            "/signin",
            data={"email": "staff@example.com", "password": "password123"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(valid.headers["Location"], "/fridges")

    def test_customer_signup_validates_and_can_create_account(self):
        invalid = self.client.post(
            "/customer/signup",
            data={
                "first_name": "",
                "last_name": "Customer",
                "address": "1 Main Street",
                "email": "customer@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
            headers=self.csrf_headers(),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn(b"Enter your first name", invalid.data)
        self.assertEqual(self.count_users(), 0)

        form = {
            "first_name": "Test",
            "last_name": "Customer",
            "address": "1 Main Street",
            "phone": "514-555-1234",
            "email": "customer@example.com",
            "password": "password123",
            "confirm_password": "password123",
        }
        # Werkzeug's default hash is scrypt on some versions, while the
        # supported test runtime may not expose hashlib.scrypt. Keep this
        # test about the route contract by injecting a portable hash method.
        with patch.object(
            auth_module,
            "generate_password_hash",
            side_effect=lambda password, **_: generate_password_hash(
                password, method="pbkdf2:sha256"
            ),
        ):
            created = self.client.post(
                "/customer/signup", data=form, headers=self.csrf_headers()
            )
        self.assertEqual(created.status_code, 302)
        self.assertEqual(created.headers["Location"], "/account")
        self.assertEqual(self.count_users(), 1)

    def test_guest_cart_lifecycle_and_malformed_inputs(self):
        product = self.add_product()
        empty = self.client.get("/api/cart")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.get_json()["items"], [])

        no_json = self.client.post("/api/cart/items")
        self.assertEqual(no_json.status_code, 403)
        self.assertEqual(no_json.get_json()["code"], "csrf_failed")

        no_json = self.client.post("/api/cart/items", headers=self.csrf_headers())
        self.assertEqual(no_json.status_code, 400)
        self.assertIn("JSON object", no_json.get_json()["error"])

        invalid_quantity = self.client.post(
            "/api/cart/items",
            json={"product_id": product["product_id"], "quantity": -1},
            headers=self.csrf_headers(),
        )
        self.assertEqual(invalid_quantity.status_code, 400)

        unknown_product = self.client.post(
            "/api/cart/items",
            json={"product_id": 999999, "quantity": 1},
            headers=self.csrf_headers(),
        )
        self.assertEqual(unknown_product.status_code, 404)

        added = self.client.post(
            "/api/cart/items",
            json={"product_id": product["product_id"], "quantity": 2},
            headers=self.csrf_headers(),
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.get_json()["quantity"], 2)

        updated = self.client.patch(
            f"/api/cart/items/{product['product_id']}",
            json={"quantity": 1},
            headers=self.csrf_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["quantity"], 1)

        removed = self.client.delete(
            f"/api/cart/items/{product['product_id']}", headers=self.csrf_headers()
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.get_json()["items"], [])

        malformed_membership = self.client.post(
            "/api/checkout/membership", json=[], headers=self.csrf_headers()
        )
        self.assertEqual(malformed_membership.status_code, 400)

        self.add_customer(email="membership@example.com")
        email_membership = self.client.post(
            "/api/checkout/membership",
            json={"membership": "membership@example.com"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(email_membership.status_code, 404)
        number_membership = self.client.post(
            "/api/checkout/membership",
            json={"membership": "MEMBER-1"},
            headers=self.csrf_headers(),
        )
        self.assertEqual(number_membership.status_code, 200)

    def test_missing_and_invalid_csrf_are_rejected(self):
        missing = self.client.post("/api/cart/items", json={})
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(missing.get_json()["code"], "csrf_failed")

        invalid = self.client.post(
            "/api/cart/items", json={}, headers={"X-CSRF-Token": "not-the-session-token"}
        )
        self.assertEqual(invalid.status_code, 403)
        self.assertEqual(invalid.get_json()["code"], "csrf_failed")

        valid_but_malformed = self.client.post(
            "/api/cart/items", json={}, headers=self.csrf_headers()
        )
        self.assertEqual(valid_but_malformed.status_code, 400)

    def test_guest_can_complete_checkout_and_receipt_is_session_bound(self):
        product = self.add_product(quantity=2)
        added = self.client.post(
            "/api/cart/items",
            json={"product_id": product["product_id"], "quantity": 1},
            headers=self.csrf_headers(),
        )
        self.assertEqual(added.status_code, 200)

        complete = self.client.post("/checkout/complete", headers=self.csrf_headers())
        self.assertEqual(complete.status_code, 302)
        self.assertIn("/checkout/receipt/", complete.headers["Location"])
        receipt = self.client.get(complete.headers["Location"])
        self.assertEqual(receipt.status_code, 200)
        self.assertIn(b"Test Water", receipt.data)

        with self.client.session_transaction() as session:
            session["checkout_receipt_id"] = None
        self.assertEqual(self.client.get(complete.headers["Location"]).status_code, 404)

        with self.app.app_context():
            self.assertEqual(db_module.get_product(product["product_id"])["quantity"], 1)

    def test_auth_boundaries_fail_closed(self):
        guest_page = self.client.get("/inventory")
        self.assertEqual(guest_page.status_code, 302)
        self.assertEqual(guest_page.headers["Location"], "/signin")
        self.assertEqual(self.client.get("/api/readings").status_code, 401)

        user_id, customer_id = self.add_customer()
        self.sign_in_session(user_id, "customer@example.com", customer_id)
        customer_staff_page = self.client.get("/inventory")
        self.assertEqual(customer_staff_page.status_code, 302)
        self.assertEqual(customer_staff_page.headers["Location"], "/account")

        self.sign_in_session(user_id, "customer@example.com", customer_id)
        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)

    def test_gpio_backend_mock_is_safe_without_hardware(self):
        gpio_backend.GPIO.setwarnings(False)
        gpio_backend.GPIO.setmode(gpio_backend.GPIO.BCM)
        gpio_backend.GPIO.setup(17, gpio_backend.GPIO.OUT)
        gpio_backend.GPIO.output(17, gpio_backend.GPIO.HIGH)
        if platform.system() == "Darwin":
            self.assertIsInstance(gpio_backend.GPIO, gpio_backend._MockGPIO)

    def test_quebec_phone_validation_is_strict_and_canonical(self):
        valid_values = (
            "5145551234",
            "(514) 555-1234",
            "+1 418-555-2345",
            "819.555.3456",
        )
        for value in valid_values:
            with self.subTest(value=value):
                self.assertTrue(valid_phone(value))
                self.assertRegex(normalize_quebec_phone(value), r"^\+1[0-9]{10}$")

        invalid_values = (
            "123-555-1234",       # Not a Quebec area code.
            "514-155-1234",       # NXX exchange cannot start with 0 or 1.
            "514-555-123",        # Only 9 local digits.
            "514-555-12345",      # 11 local digits.
            "514-555-0100",       # Reserved fictional 555 range.
            "+44 514 555 1234",   # Not a Canadian/NANP country code.
            "514-ABC-1234",       # Letters are not accepted.
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertFalse(valid_phone(value))
                self.assertIsNone(normalize_quebec_phone(value))

    def count_users(self):
        with self.app.app_context():
            return db_module.get_db().execute("SELECT COUNT(*) FROM Users").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
