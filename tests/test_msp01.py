import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from app import create_app
from msp01.ingest import get_history, get_latest_reading, ingest_dynamb, parse_dynamb


class MSP01IngestTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="smart-store-msp01-")
        self.app = create_app({
            "TESTING": True,
            "START_SERVICES": False,
            "DATABASE": str(Path(self.temp_dir.name) / "store.sqlite3"),
            "SECRET_KEY": "msp01-test-secret",
        })

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_dynamb_is_normalized_and_persisted_as_history(self):
        payload = {
            "timestamp": 1_769_000_000_000,
            "transmitterId": "C3:00:00:45:5D:A6",
            "temperature": 5.2,
            "relativeHumidity": 48.5,
            "illuminance": 12.0,
            "isMotionDetected": [False, True],
            "batteryPercentage": 91,
            "rssi": -61,
        }
        with self.app.app_context():
            stored = ingest_dynamb(json.dumps(payload))
            latest = dict(get_latest_reading("c30000455da6"))
            history = [dict(row) for row in get_history("c30000455da6")]

        self.assertEqual(stored["device"], "c30000455da6")
        self.assertEqual(stored["motion"], 1)
        self.assertEqual(latest["temperature"], 5.2)
        self.assertEqual(latest["humidity"], 48.5)
        self.assertEqual(latest["light"], 12.0)
        self.assertEqual(latest["motion"], 1)
        self.assertEqual(len(history), 1)

    def test_partial_dynamb_carries_forward_latest_snapshot(self):
        with self.app.app_context():
            ingest_dynamb({
                "timestamp": 1_769_000_000_000,
                "device": "c30000455da6",
                "temperature": 4.0,
                "relativeHumidity": 40.0,
                "illuminance": 8.0,
                "isMotionDetected": [False],
            })
            ingest_dynamb({
                "timestamp": 1_769_000_001_000,
                "device": "c30000455da6",
                "isMotionDetected": [True],
            })
            latest = dict(get_latest_reading("c30000455da6"))
            history = get_history("c30000455da6")

        self.assertEqual(len(history), 2)
        self.assertEqual(latest["temperature"], 4.0)
        self.assertEqual(latest["humidity"], 40.0)
        self.assertEqual(latest["light"], 8.0)
        self.assertEqual(latest["motion"], 1)

    def test_invalid_payloads_are_rejected_without_rows(self):
        invalid_payloads = [
            "not json",
            {"timestamp": 1_769_000_000_000, "device": "not-an-address", "temperature": 4},
            {"timestamp": 1_769_000_000_000, "device": "c30000455da6", "relativeHumidity": 101},
            {"timestamp": 1_769_000_000_000, "device": "c30000455da6", "illuminance": -1},
            {"timestamp": 1_769_000_000_000, "device": "c30000455da6", "isMotionDetected": [1]},
            {"timestamp": 1_769_000_000_000, "device": "c30000455da6"},
        ]
        with self.app.app_context():
            for payload in invalid_payloads:
                with self.assertRaises(ValueError):
                    parse_dynamb(payload)
            self.assertIsNone(get_latest_reading("c30000455da6"))

    def test_pareto_dynamb_path_keeps_latest_and_history(self):
        from pareto import TOPIC, latest_fridge, store_message

        payload = {
            "timestamp": 1_769_000_000_000,
            "temperature": 6.1,
            "relativeHumidity": 51.0,
            "illuminance": 22,
            "isMotionDetected": [True],
        }
        with self.app.app_context():
            store_message(TOPIC, json.dumps(payload))
            latest = latest_fridge()
            history = get_history()

        self.assertEqual(latest["temperature"], 6.1)
        self.assertEqual(latest["humidity"], 51.0)
        self.assertEqual(latest["illuminance"], 22.0)
        self.assertTrue(latest["motion"])
        self.assertEqual(len(history), 1)

    def test_direct_mqtt_listener_ingests_without_hardware(self):
        from mqtt import on_msp01_message

        message = SimpleNamespace(
            topic="msp01/dynamb",
            payload=json.dumps({
                "timestamp": 1_769_000_000_000,
                "transmitterId": "c30000455da6",
                "temperature": 7.0,
                "relativeHumidity": 55.0,
                "illuminance": 30,
                "isMotionDetected": [False],
            }).encode("utf-8"),
        )
        client = SimpleNamespace(_flask_app=self.app)
        stored = on_msp01_message(client, None, message)

        self.assertEqual(stored["temperature"], 7.0)
        with self.app.app_context():
            self.assertEqual(len(get_history("c30000455da6")), 1)


if __name__ == "__main__":
    unittest.main()
