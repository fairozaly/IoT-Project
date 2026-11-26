// Optional Minew MSP01 BLE -> MQTT bridge.
// The Flask app does not start this process automatically; run it on the Pi
// after installing the packages in package.json. The Python ingest contract is
// hardware-independent and is exercised by tests with a JSON dynamb payload.

const Barnowl = require("barnowl");
const BarnowlHci = require("barnowl-hci");
const advlib = require("advlib");
const mqtt = require("mqtt");

const MQTT_HOST = process.env.MQTT_HOST || "127.0.0.1";
const MQTT_PORT = process.env.MQTT_PORT || "1883";
const TOPIC = (process.env.MSP01_TOPIC || "msp01").replace(/\/+$/, "");
let chosen = (process.env.MSP01_ADDRESS || "").replace(/:/g, "").toLowerCase();

const processors = [{
  processor: require("advlib-ble"),
  libraries: [require("advlib-ble-services"), require("advlib-ble-manufacturers")],
  options: { ignoreProtocolOverhead: true },
}];

const client = mqtt.connect(`mqtt://${MQTT_HOST}:${MQTT_PORT}`, {
  username: process.env.MQTT_USERNAME || undefined,
  password: process.env.MQTT_PASSWORD || undefined,
  queueQoSZero: false,
});
client.on("connect", () => console.log(`MSP01: connected to MQTT at ${MQTT_HOST}`));
client.on("error", (error) => console.log(`MSP01: MQTT problem: ${error.message}`));

function isMinew(data) {
  return typeof data.uri === "string" && data.uri.includes("Minew");
}

function publishDynamb(transmitterId, data, rssi) {
  const event = { timestamp: Date.now(), transmitterId };
  for (const key of ["temperature", "relativeHumidity", "batteryPercentage", "illuminance", "luminousFlux", "isMotionDetected"]) {
    if (data[key] !== undefined) event[key] = data[key];
  }
  if (rssi !== undefined) event.rssi = rssi;
  client.publish(`${TOPIC}/dynamb`, JSON.stringify(event));
}

const barnowl = new Barnowl({ enableMixing: true });
try {
  barnowl.addListener(BarnowlHci, {}, BarnowlHci.SocketListener, {});
} catch (error) {
  console.error(`MSP01: cannot use Bluetooth: ${error.message}`);
  process.exitCode = 1;
}

barnowl.on("raddec", (raddec) => {
  if (!raddec.packets || !raddec.packets.length) return;
  const data = advlib.process(raddec.packets, processors);
  if (!isMinew(data)) return;
  const transmitterId = String(raddec.transmitterId || "").replace(/:/g, "").toLowerCase();
  if (!chosen) chosen = transmitterId;
  if (transmitterId !== chosen) return;
  const signature = raddec.rssiSignature && raddec.rssiSignature[0];
  publishDynamb(transmitterId, data, signature && signature.rssi);
});

console.log(`MSP01: listening for ${chosen || "any Minew sensor"} on ${TOPIC}/dynamb`);
