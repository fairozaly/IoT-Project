import paho.mqtt.client as mqtt

from db import (
    add_sensor_reading,
    create_alert,
    get_or_create_sensor,
    get_sensor_thresholds,
    set_sensor_thresholds,
)

MQTT_SERVER_ADDRESS = "192.168.50.111"
MQTT_SERVER_PORT = 1883

FRIDGE_THRESHOLDS = {
    "Frig1": {
        "temp_min": 15.0,
        "temp_max": 25.0,
        "humid_min": 30.0,
        "humid_max": 70.0,
    },
}


def configure_fridge_thresholds():
    for name, limits in FRIDGE_THRESHOLDS.items():
        set_sensor_thresholds(
            name,
            limits["temp_min"],
            limits["temp_max"],
            limits["humid_min"],
            limits["humid_max"],
        )
        print(f"Configured thresholds for {name}: {limits}")


def check_thresholds(sensor_id, reading_id, temperature, humidity):
    limits = get_sensor_thresholds(sensor_id)
    if limits is None:
        return

    if temperature < limits["temp_min"]:
        create_alert(reading_id, f"temperature low ({temperature} < {limits['temp_min']})")
    elif temperature > limits["temp_max"]:
        create_alert(reading_id, f"temperature high ({temperature} > {limits['temp_max']})")

    if humidity < limits["humid_min"]:
        create_alert(reading_id, f"humidity low ({humidity} < {limits['humid_min']})")
    elif humidity > limits["humid_max"]:
        create_alert(reading_id, f"humidity high ({humidity} > {limits['humid_max']})")


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

