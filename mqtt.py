from math import isfinite
import os

import paho.mqtt.client as mqtt

from config import MSP01_ADDRESS, MSP01_ENABLED, MSP01_TOPIC

from db import (
    add_sensor_reading,
    create_alert,
    get_or_create_sensor,
    get_sensor_thresholds,
)

from fan_control import update_sensor
from pareto import TOPIC as PARETO_TOPIC, store_message
from msp01.ingest import ingest_dynamb

MQTT_SERVER_ADDRESS = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_SERVER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MSP01_DYNAMB_TOPIC = f"{MSP01_TOPIC}/dynamb"


def check_thresholds(sensor_id, reading_id, temperature, humidity):
    limits = get_sensor_thresholds(sensor_id)
    if limits is None:
        return

    violations = []

    if temperature >= limits["temp_threshold"]:
        violations.append(f"temperature high ({temperature} >= {limits['temp_threshold']})")

    if humidity >= limits["humid_threshold"]:
        violations.append(f"humidity high ({humidity} >= {limits['humid_threshold']})")

    for violation in violations:
        create_alert(reading_id, violation)

    update_sensor(sensor_id, reading_id, bool(violations))


def on_connect_mqtt(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")

    client.subscribe("SmartHome/#")
    client.subscribe(PARETO_TOPIC)
    if MSP01_ENABLED:
        client.subscribe(MSP01_DYNAMB_TOPIC)


def on_disconnect_mqtt(client, userdata, flags, reason_code, properties):
    print(f"Disconnected with result code {reason_code}; reconnecting...")


def on_message_mqtt(client, userdata, message):
    app = client._flask_app
    label = message.topic.rsplit("/", 1)[-1]

    try:
        humidity, temperature = message.payload.decode().split(",")
        humidity = float(humidity)
        temperature = float(temperature)
        if not label or not isfinite(humidity) or not isfinite(temperature):
            raise ValueError("Invalid sensor reading")
    except ValueError:
        print(f"Invalid payload on {message.topic}: {message.payload!r}")
        return

    try:
        with app.app_context():
            sensor_id = get_or_create_sensor(label, label)
            reading_id = add_sensor_reading(sensor_id, temperature, humidity)
            check_thresholds(sensor_id, reading_id, temperature, humidity)
    except Exception as error:
        print(f"Failed to handle message on {message.topic}: {error!r}")


def on_pareto_message(client, userdata, message):
    app = client._flask_app
    with app.app_context():
        try:
            store_message(message.topic, message.payload)
        except Exception:
            app.logger.exception("Failed to store Pareto Anywhere reading")


def on_msp01_message(client, userdata, message):
    """Ingest a direct BLE bridge dynamb message without real hardware in tests."""
    app = client._flask_app
    with app.app_context():
        try:
            return ingest_dynamb(message.payload, device=MSP01_ADDRESS or None)
        except ValueError:
            app.logger.warning("Invalid MSP01 dynamb payload on %s", message.topic)
            return None


def setup_mqtt(app):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client._flask_app = app
    client.on_connect = on_connect_mqtt
    client.on_disconnect = on_disconnect_mqtt
    client.on_message = on_message_mqtt
    client.message_callback_add(PARETO_TOPIC, on_pareto_message)
    client.message_callback_add(MSP01_DYNAMB_TOPIC, on_msp01_message)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.connect_async(MQTT_SERVER_ADDRESS, MQTT_SERVER_PORT)
    client.loop_start()
    return client

