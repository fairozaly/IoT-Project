import time

import serial

PORT = "/dev/ttyUSB0"   # change to /dev/ttyACM0 if that's what shows up
BAUD = 115200            # if nothing prints, try 115200

READ_TAGS = bytes([0x04, 0xFF, 0x01, 0x1B, 0xB4])  # Chafon "inventory" command


def parse_epcs(buf):
    """Pull EPCs out of CF600 tag frames.

    Frame: CF | addr | cmd(2) | len | status | rssi(2) | ant | ? | epc_len | epc | crc(2)
    Returns (list of EPC hex strings, leftover bytes of an incomplete frame).
    """
    epcs = []
    i = 0
    while True:
        i = buf.find(0xCF, i)
        if i < 0 or i + 5 > len(buf):
            return epcs, buf[i:] if i >= 0 else b""
        length = buf[i + 4]
        end = i + 5 + length + 2
        if end > len(buf):
            return epcs, buf[i:]
        data = buf[i + 5:i + 5 + length]
        if length >= 6 and data[0] == 0x00:
            epc_len = data[5]
            epc = data[6:6 + epc_len]
            if len(epc) == epc_len:
                epcs.append(epc.hex().upper())
        i = end


ser = serial.Serial(PORT, BAUD, timeout=0.5)
print(f"Opened {PORT} at {BAUD}. Hold a tag near the reader...")

buf = b""
while True:
    ser.write(READ_TAGS)
    time.sleep(0.5)
    buf += ser.read(ser.in_waiting)
    epcs, buf = parse_epcs(buf)
    for epc in dict.fromkeys(epcs):  # drop repeat reads of the same tag
        print(epc)