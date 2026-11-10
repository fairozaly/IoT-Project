#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

#include <string>
#include <unordered_map>

#define FRIDGE_1_PIN 12
#define FRIDGE_NAME "Frig2"

#define MQTT_SERVER_ADDRESS "10.0.0.237"
#define MQTT_SERVER_PORT 1883

#define NETWORK_SSID ""
#define NETWORK_PASSWORD ""

class state_t {
public:
  	state_t() : mqtt_client(wifi_client) {}

	bool add_fridge(const char* label, int pin) {
		auto [iter, inserted] = fridges.try_emplace(label, pin, DHT11);

		if (inserted)
			iter->second.begin(); // setup DHT element

		return inserted;
	}

	DHT* get_fridge(const char* label) {
		if (auto iter = fridges.find(label); iter != fridges.end())
			return &iter->second;

		return nullptr;
	}

	void setup_wifi() {
		Serial.printf("Connecting to: %s...\n", NETWORK_SSID);

		WiFi.begin(NETWORK_SSID, NETWORK_PASSWORD);

		while (WiFi.status() != WL_CONNECTED) {
			delay(500);
		}

		Serial.println("WiFi connected");
		Serial.printf("IP address: %s\n", WiFi.localIP().toString().c_str());
	}

	void setup_mqtt() {
		mqtt_client.setServer(MQTT_SERVER_ADDRESS, MQTT_SERVER_PORT);
	}

	bool is_connected_mqtt() {
		return mqtt_client.connected();
	}

	void loop_mqtt() {
		mqtt_client.loop();
	}

	void reconnect_mqtt() {
		while (!mqtt_client.connected()) {
			Serial.println("Attempting MQTT connection...");

			if (mqtt_client.connect("ESP32")) {
				Serial.println("Connected");
			} else {
				Serial.println("Failed to connect to MQTT, trying again in 5 seconds");
				delay(5000);
			}
		}
	}

	void publish(const char* topic, const char* message) {
		mqtt_client.publish(topic, message);
	}

private:
	std::unordered_map<std::string, DHT> fridges;

	WiFiClient wifi_client;
	PubSubClient mqtt_client;
};

inline state_t state;

void setup() {
  	Serial.begin(115200);

    state.add_fridge(FRIDGE_NAME, FRIDGE_1_PIN);

    state.setup_wifi();
    state.setup_mqtt();
}

void loop() {
	if (!state.is_connected_mqtt())
		state.reconnect_mqtt();

	state.loop_mqtt();

	DHT* fridge1 = state.get_fridge(FRIDGE_NAME);

	float humidity = fridge1->readHumidity();
	float temperature = fridge1->readTemperature();

	Serial.printf("Temperature: %.1f\tHumidity: %.1f\n", temperature, humidity);

	std::string payload = std::to_string(humidity) + "," + std::to_string(temperature);
	state.publish("SmartHome/" FRIDGE_NAME, payload.c_str());

	delay(2000);
}
