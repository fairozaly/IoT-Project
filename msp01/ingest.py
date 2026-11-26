"""Validated, hardware-independent Minew MSP01 dynamb ingestion.

The regular web application already has a Pareto Anywhere path. This module
adds the small data contract needed by a direct MSP01 bridge and keeps a
durable snapshot history for all measurements that the MSP01 can provide.
The support table is created lazily so this work does not require changing the
shared schema owner files.
"""

import json
import re
from datetime import datetime, timezone
from math import isfinite

from config import MSP01_ADDRESS
from db import get_db


MSP01_DYNAMB_TOPIC_SUFFIX = "dynamb"
HISTORY_TABLE = "MSP01Readings"
_DEVICE_RE = re.compile(r"^[0-9a-f]{12}(?:/[0-9]+)?$")
_MAX_TIMESTAMP = 8_640_000_000_000_000
_SUPPORTED_FIELDS = ("temperature", "humidity", "light", "motion")


def ensure_history_table(database=None):
    """Create the narrowly scoped MSP01 history store when it is first used."""
    database = database or get_db()
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS MSP01Readings (
            reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            light REAL,
            motion INTEGER,
            battery REAL,
            rssi REAL,
            raw_payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_msp01_readings_device_time
            ON MSP01Readings(device, timestamp, reading_id);
        """
    )
    return database


def _finite_number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is below the supported range.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} is above the supported range.")
    return float(value)


def _device_name(value):
    if value is None:
        value = MSP01_ADDRESS
    if not isinstance(value, str):
        raise ValueError("MSP01 device address must be text.")
    normalized = value.strip().lower().replace(":", "")
    if not _DEVICE_RE.fullmatch(normalized):
        raise ValueError("MSP01 device address must be 12 hex digits, optionally followed by /slot.")
    return normalized


def _timestamp(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("MSP01 timestamp must be a finite number.")
    if value <= 0 or value > _MAX_TIMESTAMP:
        raise ValueError("MSP01 timestamp is outside the supported range.")
    # Pareto Anywhere and the BLE bridge use epoch milliseconds; accepting
    # seconds also makes the ingest function convenient for local test tools.
    seconds = float(value) / 1000 if value >= 100_000_000_000 else float(value)
    try:
        recorded = datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError("MSP01 timestamp is not a valid Unix timestamp.") from error
    if not 2000 <= recorded.year <= 2100:
        raise ValueError("MSP01 timestamp is outside the supported date range.")
    return int(seconds), recorded.strftime("%Y-%m-%d %H:%M:%S")


def _motion(value):
    if isinstance(value, list):
        if not value or any(type(item) is not bool for item in value):
            raise ValueError("MSP01 motion must be a non-empty boolean list.")
        return int(any(value))
    if type(value) is bool:
        return int(value)
    if type(value) is int and value in (0, 1):
        return value
    raise ValueError("MSP01 motion must be a boolean or boolean list.")


def _json_payload(payload):
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("MSP01 payload must be UTF-8 JSON.") from error
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, RecursionError) as error:
            raise ValueError("MSP01 payload must be valid JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError("MSP01 payload must be a JSON object.")
    return payload


def parse_dynamb(payload, device=None):
    """Validate a Pareto/MSP01 dynamb object and return a normalized snapshot."""
    event = _json_payload(payload)
    device_value = device or event.get("device") or event.get("transmitterId") or event.get("id")
    normalized_device = _device_name(device_value)
    timestamp, recorded_at = _timestamp(event.get("timestamp"))

    normalized = {
        "device": normalized_device,
        "timestamp": timestamp,
        "recorded_at": recorded_at,
        "temperature": None,
        "humidity": None,
        "light": None,
        "motion": None,
        "battery": None,
        "rssi": None,
    }

    if "temperature" in event:
        normalized["temperature"] = _finite_number(event["temperature"], "temperature", -100, 100)
    humidity_key = "relativeHumidity" if "relativeHumidity" in event else "humidity"
    if humidity_key in event:
        normalized["humidity"] = _finite_number(event[humidity_key], "humidity", 0, 100)
    light_key = next((key for key in ("illuminance", "luminousFlux", "light") if key in event), None)
    if light_key:
        normalized["light"] = _finite_number(event[light_key], "light", 0, 1_000_000)
    motion_key = "isMotionDetected" if "isMotionDetected" in event else "motion"
    if motion_key in event:
        normalized["motion"] = _motion(event[motion_key])
    if "batteryPercentage" in event or "battery" in event:
        key = "batteryPercentage" if "batteryPercentage" in event else "battery"
        normalized["battery"] = _finite_number(event[key], "battery", 0, 100)
    if "rssi" in event:
        normalized["rssi"] = _finite_number(event["rssi"], "rssi", -200, 0)

    if all(normalized[field] is None for field in _SUPPORTED_FIELDS):
        raise ValueError("MSP01 payload contains no supported sensor measurement.")
    normalized["raw_payload"] = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return normalized


def ingest_dynamb(payload, device=None, database=None):
    """Validate and persist one MSP01 snapshot, returning the stored reading."""
    normalized = parse_dynamb(payload, device=device)
    database = ensure_history_table(database)
    previous = database.execute(
        "SELECT temperature, humidity, light, motion, battery, rssi "
        "FROM MSP01Readings WHERE device = ? ORDER BY timestamp DESC, reading_id DESC LIMIT 1",
        (normalized["device"],),
    ).fetchone()
    # A BLE advertisement may expose only one slot at a time. Carry forward
    # the last known fields so each historical row remains a usable snapshot.
    if previous:
        for field in ("temperature", "humidity", "light", "motion", "battery", "rssi"):
            if normalized[field] is None:
                normalized[field] = previous[field]
    cursor = database.execute(
        """INSERT INTO MSP01Readings
           (device, timestamp, recorded_at, temperature, humidity, light, motion, battery, rssi, raw_payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        tuple(normalized[field] for field in (
            "device", "timestamp", "recorded_at", "temperature", "humidity",
            "light", "motion", "battery", "rssi", "raw_payload",
        )),
    )
    database.commit()
    normalized["reading_id"] = cursor.lastrowid
    return normalized


def get_latest_reading(device=None, database=None):
    database = ensure_history_table(database)
    if device is None:
        device = MSP01_ADDRESS or None
    if device is not None:
        device = _device_name(device)
        return database.execute(
            "SELECT * FROM MSP01Readings WHERE device = ? "
            "ORDER BY timestamp DESC, reading_id DESC LIMIT 1", (device,)
        ).fetchone()
    return database.execute(
        "SELECT * FROM MSP01Readings ORDER BY timestamp DESC, reading_id DESC LIMIT 1"
    ).fetchone()


def get_history(device=None, start_timestamp=None, end_timestamp=None, database=None):
    database = ensure_history_table(database)
    clauses = []
    values = []
    if device is not None:
        clauses.append("device = ?")
        values.append(_device_name(device))
    if start_timestamp is not None:
        clauses.append("timestamp >= ?")
        values.append(_timestamp(start_timestamp)[0])
    if end_timestamp is not None:
        clauses.append("timestamp < ?")
        values.append(_timestamp(end_timestamp)[0])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return database.execute(
        f"SELECT * FROM MSP01Readings{where} ORDER BY timestamp, reading_id", values
    ).fetchall()
