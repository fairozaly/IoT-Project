import os
import secrets
import sqlite3
import math
from datetime import datetime, time, timedelta, timezone
from threading import Lock

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from db import (
    add_customer,
    add_product,
    close_connection,
    delete_customer,
    delete_product,
    delete_product_tag,
    edit_product,
    get_category_stock_thresholds,
    get_customer,
    get_customer_by_email,
    get_customer_by_phone,
    get_customers,
    get_fridge_thresholds,
    get_db,
    get_latest_readings,
    get_pending_alerts,
    get_product,
    get_product_receptions,
    get_product_tags,
    get_products,
    get_sensor_readings_for_period,
    init_db,
    mark_alerts_sent,
    normalize_epc,
    receive_scanned_tags,
    set_category_stock_threshold,
    set_sensor_thresholds,
    undo_received_tag,
    update_customer_membership,
)

from account import account
from auth import init_auth
from cart import cart, cart_owner, checkout_customer
from fan_control import get_status, init_control, stop_manually
from gpio import indicate_failure, indicate_success

from fan import stop_fan

from mqtt import setup_mqtt
from pareto import latest_fridge
from reports import reports
from receipts import LOCAL_TZ
import tag_reader
from validation_security import (
    clean_text,
    json_error,
    normalize_quebec_phone,
    parse_finite_number,
    valid_email,
    valid_phone,
)

app = Flask(__name__)
receiving_lock = Lock()
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.teardown_appcontext(close_connection)
init_auth(app)
app.register_blueprint(cart)
app.register_blueprint(account)
app.register_blueprint(reports)


def product_form_values(values):
    """Validate the shared product form while preserving its submitted values."""
    errors = []
    result = {}
    fields = (
        ("name", "Product name", 120, True),
        ("category", "Category", 80, True),
        ("company", "Producer company", 120, True),
        ("SDK", "SDK", 64, False),
        ("image_url", "Image URL", 500, False),
    )
    for key, label, maximum, required in fields:
        try:
            result[key] = clean_text(values.get(key, ""), label, required=required, maximum=maximum)
        except ValueError as error:
            errors.append(str(error))

    upc = values.get("upc", "")
    if not isinstance(upc, str) or not upc.strip():
        errors.append("UPC is required.")
        result["upc"] = ""
    else:
        result["upc"] = upc.strip()
        if not result["upc"].isdigit() or not 1 <= len(result["upc"]) <= 13:
            errors.append("UPC must contain 1 to 13 digits.")

    try:
        result["price"] = parse_finite_number(values.get("price", ""), "Price", minimum=0, maximum=1_000_000)
    except ValueError as error:
        errors.append(str(error))
        result["price"] = 0
    return result, errors


def inventory_snapshot():
    """Return the current product stock state for staff polling and reports."""
    rows = get_db().execute(
        """
        SELECT p.product_id, p.name, p.category, p.quantity,
               COUNT(t.tag_id) AS tag_count,
               COALESCE(th.threshold, 5) AS low_stock_threshold
        FROM Products p
        LEFT JOIN ProductTags t ON t.product_id = p.product_id
        LEFT JOIN CategoryStockThresholds th ON th.category = p.category
        GROUP BY p.product_id
        ORDER BY p.name COLLATE NOCASE, p.product_id
        """
    ).fetchall()
    items = []
    for row in rows:
        quantity = row["quantity"]
        threshold = row["low_stock_threshold"]
        status = "out_of_stock" if quantity == 0 else (
            "low_stock" if quantity <= threshold else "in_stock"
        )
        items.append({
            "product_id": row["product_id"],
            "name": row["name"],
            "category": row["category"],
            "quantity": quantity,
            "tag_count": row["tag_count"],
            "low_stock_threshold": threshold,
            "status": status,
        })
    return items


def _today_bounds():
    today = datetime.now(LOCAL_TZ).date()
    start = datetime.combine(today, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return today, tuple(
        moment.astimezone(timezone.utc).replace(tzinfo=None).isoformat(
            sep=" ", timespec="seconds"
        ) for moment in (start, end)
    )


def admin_dashboard_data():
    today, bounds = _today_bounds()
    database = get_db()
    totals = database.execute(
        """
        SELECT COUNT(DISTINCT t.transaction_id) AS transactions,
               COALESCE(SUM(t.total_amount), 0) AS sales,
               COALESCE(SUM(i.quantity), 0) AS items
        FROM Transactions t
        LEFT JOIN TransactionItems i USING (transaction_id)
        WHERE t.status = 'completed'
          AND t.transaction_date >= ? AND t.transaction_date < ?
        """, bounds,
    ).fetchone()

    # The current schema has no cost field. Support an existing compatible
    # column if one is present, but never present revenue as fabricated profit.
    product_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(Products)")
    }
    profit = None
    if "cost_price" in product_columns:
        cost_check = database.execute(
            """
            SELECT COUNT(*) AS missing
            FROM TransactionItems i JOIN Products p USING (product_id)
            JOIN Transactions t USING (transaction_id)
            WHERE t.status = 'completed'
              AND t.transaction_date >= ? AND t.transaction_date < ?
              AND p.cost_price IS NULL
            """, bounds,
        ).fetchone()
        if not cost_check["missing"]:
            profit = database.execute(
                """
                SELECT COALESCE(SUM(i.quantity * (i.price_at_sale - p.cost_price)), 0)
                FROM TransactionItems i JOIN Products p USING (product_id)
                JOIN Transactions t USING (transaction_id)
                WHERE t.status = 'completed'
                  AND t.transaction_date >= ? AND t.transaction_date < ?
                """, bounds,
            ).fetchone()[0]

    return {
        "today": today,
        "sales": float(totals["sales"] or 0),
        "profit": None if profit is None else float(profit),
        "transactions": int(totals["transactions"] or 0),
        "items": int(totals["items"] or 0),
        "fridges": storage_readings(),
    }


def account_rows():
    return get_db().execute(
        """
        SELECT u.user_id, u.email AS account_email, u.customer_id,
               c.first_name, c.last_name, c.email AS customer_email,
               CASE WHEN u.customer_id IS NULL THEN 'admin' ELSE 'customer' END AS role
        FROM Users u LEFT JOIN Customers c ON c.customer_id = u.customer_id
        ORDER BY role, account_email COLLATE NOCASE
        """
    ).fetchall()

@app.route("/customers")
def customers():
    return render_template(
        "customers.html", customers=get_customers(), accounts=account_rows(),
        active_page="customers",
    )


@app.route("/", endpoint="index")
def index():
    """Send each visitor to the most useful starting point for their role."""
    if not session.get("user_id"):
        return redirect(url_for("checkout"))
    if session.get("customer_id") is not None:
        return redirect(url_for("account.overview"))
    return redirect(url_for("fridges"))

@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def edit_customer(customer_id):
    customer = get_customer(customer_id)
    if customer is None:
        abort(404)
    if request.method == "POST":
        membership_number = request.form.get("membership_number", "").strip().upper()
        if not membership_number:
            flash("Membership number is required.", "error")
            indicate_failure()
            return render_template("customer_edit.html", customer=customer, active_page="customers")
        if len(membership_number) > 64:
            flash("Membership number must be 64 characters or fewer.", "error")
            indicate_failure()
            return render_template("customer_edit.html", customer=customer, active_page="customers")
        try:
            update_customer_membership(customer_id, membership_number)
        except sqlite3.IntegrityError:
            flash("That membership number is already used by another customer.", "error")
            indicate_failure()
            return render_template("customer_edit.html", customer=customer, active_page="customers")
        flash(f"Membership number updated for {customer['first_name']} {customer['last_name']}.", "success")
        indicate_success()
        return redirect(url_for("customers"))
    return render_template("customer_edit.html", customer=customer, active_page="customers")


@app.post("/customers/<int:customer_id>/email")
def update_customer_email(customer_id):
    customer = get_customer(customer_id)
    if customer is None:
        flash("Customer not found.", "error")
        return redirect(url_for("customers"))

    email = request.form.get("email", "").strip().lower()
    if not valid_email(email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("edit_customer", customer_id=customer_id))

    database = get_db()
    linked_user = database.execute(
        "SELECT user_id FROM Users WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    conflict = database.execute(
        """
        SELECT 1 FROM Customers
        WHERE lower(email) = lower(?) AND customer_id <> ?
        UNION ALL
        SELECT 1 FROM Users
        WHERE lower(email) = lower(?) AND (? IS NULL OR user_id <> ?)
        LIMIT 1
        """, (email, customer_id, email,
               linked_user["user_id"] if linked_user else None,
               linked_user["user_id"] if linked_user else None),
    ).fetchone()
    if conflict:
        flash("That email address is already used by another account.", "error")
        return redirect(url_for("edit_customer", customer_id=customer_id))

    try:
        with database:
            database.execute(
                "UPDATE Customers SET email = ? WHERE customer_id = ?",
                (email, customer_id),
            )
            if linked_user:
                database.execute(
                    "UPDATE Users SET email = ? WHERE user_id = ?",
                    (email, linked_user["user_id"]),
                )
    except sqlite3.IntegrityError:
        flash("That email address is already used by another account.", "error")
        return redirect(url_for("edit_customer", customer_id=customer_id))

    flash("Customer email updated.", "success")
    return redirect(url_for("edit_customer", customer_id=customer_id))


@app.post("/customers/<int:customer_id>/delete")
def remove_customer(customer_id):
    customer = get_customer(customer_id)
    if customer is None:
        flash("Customer not found.", "error")
    elif delete_customer(customer_id):
        flash(
            f"Customer {customer['first_name']} {customer['last_name']} deleted successfully.",
            "success",
        )
        indicate_success()
    else:
        flash(
            "Customer cannot be deleted because they have transaction history.",
            "error",
        )
        indicate_failure()
    return redirect(url_for("customers"))


@app.post("/admin/users/<int:user_id>/role")
def update_account_role(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot change your own administrator access.", "error")
        return redirect(url_for("customers"))

    action = request.form.get("action", "").strip().lower()
    if action not in {"promote", "demote"}:
        flash("Choose a valid account role action.", "error")
        return redirect(url_for("customers"))

    database = get_db()
    user = database.execute(
        "SELECT user_id, email, customer_id FROM Users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        flash("Account not found.", "error")
        return redirect(url_for("customers"))

    if action == "promote":
        if user["customer_id"] is None:
            flash("That account is already an administrator.", "error")
            return redirect(url_for("customers"))
        database.execute("UPDATE Users SET customer_id = NULL WHERE user_id = ?", (user_id,))
        database.commit()
        flash(f"{user['email']} is now an administrator.", "success")
        return redirect(url_for("customers"))

    if user["customer_id"] is not None:
        flash("That account is already a customer account.", "error")
        return redirect(url_for("customers"))
    customer = database.execute(
        "SELECT customer_id FROM Customers WHERE lower(email) = lower(?) LIMIT 1",
        (user["email"],),
    ).fetchone()
    if customer is None:
        flash("Demotion requires an existing customer profile with the same email.", "error")
        return redirect(url_for("customers"))
    try:
        database.execute(
            "UPDATE Users SET customer_id = ? WHERE user_id = ?",
            (customer["customer_id"], user_id),
        )
        database.commit()
    except sqlite3.IntegrityError:
        database.rollback()
        flash("That customer profile is already linked to another account.", "error")
        return redirect(url_for("customers"))
    flash(f"{user['email']} is now a customer account.", "success")
    return redirect(url_for("customers"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        address = request.form.get("address", "").strip()
        phone_input = request.form.get("phone", "").strip()
        phone = normalize_quebec_phone(phone_input) if phone_input else None
        email = request.form.get("email", "").strip().lower() or None

        errors = []
        for value, label, maximum in (
            (first_name, "First name", 100),
            (last_name, "Last name", 100),
            (address, "Address", 200),
        ):
            if not value:
                errors.append(f"{label} is required.")
            elif len(value) > maximum:
                errors.append(f"{label} must be {maximum} characters or fewer.")
        if email and not valid_email(email):
            errors.append("Enter a valid email address.")
        if phone_input and not valid_phone(phone_input):
            errors.append("Enter a valid 10-digit phone number, such as (514) 555-1234.")
        if email and get_customer_by_email(email):
            errors.append("A customer with that email already exists.")
        if phone and get_customer_by_phone(phone):
            errors.append("A customer with that phone number already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            indicate_failure()
            return render_template(
                "registration.html",
                form=request.form,
                active_page="customers",
            )

        add_customer(first_name, last_name, address, phone, email)
        flash(f"Customer {first_name} {last_name} created successfully.", "success")
        indicate_success()
        return redirect(url_for("customers"))

    return render_template("registration.html", form={}, active_page="customers")

@app.route("/inventory")
def inventory():
    return render_template(
        "inventory.html",
        products=get_products(),
        receptions=get_product_receptions(),
        active_page="inventory",
    )


@app.get("/api/inventory")
def api_inventory():
    """Return current stock for staff dashboards and inventory polling."""
    return jsonify({
        "items": inventory_snapshot(),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })


@app.route("/admin")
def admin_dashboard():
    return render_template(
        "admin_dashboard.html", dashboard=admin_dashboard_data(), active_page="admin"
    )


@app.get("/products/<int:product_id>")
def product_detail(product_id):
    product = get_product(product_id)
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("inventory"))
    return render_template(
        "product_detail.html", product=product, tags=get_product_tags(product_id),
        active_page="inventory",
    )


@app.post("/products/<int:product_id>/tags/<int:tag_id>/delete")
def remove_product_tag(product_id, tag_id):
    if get_product(product_id) is None:
        flash("Product not found.", "error")
        return redirect(url_for("inventory"))
    if delete_product_tag(product_id, tag_id):
        flash("EPC deleted successfully.", "success")
    else:
        flash("EPC not found for this product.", "error")
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/products/new", methods=["GET", "POST"])
def new_product():
    if request.method == "POST":
        values = request.form.to_dict()
        product, errors = product_form_values(values)
        name = product.get("name") or ""
        category = product.get("category") or ""
        upc = product.get("upc") or ""
        company = product.get("company") or ""
        sdk = product.get("SDK")
        image_url = product.get("image_url")
        price = product.get("price", 0)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "product_form.html",
                product=values,
                product_id=None,
                active_page="inventory",
            )

        try:
            add_product(
                name=name,
                category=category,
                upc=upc,
                SDK=sdk,
                price=price,
                quantity=0,
                company=company,
                image_url=image_url,
            )
        except sqlite3.IntegrityError:
            flash("UPC or SDK is already used by another product.", "error")
            return render_template(
                "product_form.html",
                product=values,
                product_id=None,
                active_page="inventory",
            )

        flash(f"Product {name} added successfully.", "success")
        return redirect(url_for("inventory"))

    return render_template(
        "product_form.html", product={}, product_id=None, active_page="inventory"
    )


@app.post("/api/inventory/receive/scan")
def receive_scanned_stock():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data.keys() <= {"product_id", "after", "supplier"}:
        return json_error("Send only product_id, after, and supplier while scanning stock.")

    product_id = data.get("product_id")
    if type(product_id) is not int or not 0 < product_id <= 2**63 - 1:
        return json_error("product_id must be a positive whole number.")
    supplier = data.get("supplier")
    if supplier is not None and (not isinstance(supplier, str) or len(supplier.strip()) > 120):
        return json_error("supplier must be 120 characters or fewer.")
    after = data.get("after")
    if after is not None and (not isinstance(after, str) or len(after) > 20 or not after.isascii() or not after.isdecimal()):
        return json_error("after must be a valid scan cursor.")
    after_cursor = None
    if after is not None:
        after_cursor = int(after)
        if after_cursor > 2**63 - 1:
            return json_error("after must be a valid scan cursor.")

    if app.config.get("START_SERVICES", True):
        tag_reader.ensure_started()
    with receiving_lock:
        connected = tag_reader.is_connected()
        cursor, epcs = tag_reader.receive_scans(after_cursor)
        if not connected or not epcs:
            return jsonify(cursor=cursor, connected=connected, error=tag_reader.get_last_error())

        result = receive_scanned_tags(product_id, epcs, (supplier or "").strip() or None)
        if result["status"] == "missing_product":
            return json_error("Product not found.", 404, "not_found")
        return jsonify(cursor=cursor, connected=True, **result)


@app.post("/api/inventory/receive/undo")
def undo_stock_reception():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Send reception_id and epc to undo a received tag.")
    reception_id, epc = data.get("reception_id"), data.get("epc")
    if type(reception_id) is not int or not 0 < reception_id <= 2**63 - 1 or not isinstance(epc, str):
        return json_error("reception_id must be positive and epc must be text.")
    try:
        epc = normalize_epc(epc)
    except ValueError as error:
        return json_error(str(error))

    with receiving_lock:
        result = undo_received_tag(reception_id, epc)
        if result is None:
            return json_error("This tag was already removed, sold, or received again.", 409, "stale_resource")
        tag_reader.suppress_reception(epc)
        return jsonify(result)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product_page(product_id):
    product = get_product(product_id)
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("inventory"))

    if request.method == "POST":
        values = request.form.to_dict()
        product_values, errors = product_form_values(values)
        name = product_values.get("name") or ""
        category = product_values.get("category") or ""
        upc = product_values.get("upc") or ""
        company = product_values.get("company") or ""
        sdk = product_values.get("SDK")
        image_url = product_values.get("image_url")
        price = product_values.get("price", 0)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "product_form.html",
                product=values,
                product_id=product_id,
                active_page="inventory",
            )

        try:
            edit_product(
                product_id,
                name=name,
                category=category,
                upc=upc,
                SDK=sdk,
                price=price,
                company=company,
                image_url=image_url,
            )
        except sqlite3.IntegrityError:
            flash("UPC or SDK is already used by another product.", "error")
            return render_template(
                "product_form.html",
                product=values,
                product_id=product_id,
                active_page="inventory",
            )

        flash(f"Product {name} updated successfully.", "success")
        return redirect(url_for("inventory"))

    return render_template(
        "product_form.html",
        product=dict(product),
        product_id=product_id,
        active_page="inventory",
    )


@app.route("/products/<int:product_id>/delete", methods=["POST"])
def remove_product(product_id):
    product = get_product(product_id)
    if product is None:
        flash("Product not found.", "error")
    elif delete_product(product_id):
        flash(f"Product {product['name']} deleted successfully.", "success")
    else:
        flash("Product cannot be deleted because it is used in transactions.", "error")
    return redirect(url_for("inventory"))


@app.route("/checkout")
def checkout():
    cart_owner()
    mock_products = [
        {
            "product_id": product["product_id"],
            "name": product["name"],
            "in_stock": product["quantity"] > 0,
            "epcs": [
                tag["epc"] for tag in get_product_tags(product["product_id"])
            ],
        }
        for product in get_products()
    ]
    response = app.make_response(render_template(
        "checkout.html",
        active_page="checkout",
        checkout_customer=checkout_customer(),
        mock_products=mock_products,
    ))
    response.cache_control.no_store = True
    return response


@app.route("/fridges")
def fridges():
    return render_template("fridges.html", fridges=storage_readings(), active_page="fridges")

@app.route("/storage-history")
def storage_history():
    now = datetime.now(LOCAL_TZ)
    today = now.date()
    start_local = datetime.combine(today, time.min, tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

    groups = {}
    invalid_count = 0
    rows = get_sensor_readings_for_period(
        start_utc.isoformat(sep=" ", timespec="seconds"),
        end_utc.isoformat(sep=" ", timespec="seconds"),
    )
    for row in rows:
        group = groups.setdefault(
            row["sensor_id"],
            {
                "sensor_id": row["sensor_id"],
                "name": row["name"],
                "location": row["location"],
                "readings": [],
            },
        )
        if row["reading_id"] is None:
            continue

        timestamp = None
        raw_timestamp = row["timestamp"]
        if isinstance(raw_timestamp, str):
            try:
                timestamp_text = raw_timestamp.strip().replace(" ", "T", 1)
                if timestamp_text.endswith(("Z", "z")):
                    timestamp_text = timestamp_text[:-1] + "+00:00"
                timestamp = datetime.fromisoformat(timestamp_text)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(LOCAL_TZ)
            except (TypeError, ValueError, OverflowError):
                timestamp = None

        temperature = row["temperature"]
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = None
        if (
            timestamp is None
            or timestamp.date() != today
            or temperature is None
            or not math.isfinite(temperature)
        ):
            invalid_count += 1
            continue

        humidity = row["humidity"]
        try:
            humidity = float(humidity)
        except (TypeError, ValueError):
            humidity = None
        if humidity is not None and (
            not math.isfinite(humidity) or not 0 <= humidity <= 100
        ):
            humidity = None

        group["readings"].append(
            {
                "reading_id": row["reading_id"],
                "timestamp": raw_timestamp,
                "local_time": timestamp.strftime("%H:%M:%S"),
                "temperature": temperature,
                "humidity": humidity,
            }
        )

    return render_template(
        "storage_history.html",
        active_page="storage_history",
        history_groups=list(groups.values()),
        history_date=today.isoformat(),
        invalid_readings=invalid_count,
    )

@app.route("/settings", methods=["GET", "POST"])
def settings():
    thresholds = {row["name"]: dict(row) for row in get_fridge_thresholds()}
    status = 200
    if request.method == "POST":
        if request.form.get("setting") == "stock":
            try:
                limit = int(request.form.get("stock_threshold", ""))
                if not 0 <= limit <= 2**63 - 1:
                    raise ValueError
            except ValueError:
                flash("Enter a non-negative whole number for the low-stock limit.", "error")
                status = 400
            else:
                category = request.form.get("category", "").strip()
                if not category or len(category) > 80 or not set_category_stock_threshold(category, limit):
                    flash("Select an existing product category.", "error")
                    status = 400
                else:
                    flash(f"Low-stock limit saved for {category}.", "success")
                    return redirect(url_for("settings", _anchor="stock-thresholds"))
        else:
            name = request.form.get("name")
            if name not in thresholds:
                flash("Select a valid fridge.", "error")
                status = 400
            else:
                try:
                    temperature = parse_finite_number(
                        request.form.get("temp_threshold", ""),
                        "Temperature limit", minimum=-100, maximum=100,
                    )
                    humidity = parse_finite_number(
                        request.form.get("humid_threshold", ""),
                        "Humidity limit", minimum=0, maximum=100,
                    )
                except ValueError:
                    flash("Enter a temperature between -100 and 100°C and humidity between 0 and 100%.", "error")
                    status = 400
                else:
                    set_sensor_thresholds(name, temperature, humidity)
                    flash(f"Thresholds saved for {name}.", "success")
                    return redirect(url_for("settings"))

    return render_template(
        "settings.html", thresholds=thresholds.values(),
        stock_thresholds=get_category_stock_thresholds(), active_page="settings",
    ), status


@app.route("/profile")
def profile():
    return render_template(
        "profile.html", active_page="profile", dashboard_url=url_for("admin_dashboard")
    )

@app.route("/alerts")
def alerts():
    rows = get_pending_alerts()
    items = []
    alert_ids = []
    for row in rows:
        alert_ids.append(row["alert_id"])
        alert_type = row["alert_type"]
        if alert_type == "fan started":
            message = f"Fridge {row['sensor_name']} is out of range, fan started"
        elif alert_type == "fan stopped":
            message = f"Fridge {row['sensor_name']} fan stopped"
        elif alert_type.startswith("temperature"):
            message = (
                f"Fridge {row['sensor_name']} has a dangerous temperature {row['temperature']:.1f}C"
            )
        else:
            message = (
                f"Fridge {row['sensor_name']} has a dangerous humidity {row['humidity']:.1f}%"
            )
        items.append({"id": row["alert_id"], "message": message})
    mark_alerts_sent(alert_ids)
    return jsonify(items)


@app.route("/api/fan")
def api_fan():
    return jsonify(get_status())


@app.route("/api/fan/stop", methods=["POST"])
def api_stop_fan():
    stop_manually()
    return jsonify(get_status())

def storage_readings():
    readings = [dict(reading) for reading in get_latest_readings()]
    bluetooth_fridge = latest_fridge()
    if bluetooth_fridge is not None:
        limits = next(row for row in get_fridge_thresholds() if row["name"] == "Fridge 3")
        bluetooth_fridge["above_threshold"] = any(
            bluetooth_fridge[measurement] is not None
            and bluetooth_fridge[measurement] >= limits[limit]
            for measurement, limit in (
                ("temperature", "temp_threshold"), ("humidity", "humid_threshold")
            )
        )
        readings.append(bluetooth_fridge)
    return readings


@app.route("/api/readings")
def api_readings():
    return jsonify(storage_readings())


def create_app(test_config=None):
    app.config["START_SERVICES"] = True
    if test_config:
        app.config.update(test_config)
    if app.config.get("SECRET_KEY"):
        app.secret_key = app.config["SECRET_KEY"]
    init_db(app)
    if app.config["START_SERVICES"]:
        stop_fan()
    init_control(app)
    if app.config["START_SERVICES"]:
        app.extensions["mqtt"] = setup_mqtt(app)
        tag_reader.start()
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, use_reloader=False)
