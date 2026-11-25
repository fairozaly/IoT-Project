# Smart Store

```sh
pip install -r requirements.txt
python app.py
```

## Pareto Anywhere Bluetooth sensors

1. Follow the [reelyActive Raspberry Pi guide](https://reelyactive.github.io/diy/pareto-anywhere-pi/) to install Pareto Anywhere and `barnowl-hci`. Start Pareto Anywhere with `npm start` and run `npm run forwarder` from the `barnowl-hci` directory to capture Bluetooth advertising packets.
2. Run Mosquitto on the broker shared by Pareto Anywhere and Smart Store. Both default to localhost on port 1883. If the broker is on another host, set `MQTT_HOST` and `MQTT_PORT` in Smart Store's `.env` and configure [Pareto Anywhere's MQTT publisher](https://github.com/reelyactive/barnacles-mqtt#options) to use the same broker and its default topic prefix, `paretoanywhere`.
3. Sign in to Smart Store and open **Storage Overview → Fridge 3**. The page refreshes every three seconds and shows the most recent value and timestamp for each measurement the device reports.

To confirm Pareto Anywhere is decoding telemetry, subscribe to its [`dynamb` topics](https://reelyactive.github.io/diy/cheatsheet/#dynamb) on the shared broker:

```sh
mosquitto_sub -v -t 'paretoanywhere/devices/c30000455da7/3/dynamb'
```

Fridge 3 uses Bluetooth sensor `c30000455da7/3` and reports temperature, humidity, motion, and battery. The ESP32 refrigerator readings drive the fan approval workflow.
