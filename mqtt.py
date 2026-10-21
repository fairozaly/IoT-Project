import paho.mqtt.client as mqtt

from db import (
    add_sensor_reading,
    create_alert,
    get_or_create_sensor,
    get_sensor_thresholds,
    set_sensor_thresholds,
)

from fan import (
    is_fan_running,
    start_fan,
    stop_fan,
)

MQTT_SERVER_ADDRESS = "192.168.50.111"
MQTT_SERVER_PORT = 1883

FAN_STARTED_ALERT = "fan started"
FAN_STOPPED_ALERT = "fan stopped"

FRIDGE_THRESHOLDS = {
    "Frig1": {
        "temp_threshold": 25.0,
        "humid_threshold": 70.0,
    },
}


def configure_fridge_thresholds():
    for name, limits in FRIDGE_THRESHOLDS.items():
        set_sensor_thresholds(
            name,
            limits["temp_threshold"],
            limits["humid_threshold"],
        )
        print(f"Configured thresholds for {name}: {limits}")


def update_fan(out_of_range, reading_id):
    running = is_fan_running()

    if out_of_range and not running:
        start_fan()
        create_alert(reading_id, FAN_STARTED_ALERT)
    elif not out_of_range and running:
        stop_fan()
        create_alert(reading_id, FAN_STOPPED_ALERT)


def check_thresholds(sensor_id, reading_id, temperature, humidity):
    limits = get_sensor_thresholds(sensor_id)
    if limits is None:
        return

    violations = []

    if temperature > limits["temp_threshold"]:
        violations.append(f"temperature high ({temperature} > {limits['temp_threshold']})")

    if humidity > limits["humid_threshold"]:
        violations.append(f"humidity high ({humidity} > {limits['humid_threshold']})")

    for violation in violations:
        create_alert(reading_id, violation)

    update_fan(bool(violations), reading_id)


def on_connect_mqtt(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")

    client.subscribe("SmartHome/Frig1")


def on_message_mqtt(client, userdata, message):
    app = client._flask_app
    label = message.topic.rsplit("/", 1)[-1]

    try:
        humidity, temperature = message.payload.decode().split(",")
        temperature = float(temperature)
        humidity = float(humidity)
    except ValueError:
        print(f"Invalid payload on {message.topic}: {message.payload!r}")
        return

    with app.app_context():
        sensor_id = get_or_create_sensor(label, label)
        reading_id = add_sensor_reading(sensor_id, temperature, humidity)
        check_thresholds(sensor_id, reading_id, temperature, humidity)


def setup_mqtt(app):
    with app.app_context():
        configure_fridge_thresholds()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client._flask_app = app
    client.on_connect = on_connect_mqtt
    client.on_message = on_message_mqtt
    client.connect(MQTT_SERVER_ADDRESS, MQTT_SERVER_PORT)
    client.loop_start()
    return client

