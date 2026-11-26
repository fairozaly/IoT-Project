import json
import re
from math import isfinite

from config import FRIDGE3_BLE_DEVICE
from db import get_db
from msp01.ingest import get_latest_reading as get_latest_msp01_reading
from msp01.ingest import ingest_dynamb

DEVICE = FRIDGE3_BLE_DEVICE
if not re.fullmatch(r"[0-9a-f]{12}/[23]", DEVICE):
    raise ValueError("FRIDGE3_BLE_DEVICE must be a 12-digit hex address followed by /2 or /3.")
TOPIC = f"paretoanywhere/devices/{DEVICE}/dynamb"

METRICS = {
    "temperature": "temperature",
    "relativeHumidity": "humidity",
    "isMotionDetected": "motion",
    "batteryPercentage": "battery",
    "illuminance": "illuminance",
    "isLightDetected": "light_detected",
}


def valid_value(metric, value):
    if metric in ("isMotionDetected", "isLightDetected"):
        return isinstance(value, list) and bool(value) and all(
            type(channel) is bool for channel in value
        )
    if not finite_number(value):
        return False
    if metric == "illuminance":
        return value >= 0
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

    if "isMotionDetected" not in event and "isOccupancyDetected" in event:
        event["isMotionDetected"] = event["isOccupancyDetected"]

    readings = [
        (DEVICE, metric, json.dumps(event[metric]), timestamp)
        for metric in METRICS
        if metric in event and valid_value(metric, event[metric])
    ]
    if readings:
        # Keep the existing latest-metric table and also retain a full MSP01
        # history snapshot for temperature, humidity, light, and motion.
        try:
            ingest_dynamb(event, device=DEVICE)
        except ValueError:
            # Pareto's existing metric path remains tolerant of partial
            # dynamb events that do not contain a complete supported snapshot.
            pass
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
    historical = get_latest_msp01_reading(DEVICE)
    if not metrics and historical is None:
        return None

    reading = dict.fromkeys(METRICS.values())
    for key, row in metrics.items():
        reading[METRICS[key]] = json.loads(row["value"])
    for key in ("motion", "light_detected"):
        if reading[key] is not None:
            reading[key] = any(reading[key])

    if historical is not None:
        for metric, field in (
            ("temperature", "temperature"),
            ("humidity", "humidity"),
            ("illuminance", "light"),
        ):
            if historical[field] is not None:
                reading[metric] = historical[field]
        if historical["motion"] is not None:
            reading["motion"] = bool(historical["motion"])

    return {
        **reading,
        "name": "Fridge 3",
        "bluetooth": True,
        "timestamp": max(
            [row["timestamp"] for row in metrics.values()]
            + ([historical["timestamp"] * 1000] if historical is not None else [])
        ),
        "reading_id": max(
            (metrics[key]["timestamp"] for key in ("temperature", "relativeHumidity")
             if key in metrics),
            default=historical["timestamp"] * 1000 if historical is not None else None,
        ),
    }
