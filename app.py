import json
import re
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import sqlite3

from db import create_customer, initialize_database, list_customers

ROOT = Path(__file__).parent
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StoreRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/customers":
            self.send_json({"customers": list_customers()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/customers":
            self.send_json({"error": "Endpoint not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            data = self.read_json()
            first_name = str(data.get("firstName", "")).strip()
            last_name = str(data.get("lastName", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            if not first_name or not last_name or not EMAIL_PATTERN.match(email):
                self.send_json(
                    {"error": "First name, last name, and a valid email are required"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            customer = create_customer(first_name, last_name, email)
        except json.JSONDecodeError:
            self.send_json({"error": "Request body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
            return
        except sqlite3.IntegrityError:
            self.send_json({"error": "A customer with that email already exists"}, HTTPStatus.CONFLICT)
            return

        self.send_json({"customer": customer}, HTTPStatus.CREATED)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer(("0.0.0.0", 8000), StoreRequestHandler)
    print("Smart Store running at http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()