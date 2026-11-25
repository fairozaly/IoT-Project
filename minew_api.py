import hmac
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from flask import Blueprint, current_app, jsonify, request

minew = Blueprint('minew', __name__)
_lock = Lock()


def _db_path():
    return Path(current_app.instance_path) / 'minew.sqlite3'


def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=5)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS minew_latest (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        device_id TEXT, temperature REAL, humidity REAL,
        illuminance REAL, motion_detected INTEGER,
        battery_percentage REAL, timestamp TEXT, last_motion_at TEXT
    )''')
    return con


def _number(payload, field, lower, upper):
    if field not in payload:
        return None
    value = payload[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{field} must be a finite number')
    if not lower <= value <= upper:
        raise ValueError(f'{field} out of range')
    return value


@minew.get('/api/minew')
def get_minew():
    with _connect() as con:
        row = con.execute('SELECT * FROM minew_latest WHERE id = 1').fetchone()
    if row is None:
        return jsonify({'timestamp': None})
    result = dict(row)
    result.pop('id', None)
    # A PIR trigger is an event, not a continuous occupancy guarantee.
    if result['last_motion_at']:
        from datetime import timedelta
        last = datetime.fromisoformat(result['last_motion_at'])
        result['motion_detected'] = (datetime.now(timezone.utc) - last) < timedelta(seconds=5)
    else:
        result['motion_detected'] = None
    return jsonify(result)


@minew.post('/api/minew/ingest')
def ingest_minew():
    expected = os.environ.get('MINEW_INGEST_TOKEN', '')
    supplied = request.headers.get('X-Minew-Token', '')
    if not expected or not hmac.compare_digest(supplied, expected):
        return jsonify({'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Expected a JSON object'}), 400
    try:
        fields = {
            'temperature': _number(payload, 'temperature', -40, 85),
            'humidity': _number(payload, 'humidity', 0, 100),
            'illuminance': _number(payload, 'illuminance', 0, 200000),
            'battery_percentage': _number(payload, 'battery_percentage', 0, 100),
        }
        if 'motion_detected' in payload and not isinstance(payload['motion_detected'], bool):
            raise ValueError('motion_detected must be a boolean')
        if 'device_id' in payload and (not isinstance(payload['device_id'], str) or len(payload['device_id']) > 80):
            raise ValueError('Invalid device_id')
        if not any(k in payload for k in (*fields.keys(), 'motion_detected')):
            raise ValueError('No sensor values provided')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _connect() as con:
            previous = con.execute('SELECT * FROM minew_latest WHERE id = 1').fetchone()
            existing = dict(previous) if previous else {}
            updated = {
                'device_id': payload.get('device_id', existing.get('device_id')),
                'timestamp': now,
                'last_motion_at': now if payload.get('motion_detected') is True else existing.get('last_motion_at'),
                'motion_detected': 1 if payload.get('motion_detected') is True else existing.get('motion_detected'),
            }
            for field, value in fields.items():
                updated[field] = value if field in payload else existing.get(field)
            con.execute('''INSERT INTO minew_latest
                (id, device_id, temperature, humidity, illuminance, motion_detected,
                 battery_percentage, timestamp, last_motion_at)
                VALUES (1,:device_id,:temperature,:humidity,:illuminance,:motion_detected,
                        :battery_percentage,:timestamp,:last_motion_at)
                ON CONFLICT(id) DO UPDATE SET
                device_id=excluded.device_id,temperature=excluded.temperature,
                humidity=excluded.humidity,illuminance=excluded.illuminance,
                motion_detected=excluded.motion_detected,
                battery_percentage=excluded.battery_percentage,
                timestamp=excluded.timestamp,last_motion_at=excluded.last_motion_at''', updated)
            con.commit()
    return jsonify({'ok': True, 'timestamp': now})
