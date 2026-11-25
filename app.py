from math import isfinite
import os
import secrets
import sqlite3
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
    get_latest_readings,
    get_pending_alerts,
    get_product,
    get_product_receptions,
    get_product_tags,
    get_products,
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
import tag_reader

app = Flask(__name__)
receiving_lock = Lock()
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.teardown_appcontext(close_connection)
init_auth(app)
app.register_blueprint(cart)
app.register_blueprint(account)
app.register_blueprint(reports)

@app.route("/", endpoint="index")
@app.route("/customers")
def customers():
    return render_template("customers.html", customers=get_customers(), active_page="customers")

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


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip() or None
        email = request.form.get("email", "").strip() or None

        errors = []
        if not first_name:
            errors.append("First name is required.")
        if not last_name:
            errors.append("Last name is required.")
        if not address:
            errors.append("Address is required.")
        if get_customer_by_email(email):
            errors.append("A customer with that email already exists.")
        if get_customer_by_phone(phone):
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
        name = values.get("name", "").strip()
        category = values.get("category", "").strip()
        upc = values.get("upc", "").strip()
        company = values.get("company", "").strip()
        sdk = values.get("SDK", "").strip() or None
        image_url = values.get("image_url", "").strip() or None
        price_text = values.get("price", "").strip()

        errors = []
        if not name:
            errors.append("Product name is required.")
        if not category:
            errors.append("Category is required.")
        if not upc:
            errors.append("UPC is required.")
        elif len(upc) > 13:
            errors.append("UPC must be 13 characters or fewer.")
        if not company:
            errors.append("Producer company is required.")

        try:
            price = float(price_text)
            if price < 0:
                raise ValueError
        except ValueError:
            price = 0
            errors.append("Enter a valid price.")

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
        return jsonify(error="Receive stock by scanning tags with the RFID reader."), 400

    product_id = data.get("product_id")
    if type(product_id) is not int or not 0 < product_id <= 2**63 - 1:
        return jsonify(error="Select a valid product."), 400
    supplier = data.get("supplier")
    if supplier is not None and not isinstance(supplier, str):
        return jsonify(error="Invalid supplier."), 400
    after = data.get("after")
    if after is not None and (not isinstance(after, str) or len(after) > 20 or not after.isascii() or not after.isdecimal()):
        return jsonify(error="Invalid scan position. Select the product again."), 400

    if app.config.get("START_SERVICES", True):
        tag_reader.ensure_started()
    with receiving_lock:
        connected = tag_reader.is_connected()
        cursor, epcs = tag_reader.receive_scans(int(after) if after is not None else None)
        if not connected or not epcs:
            return jsonify(cursor=cursor, connected=connected, error=tag_reader.get_last_error())

        result = receive_scanned_tags(product_id, epcs, (supplier or "").strip() or None)
        if result["status"] == "missing_product":
            return jsonify(error="Product not found."), 404
        return jsonify(cursor=cursor, connected=True, **result)


@app.post("/api/inventory/receive/undo")
def undo_stock_reception():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Select a received tag to undo."), 400
    reception_id, epc = data.get("reception_id"), data.get("epc")
    if type(reception_id) is not int or not 0 < reception_id <= 2**63 - 1 or not isinstance(epc, str):
        return jsonify(error="Select a received tag to undo."), 400
    try:
        epc = normalize_epc(epc)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    with receiving_lock:
        result = undo_received_tag(reception_id, epc)
        if result is None:
            return jsonify(error="This tag was already removed, sold, or received again."), 409
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
        name = values.get("name", "").strip()
        category = values.get("category", "").strip()
        upc = values.get("upc", "").strip()
        company = values.get("company", "").strip()
        sdk = values.get("SDK", "").strip() or None
        image_url = values.get("image_url", "").strip() or None
        price_text = values.get("price", "").strip()

        errors = []
        if not name:
            errors.append("Product name is required.")
        if not category:
            errors.append("Category is required.")
        if not upc:
            errors.append("UPC is required.")
        elif len(upc) > 13:
            errors.append("UPC must be 13 characters or fewer.")
        if not company:
            errors.append("Producer company is required.")

        try:
            price = float(price_text)
            if price < 0:
                raise ValueError
        except ValueError:
            price = 0
            errors.append("Enter a valid price.")

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
    response = app.make_response(render_template(
        "checkout.html", active_page="checkout", checkout_customer=checkout_customer()
    ))
    response.cache_control.no_store = True
    return response


@app.route("/fridges")
def fridges():
    return render_template("fridges.html", fridges=storage_readings(), active_page="fridges")

@app.route("/storage-history")
def storage_history():
    return render_template("storage_history.html", active_page="storage_history")

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
                category = request.form.get("category")
                if not set_category_stock_threshold(category, limit):
                    abort(400, "Select an existing product category.")
                flash(f"Low-stock limit saved for {category}.", "success")
                return redirect(url_for("settings", _anchor="stock-thresholds"))
        else:
            name = request.form.get("name")
            if name not in thresholds:
                abort(400)
            try:
                temperature = float(request.form.get("temp_threshold", ""))
                humidity = float(request.form.get("humid_threshold", ""))
                if not isfinite(temperature) or not 0 <= humidity <= 100:
                    raise ValueError
            except ValueError:
                flash("Enter a valid temperature and a humidity between 0 and 100%.", "error")
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
    return render_template("profile.html", active_page="profile")

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
