import os
import secrets
import sqlite3

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from db import (
    add_customer,
    add_product,
    add_product_reception,
    close_connection,
    delete_product,
    edit_product,
    get_customer_by_email,
    get_customer_by_phone,
    get_customers,
    get_latest_readings,
    get_pending_alerts,
    get_product,
    get_product_by_barcode,
    get_product_receptions,
    get_products,
    init_db,
    mark_alerts_sent,
)

from auth import init_auth
from fan_control import get_status, init_control, stop_manually
from gpio import indicate_failure, indicate_success

from fan import stop_fan

from mqtt import setup_mqtt

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.teardown_appcontext(close_connection)
init_auth(app)

@app.route("/", endpoint="index")
@app.route("/customers")
def customers():
    return render_template("customers.html", customers=get_customers(), active_page="customers")

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


@app.route("/products/new", methods=["GET", "POST"])
def new_product():
    if request.method == "POST":
        values = request.form.to_dict()
        name = values.get("name", "").strip()
        category = values.get("category", "").strip()
        upc = values.get("upc", "").strip()
        epc = values.get("epc", "").strip()
        company = values.get("company", "").strip()
        sdk = values.get("SDK", "").strip() or None
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
        if not epc:
            errors.append("EPC is required.")
        elif len(epc) > 24:
            errors.append("EPC must be 24 characters or fewer.")
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
                epc=epc,
                SDK=sdk,
                price=price,
                quantity=0,
                company=company,
            )
        except sqlite3.IntegrityError:
            flash("UPC, EPC, or SDK is already used by another product.", "error")
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
        epc = values.get("epc", "").strip()
        company = values.get("company", "").strip()
        sdk = values.get("SDK", "").strip() or None
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
        if not epc:
            errors.append("EPC is required.")
        elif len(epc) > 24:
            errors.append("EPC must be 24 characters or fewer.")
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
                epc=epc,
                SDK=sdk,
                price=price,
                company=company,
            )
        except sqlite3.IntegrityError:
            flash("UPC, EPC, or SDK is already used by another product.", "error")
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


@app.route("/inventory/receive", methods=["POST"])
def receive_stock():
    product_id = request.form.get("product_id", type=int)
    quantity = request.form.get("quantity_received", type=int)
    supplier = request.form.get("supplier", "").strip() or None

    if product_id is None or get_product(product_id) is None:
        flash("Select a valid product.", "error")
    elif quantity is None or quantity <= 0:
        flash("Received quantity must be greater than zero.", "error")
    else:
        add_product_reception(product_id, quantity, supplier)
        flash(f"Received {quantity} item(s) into inventory.", "success")

    return redirect(url_for("inventory"))


# Checkout Stuffs
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    return render_template("checkout.html", active_page="checkout")

@app.route("/submit-barcode", methods=["POST"])
def scan_barcode():
    if request.method == "POST":
        data = request.get_json()
        barcode = data.get('barcode')   
        item = get_product_by_barcode(barcode);
        if item is None:
            # TODO: IMPLEMENT LATER - If unknown barcode prompt form to create new product OR just show an alert saying unknown
            flash("Unknown Barcode", "error")
            return jsonify({"error": "Unknown barcode", "barcode": barcode}), 404
        else:
            return jsonify({
            "product_id": item["product_id"],
            "barcode": item["barcode"],
            "name": item["name"],
            "price": item["price"],
            "stock": item["quantity"],
    })


@app.route("/fridges")
def fridges():
    return render_template("fridges.html", fridges=get_latest_readings(), active_page="fridges")

@app.route("/settings")
def settings():
    return render_template("settings.html", active_page="settings")

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

@app.route("/api/readings")
def api_readings():
    return jsonify([dict(reading) for reading in get_latest_readings()])

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
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, use_reloader=False)
