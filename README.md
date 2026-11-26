# Smart Store

```sh
pip install -r requirements.txt
python app.py
```

## Smoke tests

Run the dependency-free application smoke suite from the project root:

```sh
python3 -m unittest discover -s tests -v
```

The suite creates a temporary SQLite database for each test and disables
MQTT, RFID, email, Bluetooth, and hardware services. The production database
path remains `smart_store.db`; tests override it through the Flask `DATABASE`
configuration value.

## Pareto Anywhere Bluetooth sensors

1. Follow the [reelyActive Raspberry Pi guide](https://reelyactive.github.io/diy/pareto-anywhere-pi/) to install Pareto Anywhere and `barnowl-hci`. Start Pareto Anywhere with `npm start` and run `npm run forwarder` from the `barnowl-hci` directory to capture Bluetooth advertising packets.
2. Run Mosquitto on the broker shared by Pareto Anywhere and Smart Store. Both default to localhost on port 1883. If the broker is on another host, set `MQTT_HOST` and `MQTT_PORT` in Smart Store's `.env` and configure [Pareto Anywhere's MQTT publisher](https://github.com/reelyactive/barnacles-mqtt#options) to use the same broker and its default topic prefix, `paretoanywhere`.
3. Sign in to Smart Store and open **Storage Overview → Fridge 3**. The page refreshes every three seconds and shows the most recent value and timestamp for each measurement the device reports.

To confirm Pareto Anywhere is decoding telemetry, subscribe to its [`dynamb` topics](https://reelyactive.github.io/diy/cheatsheet/#dynamb) on the shared broker:

```sh
mosquitto_sub -v -t 'paretoanywhere/devices/c30000455da7/3/dynamb'
```

Fridge 3 uses Bluetooth sensor `c30000455da7/3` and reports temperature, humidity, motion, light, and battery. Set `FRIDGE3_BLE_DEVICE` in `.env` to the MSP01 device signature shown in the MQTT topic if it differs from the default. Enable the HT, PIR, and PS Sensor advertising slots to send temperature and humidity, motion, and illuminance. [Minew MSP01 configuration guide](https://reelyactive.github.io/diy/minew-msp01-config/). The ESP32 refrigerator readings drive the fan approval workflow.

## Catalog photo credits

Product packshots were cropped, resized, and padded for the inventory tiles.

| Product | Photo source |
| --- | --- |
| Pepsi | [Gem's Grocery](https://gemsgrocery.ca/products/pepsi-classic-355ml) |
| Evian | [Danone Foodservice](https://foodservice.danone.es/product/evian-50cl/) |
| KitKat | [Real Canadian Superstore](https://www.realcanadiansuperstore.ca/en/food/snacks-chips-candy/candy-chocolate/chocolate/c/29915) |
| Coca-Cola | [Lowe's](https://www.lowes.com/pd/Coca-Cola-Coca-Cola-Bottle-20-fl-oz/5014075097) |
| Red Bull | [J L Brooks](https://jlbrooks.co.uk/redbull-can-250ml-x-24.html) |
| Hershey's Milk Chocolate | [Open Food Facts contributors](https://world.openfoodfacts.org/product/0034000002405) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| M&M's Peanut | [Martin's](https://martinsfoods.com/groceries/candy-chocolate/chocolate-candy/single-serve-chocolate-candy/mms-peanut-milk-chocolate-candy-174-oz-bag.html) |
| Pringles Original | [Open Food Facts contributors](https://world.openfoodfacts.org/product/0038000138416) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
