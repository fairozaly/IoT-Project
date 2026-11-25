import os
import threading
import time

import serial

PORT = os.getenv("RFID_PORT", "/dev/ttyUSB0")
BAUD = int(os.getenv("RFID_BAUD", "115200"))
TAG_TTL = float(os.getenv("RFID_TAG_TTL", "3"))
READ_TAGS = bytes([0x04, 0xFF, 0x01, 0x1B, 0xB4])

connection = None
buffer = b""
lock = threading.Lock()

_state_lock = threading.Lock()
_stop_event = threading.Event()
_thread = None
_tags = {}
_connected = False
_last_error = None


def parse_epcs(data):
    epcs = []
    position = 0

    while True:
        position = data.find(b"\xcf", position)
        if position == -1:
            return epcs, b""
        if position + 5 > len(data):
            return epcs, data[position:]

        length = data[position + 4]
        end = position + 5 + length + 2
        if end > len(data):
            return epcs, data[position:]

        payload = data[position + 5:position + 5 + length]
        if length >= 8 and payload[0] == 0:
            epc_length = payload[5]
            epc = payload[6:6 + epc_length]
            if epc_length > 0 and epc_length <= 12 and len(epc) == epc_length:
                epcs.append(epc.hex().upper())
        position = end


def scan():
    global connection, buffer

    with lock:
        try:
            if connection is None or not connection.is_open:
                connection = serial.Serial(
                    PORT, BAUD, timeout=0.35, write_timeout=0.5, exclusive=True
                )
                buffer = b""

            connection.write(READ_TAGS)
            buffer += connection.read(4096)
            epcs, buffer = parse_epcs(buffer)

            tags = []
            for epc in epcs:
                if epc not in tags:
                    tags.append(epc)
            return tags
        except (serial.SerialException, OSError):
            if connection is not None:
                connection.close()
            connection = None
            buffer = b""
            raise


def _prune_tags(now=None):
    now = time.monotonic() if now is None else now
    stale = [epc for epc, seen in _tags.items() if now - seen > TAG_TTL]
    for epc in stale:
        del _tags[epc]


def _worker():
    global _connected, _last_error

    while not _stop_event.is_set():
        try:
            epcs = scan()
        except (serial.SerialException, OSError) as error:
            _connected = False
            _last_error = str(error) or "RFID reader unavailable."
            _stop_event.wait(1.0)
            continue

        now = time.monotonic()
        _connected = True
        _last_error = None
        for epc in epcs:
            _tags[epc] = now
        _prune_tags(now)
        _stop_event.wait(0.15)


def ensure_started():
    global _thread

    with _state_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_worker, name="rfid-reader", daemon=True)
        _thread.start()


def start():
    ensure_started()


def stop():
    global _thread, connection, buffer, _connected, _last_error

    _stop_event.set()
    with _state_lock:
        thread = _thread
        _thread = None
        if thread is not None:
            thread.join(timeout=2.0)
    with lock:
        if connection is not None:
            connection.close()
        connection = None
        buffer = b""
    _tags.clear()
    _connected = False
    _last_error = None


def get_tags():
    now = time.monotonic()
    _prune_tags(now)
    return [
        epc for epc, _ in sorted(_tags.items(), key=lambda item: item[1], reverse=True)
    ]


def is_connected():
    return _connected


def get_last_error():
    return _last_error


if __name__ == "__main__":
    ensure_started()
    print(f"Reading {PORT} at {BAUD}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop()
