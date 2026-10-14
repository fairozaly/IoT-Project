import os

from flask import Flask, flash, redirect, render_template, request, url_for

from db import (
    DATABASE,
    add_customer,
    close_connection,
    get_customer_by_email,
    get_customer_by_phone,
    get_customers,
    init_db,
)

import paho.mqtt.client as mqtt

from gpio import (
    indicate_success,
    indicate_failure
)

MQTT_SERVER_ADDRESS = "10.0.0.237"
MQTT_SERVER_PORT = 1883

app = Flask(__name__)
app.secret_key = "827mo34t9zwb3ty598"
app.teardown_appcontext(close_connection)

fridge_readings = {}

def on_connect_mqtt(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")

    client.subscribe("SmartHome/Frig1")

def on_message_mqtt(client, userdata, message):
    label = message.topic.rsplit("/", 1)[-1]

    try:
        humidity, temperature = message.payload.decode().split(",")
        fridge_readings[label] = {
            "temperature": float(temperature),
            "humidity": float(humidity),
        }
    except ValueError:
        print(f"Invalid payload on {message.topic}: {message.payload!r}")

def setup_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect_mqtt
    client.on_message = on_message_mqtt
    client.connect(MQTT_SERVER_ADDRESS, MQTT_SERVER_PORT)
    client.loop_start()
    return client

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
    return render_template("fridges.html", fridges=fridge_readings, active_page="fridges")

@app.route("/settings")
def settings():
    return render_template("settings.html", active_page="settings")


if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        print("initializing database...")
        init_db(app)

    setup_mqtt()

    app.run(debug=True)
