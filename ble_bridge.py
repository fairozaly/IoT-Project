import asyncio
import json
import os
import urllib.error
import urllib.request
from bleak import BleakScanner

ENDPOINT = os.getenv('MINEW_INGEST_URL', 'http://127.0.0.1:5000/api/minew/ingest')
TOKEN = os.getenv('MINEW_INGEST_TOKEN', '')
DEVICE = os.getenv('MINEW_DEVICE', '').strip().upper()
QUEUE = asyncio.Queue(maxsize=100)
LAST_DISCOVERED = set()


def decode_minew(data):
    """Decode frames specified by reelyActive's advlib-ble-services Minew decoder.
    Service UUID: 0xFFE1; A1 frame. Unknown frames are ignored.
    """
    if len(data) < 3 or data[0] != 0xA1:
        return None
    frame, battery = data[1], data[2]
    values = {'battery_percentage': battery}
    if frame == 0x01 and len(data) == 13:  # HT (signed 8.8)
        values['temperature'] = int.from_bytes(data[3:4], 'big', signed=True) + data[4] / 256
        values['humidity'] = int.from_bytes(data[5:6], 'big', signed=True) + data[6] / 256
    elif frame == 0x05 and len(data) == 11:  # PS / lux
        values['illuminance'] = int.from_bytes(data[3:5], 'big')
    elif frame == 0x11 and len(data) == 11:  # PIR
        values['motion_detected'] = bool(int.from_bytes(data[3:5], 'big') & 1)
    else:
        return None
    return values


def post_data(payload):
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'X-Minew-Token': TOKEN},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        return response.status


async def post_worker():
    while True:
        payload = await QUEUE.get()
        try:
            status = await asyncio.to_thread(post_data, payload)
            print(f'Forwarded ({status}): {payload}', flush=True)
        except Exception as exc:
            print(f'Failed to forward: {exc}', flush=True)
        finally:
            QUEUE.task_done()


def callback(device, advertisement):
    address = device.address.upper()
    for uuid, data in advertisement.service_data.items():
        # Bleak on Linux usually gives a 128-bit representation of 0xFFE1.
        if uuid.lower().replace('-', '') not in ('ffe1', '0000ffe100001000800000805f9b34fb'):
            continue
        values = decode_minew(bytes(data))
        if not values:
            continue
        if not DEVICE:
            if address not in LAST_DISCOVERED:
                LAST_DISCOVERED.add(address)
                print(f'Minew candidate: {address} (name={device.name!r}) values={values}', flush=True)
            continue
        if address != DEVICE:
            continue
        values['device_id'] = address
        try:
            QUEUE.put_nowait(values)
        except asyncio.QueueFull:
            print('BLE queue full, dropping advertisement', flush=True)


async def main():
    if DEVICE and not TOKEN:
        raise SystemExit('Set MINEW_INGEST_TOKEN first; see the integration README.')
    if DEVICE:
        print(f'Monitoring {DEVICE}, forwarding to {ENDPOINT}', flush=True)
        worker = asyncio.create_task(post_worker())
    else:
        print('Discovery mode: looking for Minew 0xFFE1 service frames. Set MINEW_DEVICE to select one.', flush=True)
        worker = None
    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await scanner.stop()
        if worker:
            worker.cancel()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nStopped.')
