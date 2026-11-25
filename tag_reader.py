import os
from pathlib import Path
import select
import threading
import time

import serial

PORT = os.getenv("RFID_PORT", "/dev/ttyUSB0")
BAUD = int(os.getenv("RFID_BAUD", "115200"))
TAG_TTL = float(os.getenv("RFID_TAG_TTL", "3"))
CHAFON_KEYBOARD = "chafon-keyboard"
CHAFON_HID = "chafon-hid"
HID_REPORT_LENGTH = 64
KEYBOARD_REPORT_LENGTH = 8
TAG_TERMINATORS = {0x28, 0x2B, 0x58}  # Enter, Tab, keypad Enter.
HEX_KEYS = dict(zip(range(0x04, 0x0A), "ABCDEF"))
HEX_KEYS.update(zip(range(0x1E, 0x28), "1234567890"))
HEX_KEYS.update(zip(range(0x59, 0x63), "1234567890"))
READ_TAGS = bytes([0x04, 0xFF, 0x01, 0x1B, 0xB4])

connection = None
buffer = b""
lock = threading.Lock()

_state_lock = threading.Lock()
_tags_lock = threading.Lock()
_stop_event = threading.Event()
_thread = None
_tags = {}
_tag_starts = {}
_suppressed_receptions = set()
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


def chafon_hid_path(protocol):
    for device in Path("/sys/class/hidraw").glob("hidraw*"):
        try:
            interface = device.resolve().parents[2]
            usb_device = interface.parent
            if (
                (usb_device / "idVendor").read_text().strip() == "0483"
                and (usb_device / "idProduct").read_text().strip() == "5750"
                and (interface / "bInterfaceProtocol").read_text().strip() == protocol
            ):
                return Path("/dev") / device.name
        except OSError:
            continue
    raise FileNotFoundError("Chafon RFID USB interface (0483:5750) was not found.")


def keyboard_epcs(report, previous_keys, text, valid):
    if len(report) != KEYBOARD_REPORT_LENGTH:
        return [], previous_keys, text, valid

    keys = set(report[2:]) - {0}
    epcs = []
    for key in report[2:]:
        if not key or key in previous_keys:
            continue
        if key in TAG_TERMINATORS:
            if valid and 2 <= len(text) <= 24 and len(text) % 2 == 0:
                epcs.append(text)
            text, valid = "", True
        elif key in HEX_KEYS and len(text) < 24:
            text += HEX_KEYS[key]
        else:
            valid = False
    return epcs, keys, text, valid


class ChafonKeyboard:
    def __init__(self):
        self.device = chafon_hid_path("01").open("rb", buffering=0)
        self.keys = set()
        self.text = ""
        self.valid = True
        self.last_report = 0.0

    def scan(self):
        deadline = time.monotonic() + 0.35
        tags = []
        while select.select([self.device], [], [], max(0, deadline - time.monotonic()))[0]:
            report = self.device.read(KEYBOARD_REPORT_LENGTH)
            if not report:
                raise OSError("The Chafon RFID keyboard disconnected.")
            now = time.monotonic()
            if now - self.last_report > 1:
                self.keys, self.text, self.valid = set(), "", True
            epcs, self.keys, self.text, self.valid = keyboard_epcs(
                report, self.keys, self.text, self.valid
            )
            self.last_report = now
            tags.extend(epcs)
            if now >= deadline:
                break
        return list(dict.fromkeys(tags))

    def close(self):
        self.device.close()


def chafon_crc(packet):
    crc = 0xFFFF
    for value in packet:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc.to_bytes(2, "big")


def chafon_report(command):
    # Linux hidraw writes require a leading zero for unnumbered reports.
    packet = bytes([0xCF, 0xFF, 0, command, 0])
    return b"\0" + (packet + chafon_crc(packet)).ljust(HID_REPORT_LENGTH, b"\0")


def chafon_frames(data):
    while data:
        start = data.find(b"\xcf")
        if start < 0:
            break
        data = data[start:]
        if len(data) < 5:
            break
        end = 7 + data[4]
        if end > len(data):
            break
        frame = data[:end]
        if chafon_crc(frame[:-2]) == frame[-2:]:
            yield int.from_bytes(frame[2:4], "big"), frame[5:-2]
            data = data[end:]
        else:
            data = data[1:]


class ChafonHid:
    def __init__(self):
        self.device = chafon_hid_path("00").open("r+b", buffering=0)
        self.device.write(chafon_report(0x72))
        try:
            for command, payload in self.read_frames(1.5):
                if command != 0x72:
                    continue
                if len(payload) == 26 and payload[:1] == b"\0" and payload[3:5] == b"\x01\x01":
                    return
                raise OSError("Set the Chafon reader to Active Mode with USB output.")
            raise OSError("The Chafon RFID reader did not answer its settings query.")
        except OSError:
            self.close()
            raise

    def read_frames(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not select.select([self.device], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            report = self.device.read(HID_REPORT_LENGTH)
            if not report:
                raise OSError("The Chafon RFID reader disconnected.")
            yield from chafon_frames(report)

    def scan(self):
        tags = []
        for command, payload in self.read_frames(0.35):
            if command == 1 and len(payload) >= 8 and payload[0] == 0:
                length = payload[5]
                if 0 < length <= 12 and len(payload) == 6 + length:
                    tags.append(payload[6:].hex().upper())
        return list(dict.fromkeys(tags))

    def close(self):
        self.device.close()


def scan():
    global connection, buffer

    with lock:
        try:
            if PORT in (CHAFON_HID, CHAFON_KEYBOARD):
                if connection is None:
                    connection = ChafonHid() if PORT == CHAFON_HID else ChafonKeyboard()
                return connection.scan()

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
        _tag_starts.pop(epc, None)
        _suppressed_receptions.discard(epc)


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
        with _tags_lock:
            _prune_tags(now)
            for epc in epcs:
                if epc not in _tags:
                    _tag_starts[epc] = time.monotonic_ns()
                _tags[epc] = now
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
    with _tags_lock:
        _tags.clear()
        _tag_starts.clear()
        _suppressed_receptions.clear()
    _connected = False
    _last_error = None


def get_tags():
    with _tags_lock:
        _prune_tags()
        return [
            epc for epc, _ in sorted(_tags.items(), key=lambda item: item[1], reverse=True)
        ]


def receive_scans(after):
    with _tags_lock:
        _prune_tags()
        cursor = time.monotonic_ns()
        epcs = [] if after is None else [
            epc for epc, first_seen in _tag_starts.items()
            if first_seen > after and epc not in _suppressed_receptions
        ]
        return str(cursor), epcs


def suppress_reception(epc):
    with _tags_lock:
        _prune_tags()
        if epc in _tags:
            _suppressed_receptions.add(epc)


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
