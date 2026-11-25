import json
from math import isfinite

from db import get_db

DEVICE = "c30000455da7/3"
TOPIC = f"paretoanywhere/devices/{DEVICE}/dynamb"

METRICS = {
    "temperature": "temperature",
    "relativeHumidity": "humidity",
    "isMotionDetected": "motion",
    "batteryPercentage": "battery",
}


def valid_value(metric, value):
    if metric == "isMotionDetected":
        return isinstance(value, list) and bool(value) and all(
            type(channel) is bool for channel in value
        )
    if not finite_number(value):
        return False
    return metric == "temperature" or 0 <= value <= 100


def finite_number(value):
    return type(value) in (int, float) and abs(value) <= 1e308 and isfinite(value)


def store_message(topic, payload):
    if topic != TOPIC:
        return
    try:
        event = json.loads(payload)
    except (ValueError, RecursionError):
        return
    if not isinstance(event, dict):
        return
    timestamp = event.get("timestamp")
    if type(timestamp) is not int or not 0 < timestamp <= 8_640_000_000_000_000:
        return

    readings = [
        (DEVICE, metric, json.dumps(event[metric]), timestamp)
        for metric in METRICS
        if metric in event and valid_value(metric, event[metric])
    ]
    if readings:
        db = get_db()
        with db:
            db.executemany(
                """
                INSERT INTO ParetoMetrics (device, metric, value, timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (device, metric) DO UPDATE
                SET value = excluded.value, timestamp = excluded.timestamp
                WHERE excluded.timestamp >= ParetoMetrics.timestamp
                """,
                readings,
            )


def latest_fridge():
    rows = get_db().execute(
        "SELECT metric, value, timestamp FROM ParetoMetrics WHERE device = ?", (DEVICE,)
    )
    metrics = {row["metric"]: row for row in rows if row["metric"] in METRICS}
    if not metrics:
        return None

    reading = dict.fromkeys(METRICS.values())
    for key, row in metrics.items():
        reading[METRICS[key]] = json.loads(row["value"])
    if reading["motion"] is not None:
        reading["motion"] = any(reading["motion"])

    return {
        **reading,
        "name": "Fridge 3",
        "bluetooth": True,
        "timestamp": max(row["timestamp"] for row in metrics.values()),
        "reading_id": max(
            (metrics[key]["timestamp"] for key in ("temperature", "relativeHumidity")
             if key in metrics),
            default=None,
        ),
    }
