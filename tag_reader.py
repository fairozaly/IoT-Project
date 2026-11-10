import os
import threading
import time

import serial

PORT = os.getenv("RFID_PORT", "/dev/ttyUSB0")
BAUD = int(os.getenv("RFID_BAUD", "115200"))
READ_TAGS = bytes([0x04, 0xFF, 0x01, 0x1B, 0xB4])

connection = None
buffer = b""
lock = threading.Lock()


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


if __name__ == "__main__":
    print(f"Reading {PORT} at {BAUD}")
    try:
        while True:
            for epc in scan():
                print(epc, flush=True)
            time.sleep(0.15)
    except KeyboardInterrupt:
        if connection is not None:
            connection.close()
