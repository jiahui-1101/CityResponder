#include <Arduino.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define CITYRESPONDER_WIFI_SSID "YOUR_WIFI_SSID"
#define CITYRESPONDER_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define CITYRESPONDER_MQTT_HOST "192.168.1.33"
#define CITYRESPONDER_MQTT_PORT 1883
#endif

namespace {
constexpr char NODE_ID[] = "SN1";
constexpr uint8_t MQ2_AO_PIN = 34;
constexpr uint8_t DHT_DATA_PIN = 4;
constexpr uint8_t IR1_PIN = 32;
constexpr uint8_t IR2_PIN = 33;
constexpr uint8_t BUTTON_PIN = 27;
constexpr unsigned long PUBLISH_INTERVAL_MS = 1000;
constexpr unsigned long DHT_INTERVAL_MS = 2000;
constexpr unsigned long RETRY_INTERVAL_MS = 5000;
constexpr unsigned long WIFI_ATTEMPT_TIMEOUT_MS = 15000;
constexpr char NTP_SERVER[] = "pool.ntp.org";

DHT dht(DHT_DATA_PIN, DHT22);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
unsigned long lastPublishMs = 0;
unsigned long lastDhtReadMs = 0;
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;
bool wifiAttemptActive = false;
bool wifiConnectedReported = false;
float lastTemperatureC = NAN;
float lastHumidityPct = NAN;
bool lastDhtOk = false;
bool haveDhtRead = false;

bool credentialsConfigured() {
  return String(CITYRESPONDER_WIFI_SSID) != "YOUR_WIFI_SSID" &&
         String(CITYRESPONDER_WIFI_PASSWORD) != "YOUR_WIFI_PASSWORD" &&
         String(CITYRESPONDER_MQTT_HOST) != "YOUR_MQTT_HOST";
}

const char *wifiStatusName(wl_status_t status) {
  switch (status) {
    case WL_NO_SHIELD: return "NO_SHIELD";
    case WL_IDLE_STATUS: return "IDLE";
    case WL_NO_SSID_AVAIL: return "NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED: return "SCAN_COMPLETED";
    case WL_CONNECTED: return "CONNECTED";
    case WL_CONNECT_FAILED: return "CONNECT_FAILED";
    case WL_CONNECTION_LOST: return "CONNECTION_LOST";
    case WL_DISCONNECTED: return "DISCONNECTED";
    default: return "UNKNOWN";
  }
}

const char *encryptionName(wifi_auth_mode_t mode) {
  switch (mode) {
    case WIFI_AUTH_OPEN: return "OPEN";
    case WIFI_AUTH_WEP: return "WEP";
    case WIFI_AUTH_WPA_PSK: return "WPA_PSK";
    case WIFI_AUTH_WPA2_PSK: return "WPA2_PSK";
    case WIFI_AUTH_WPA_WPA2_PSK: return "WPA_WPA2_PSK";
    case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2_ENTERPRISE";
    case WIFI_AUTH_WPA3_PSK: return "WPA3_PSK";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2_WPA3_PSK";
    default: return "UNKNOWN";
  }
}

void reportWifiScan() {
  Serial.println("SN1 Wi-Fi scan starting");
  const int count = WiFi.scanNetworks(false, true);
  bool found = false;
  int configuredRssi = 0;
  const char *configuredEncryption = "UNKNOWN";
  for (int i = 0; i < count; ++i) {
    if (WiFi.SSID(i) == String(CITYRESPONDER_WIFI_SSID)) {
      found = true;
      configuredRssi = WiFi.RSSI(i);
      configuredEncryption = encryptionName(WiFi.encryptionType(i));
      break;
    }
  }
  Serial.printf(
      "SN1 Wi-Fi scan configured_ssid_found=%s nearby_count=%d rssi=%d encryption=%s\n",
      found ? "YES" : "NO",
      count,
      configuredRssi,
      configuredEncryption);
  WiFi.scanDelete();
}

bool timestampIso8601(char *buffer, size_t length) {
  const time_t now = time(nullptr);
  if (now < 1700000000) {
    return false;
  }
  struct tm utc;
  gmtime_r(&now, &utc);
  return strftime(buffer, length, "%Y-%m-%dT%H:%M:%SZ", &utc) > 0;
}

void readDhtIfDue(unsigned long nowMs) {
  if (haveDhtRead && nowMs - lastDhtReadMs < DHT_INTERVAL_MS) {
    return;
  }
  lastDhtReadMs = nowMs;
  const float temperatureC = dht.readTemperature();
  const float humidityPct = dht.readHumidity();
  lastDhtOk = !isnan(temperatureC) && !isnan(humidityPct);
  lastTemperatureC = lastDhtOk ? temperatureC : NAN;
  lastHumidityPct = lastDhtOk ? humidityPct : NAN;
  haveDhtRead = true;
}

bool publishJson(const char *topic, const String &payload) {
  if (!mqttClient.connected()) {
    return false;
  }
  // The existing sensor contract does not define retained messages or publisher QoS.
  // PubSubClient publishes non-retained QoS 0 sensor events.
  return mqttClient.publish(topic, payload.c_str(), false);
}

String basePayload(const char *sensorType, const char *timestamp) {
  String payload = "{\"sensor_type\":\"";
  payload += sensorType;
  payload += "\",\"timestamp\":\"";
  payload += timestamp;
  payload += "\",\"node_id\":\"";
  payload += NODE_ID;
  payload += "\"";
  return payload;
}

void publishSensors(unsigned long nowMs) {
  char timestamp[25] = {};
  if (!timestampIso8601(timestamp, sizeof(timestamp))) {
    Serial.println("SN1 MQTT timestamp unavailable; sensor events skipped");
    return;
  }

  const int mq2Raw = analogRead(MQ2_AO_PIN);
  String mq2 = basePayload("MQ2", timestamp);
  mq2 += ",\"value\":";
  mq2 += mq2Raw;
  mq2 += ",\"unit\":\"raw\"}";
  publishJson("city/sensors/mq2", mq2);

  if (lastDhtOk) {
    String dhtPayload = basePayload("DHT22", timestamp);
    dhtPayload += ",\"value\":";
    dhtPayload += String(lastTemperatureC, 1);
    dhtPayload += ",\"unit\":\"C\",\"humidity\":";
    dhtPayload += String(lastHumidityPct, 1);
    dhtPayload += ",\"dht_ok\":true}";
    publishJson("city/sensors/dht22", dhtPayload);
  } else {
    Serial.println("SN1 DHT22 read invalid; no fabricated DHT22 event published");
  }

  const bool ir1Blocked = digitalRead(IR1_PIN) == LOW;
  const bool ir2Blocked = digitalRead(IR2_PIN) == LOW;
  const bool buttonPressed = digitalRead(BUTTON_PIN) == LOW;

  String ir1 = basePayload("IR_A", timestamp);
  ir1 += ",\"value\":";
  ir1 += (ir1Blocked ? "true" : "false");
  ir1 += ",\"unit\":\"blocked\",\"raw\":\"";
  ir1 += (ir1Blocked ? "LOW" : "HIGH");
  ir1 += "\"}";
  publishJson("city/sensors/ir_a", ir1);

  String ir2 = basePayload("IR_B", timestamp);
  ir2 += ",\"value\":";
  ir2 += (ir2Blocked ? "true" : "false");
  ir2 += ",\"unit\":\"blocked\",\"raw\":\"";
  ir2 += (ir2Blocked ? "LOW" : "HIGH");
  ir2 += "\"}";
  publishJson("city/sensors/ir_b", ir2);

  String button = basePayload("BUTTON", timestamp);
  button += ",\"value\":";
  button += (buttonPressed ? "true" : "false");
  button += ",\"raw\":\"";
  button += (buttonPressed ? "LOW" : "HIGH");
  button += "\"}";
  publishJson("city/sensors/button", button);

  Serial.printf(
      "SN1 MQTT uptime=%lu mq2_raw=%d dht_ok=%d ir1=%s ir2=%s button=%s mqtt=%s\n",
      nowMs,
      mq2Raw,
      lastDhtOk ? 1 : 0,
      ir1Blocked ? "BLOCKED" : "CLEAR",
      ir2Blocked ? "BLOCKED" : "CLEAR",
      buttonPressed ? "PRESSED" : "UNPRESSED",
      mqttClient.connected() ? "CONNECTED" : "DISCONNECTED");
}

void maintainWifi(unsigned long nowMs) {
  const wl_status_t status = WiFi.status();
  if (status == WL_CONNECTED) {
    if (!wifiConnectedReported) {
      Serial.printf("SN1 Wi-Fi connected status=%d(%s) ip=%s rssi=%d\n", status, wifiStatusName(status), WiFi.localIP().toString().c_str(), WiFi.RSSI());
      wifiConnectedReported = true;
    }
    wifiAttemptActive = false;
    return;
  }
  wifiConnectedReported = false;
  if (wifiAttemptActive && nowMs - lastWifiAttemptMs >= WIFI_ATTEMPT_TIMEOUT_MS) {
    Serial.printf("SN1 Wi-Fi attempt timeout status=%d(%s)\n", status, wifiStatusName(status));
    wifiAttemptActive = false;
  }
  if (nowMs - lastWifiAttemptMs < RETRY_INTERVAL_MS) {
    return;
  }
  lastWifiAttemptMs = nowMs;
  wifiAttemptActive = true;
  Serial.printf("SN1 Wi-Fi connecting status=%d(%s) ssid=%s\n", status, wifiStatusName(status), CITYRESPONDER_WIFI_SSID);
  WiFi.begin(CITYRESPONDER_WIFI_SSID, CITYRESPONDER_WIFI_PASSWORD);
}

void maintainMqtt(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected() || nowMs - lastMqttAttemptMs < RETRY_INTERVAL_MS) {
    return;
  }
  lastMqttAttemptMs = nowMs;
  Serial.println("SN1 MQTT connecting");
  if (mqttClient.connect(NODE_ID)) {
    Serial.println("SN1 MQTT connected");
  } else {
    Serial.printf("SN1 MQTT connect failed state=%d\n", mqttClient.state());
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(MQ2_AO_PIN, INPUT);
  pinMode(DHT_DATA_PIN, INPUT);
  pinMode(IR1_PIN, INPUT);
  pinMode(IR2_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  analogReadResolution(12);
  dht.begin();

  mqttClient.setServer(CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  WiFi.mode(WIFI_STA);
  configTime(0, 0, NTP_SERVER);
  Serial.printf("SN1 MQTT node=%s broker=%s:%d\n", NODE_ID, CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  if (!credentialsConfigured()) {
    Serial.println("SN1 MQTT credentials are placeholders; provide local include/secrets.h before upload");
  } else {
    reportWifiScan();
  }
}

void loop() {
  const unsigned long nowMs = millis();
  readDhtIfDue(nowMs);
  if (credentialsConfigured()) {
    maintainWifi(nowMs);
    maintainMqtt(nowMs);
    mqttClient.loop();
  }
  if (nowMs - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = nowMs;
    publishSensors(nowMs);
  }
}
