from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from db import (
    add_customer,
    close_connection,
    get_customer_by_email,
    get_customer_by_phone,
    get_customers,
    get_latest_readings,
    get_pending_alerts,
    init_db,
    mark_alerts_sent,
)

from gpio import (
    indicate_success,
    indicate_failure
)

from mqtt import setup_mqtt

app = Flask(__name__)
app.secret_key = "827mo34t9zwb3ty598"
app.teardown_appcontext(close_connection)

@app.route("/")
def index():
    return render_template("customers.html", customers=get_customers(), active_page="customers")

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
    return render_template("inventory.html", active_page="inventory")

@app.route("/fridges")
def fridges():
    return render_template("fridges.html", fridges=get_latest_readings(), active_page="fridges")

@app.route("/settings")
def settings():
    return render_template("settings.html", active_page="settings")


@app.route("/alerts")
def alerts():
    rows = get_pending_alerts()
    items = []
    alert_ids = []
    for row in rows:
        alert_ids.append(row["alert_id"])
        if row["alert_type"].startswith("temperature"):
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


@app.route("/api/readings")
def api_readings():
    readings = get_latest_readings()
    return jsonify([
        {
            "name": reading["name"],
            "temperature": reading["temperature"],
            "humidity": reading["humidity"],
        }
        for reading in readings
    ])


if __name__ == "__main__":
    init_db(app)
    setup_mqtt(app)

    app.run(debug=True, use_reloader=False)
