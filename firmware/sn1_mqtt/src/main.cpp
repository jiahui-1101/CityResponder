#include <Arduino.h>
#include <DHT.h>
#include <esp_system.h>
#include <esp_sntp.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <sys/time.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing ignored include/secrets.h; the SN1 network firmware requires explicit credentials"
#endif

#if !defined(CITYRESPONDER_WIFI_SSID) || !defined(CITYRESPONDER_WIFI_PASSWORD) || \
    !defined(CITYRESPONDER_MQTT_HOST) || !defined(CITYRESPONDER_MQTT_PORT) || \
    !defined(CITYRESPONDER_MQTT_USERNAME) || !defined(CITYRESPONDER_MQTT_PASSWORD)
#error "SN1 secrets.h must define Wi-Fi SSID/password and authenticated MQTT host/port/username/password"
#endif

#ifndef CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY
#define CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY 0
#endif
#ifndef CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY
#define CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY 0
#endif
#if (CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY != 0) && \
    (CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY != 1)
#error "CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY must be 0 or 1"
#endif
#if (CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY != 0) && \
    (CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY != 1)
#error "CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY must be 0 or 1"
#endif

namespace {
constexpr char NODE_ID[] = "SN1";
constexpr char FIRMWARE_VERSION[] = "sn1-mqtt/1.2.0";
constexpr char PROTOCOL_VERSION[] = "1.1";
constexpr uint8_t MQ2_AO_PIN = 34;
constexpr uint8_t DHT_DATA_PIN = 4;
constexpr uint8_t IR1_PIN = 32;
constexpr uint8_t IR2_PIN = 33;
constexpr uint8_t BUTTON_PIN = 27;
constexpr unsigned long PUBLISH_INTERVAL_MS = 1000;
constexpr unsigned long DHT_INTERVAL_MS = 2000;
constexpr unsigned long RETRY_INTERVAL_MS = 5000;
constexpr unsigned long WIFI_ATTEMPT_TIMEOUT_MS = 15000;
constexpr unsigned long NTP_RETRY_INTERVAL_MS = 60000;
constexpr unsigned long DIAGNOSTIC_INTERVAL_MS = 5000;
constexpr time_t MIN_VALID_EPOCH = 1700000000;
constexpr char NTP_SERVER[] = "pool.ntp.org";

DHT dht(DHT_DATA_PIN, DHT22);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
unsigned long lastPublishMs = 0;
unsigned long lastDhtReadMs = 0;
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;
unsigned long lastNtpAttemptMs = 0;
unsigned long lastTimestampWarningMs = 0;
unsigned long lastPublishFailureLogMs = 0;
bool wifiAttemptActive = false;
bool wifiConnectedReported = false;
bool ntpConfigured = false;
bool ntpTimeSynced = false;
bool timeSyncReported = false;
bool timestampWarningReported = false;
bool publishFailureLogReported = false;
bool dhtFailureLogReported = false;
unsigned long lastDhtFailureLogMs = 0;
uint32_t bootId = 0;
uint32_t messageSequence = 0;
float lastTemperatureC = NAN;
float lastHumidityPct = NAN;
bool lastDhtOk = false;
bool haveDhtRead = false;
bool dhtReadingPending = false;

bool credentialsConfigured() {
  const bool hasUsername = String(CITYRESPONDER_MQTT_USERNAME).length() > 0 &&
                           String(CITYRESPONDER_MQTT_USERNAME) != "YOUR_MQTT_USERNAME";
  const bool hasPassword = String(CITYRESPONDER_MQTT_PASSWORD).length() > 0 &&
                           String(CITYRESPONDER_MQTT_PASSWORD) != "YOUR_MQTT_PASSWORD";
  const String wifiSsid(CITYRESPONDER_WIFI_SSID);
  const String wifiPassword(CITYRESPONDER_WIFI_PASSWORD);
  const String mqttHost(CITYRESPONDER_MQTT_HOST);
  return hasUsername && hasPassword &&
         wifiSsid.length() > 0 && wifiSsid != "YOUR_WIFI_SSID" &&
         wifiPassword.length() > 0 && wifiPassword != "YOUR_WIFI_PASSWORD" &&
         mqttHost.length() > 0 && mqttHost != "YOUR_MQTT_HOST" &&
         CITYRESPONDER_MQTT_PORT > 0 && CITYRESPONDER_MQTT_PORT <= 65535;
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

bool timestampIso8601(char *buffer, size_t length, unsigned long ageMs = 0) {
  if (!ntpTimeSynced) {
    return false;
  }
  struct timeval timeValue = {};
  if (gettimeofday(&timeValue, nullptr) != 0) {
    return false;
  }
  const int64_t epochMs = static_cast<int64_t>(timeValue.tv_sec) * 1000 +
                          static_cast<int64_t>(timeValue.tv_usec / 1000) -
                          static_cast<int64_t>(ageMs);
  if (epochMs < static_cast<int64_t>(MIN_VALID_EPOCH) * 1000) {
    return false;
  }
  const time_t now = static_cast<time_t>(epochMs / 1000);
  const long milliseconds = static_cast<long>(epochMs % 1000);
  struct tm utc = {};
  if (gmtime_r(&now, &utc) == nullptr) {
    return false;
  }
  char wholeSeconds[20] = {};
  if (strftime(wholeSeconds, sizeof(wholeSeconds), "%Y-%m-%dT%H:%M:%S", &utc) != 19) {
    return false;
  }
  return snprintf(
             buffer,
             length,
             "%s.%03ldZ",
             wholeSeconds,
             milliseconds) == 24;
}

String nextMessageId() {
  char messageId[32] = {};
  ++messageSequence;
  snprintf(messageId, sizeof(messageId), "%08lx-%lu", static_cast<unsigned long>(bootId), static_cast<unsigned long>(messageSequence));
  return String(messageId);
}

void maintainTime(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED) {
    ntpConfigured = false;
    return;
  }

  if (!ntpTimeSynced && sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED &&
      time(nullptr) >= MIN_VALID_EPOCH) {
    ntpTimeSynced = true;
  }
  const bool retryDue = !ntpConfigured ||
                        (!ntpTimeSynced && nowMs - lastNtpAttemptMs >= NTP_RETRY_INTERVAL_MS);
  if (retryDue) {
    configTime(0, 0, NTP_SERVER);
    ntpConfigured = true;
    lastNtpAttemptMs = nowMs;
    Serial.printf("SN1 NTP sync requested server=%s\n", NTP_SERVER);
  }

  if (ntpTimeSynced && !timeSyncReported) {
    char timestamp[25] = {};
    if (timestampIso8601(timestamp, sizeof(timestamp))) {
      Serial.printf("SN1 NTP synchronized timestamp=%s\n", timestamp);
      timeSyncReported = true;
    }
  }
}

void reportTimestampUnavailable(unsigned long nowMs) {
  if (!timestampWarningReported || nowMs - lastTimestampWarningMs >= NTP_RETRY_INTERVAL_MS) {
    Serial.println("SN1 MQTT timestamp unavailable; sensor events skipped until NTP sync");
    lastTimestampWarningMs = nowMs;
    timestampWarningReported = true;
  }
}

void readDhtIfDue(unsigned long nowMs) {
  if (haveDhtRead && nowMs - lastDhtReadMs < DHT_INTERVAL_MS) {
    return;
  }
  lastDhtReadMs = nowMs;
  const float temperatureC = dht.readTemperature();
  const float humidityPct = dht.readHumidity();
  lastDhtOk = !isnan(temperatureC) && !isnan(humidityPct) &&
              temperatureC >= -40.0f && temperatureC <= 80.0f &&
              humidityPct >= 0.0f && humidityPct <= 100.0f;
  lastTemperatureC = lastDhtOk ? temperatureC : NAN;
  lastHumidityPct = lastDhtOk ? humidityPct : NAN;
  dhtReadingPending = lastDhtOk;
  if (!lastDhtOk &&
      (!dhtFailureLogReported || nowMs - lastDhtFailureLogMs >= DIAGNOSTIC_INTERVAL_MS)) {
    Serial.println("SN1 DHT22 read invalid or out of range; no measurement will be published");
    lastDhtFailureLogMs = nowMs;
    dhtFailureLogReported = true;
  }
  if (lastDhtOk && dhtFailureLogReported) {
    Serial.println("SN1 DHT22 read recovered");
    dhtFailureLogReported = false;
  }
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

void reportPublishFailure(const char *topic, unsigned long nowMs) {
  if (!publishFailureLogReported || nowMs - lastPublishFailureLogMs >= DIAGNOSTIC_INTERVAL_MS) {
    Serial.printf(
        "SN1 MQTT publish failed topic=%s mqtt=%s\n",
        topic,
        mqttClient.connected() ? "CONNECTED" : "DISCONNECTED");
    lastPublishFailureLogMs = nowMs;
    publishFailureLogReported = true;
  }
}

void publishSensorEvent(const char *topic, const String &payload, unsigned long nowMs) {
  if (!publishJson(topic, payload)) {
    reportPublishFailure(topic, nowMs);
  }
}

String basePayload(const char *sensorType, const char *timestamp, const String &messageId) {
  String payload = "{\"sensor_type\":\"";
  payload += sensorType;
  payload += "\",\"firmware_version\":\"";
  payload += FIRMWARE_VERSION;
  payload += "\",\"protocol_version\":\"";
  payload += PROTOCOL_VERSION;
  payload += "\",\"message_id\":\"";
  payload += messageId;
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
    reportTimestampUnavailable(nowMs);
    return;
  }

#if CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY
  const int mq2Raw = analogRead(MQ2_AO_PIN);
  String mq2 = basePayload("MQ2", timestamp, nextMessageId());
  mq2 += ",\"value\":";
  mq2 += mq2Raw;
  mq2 += ",\"unit\":\"raw\",\"measurement_kind\":\"RAW_ADC\",\"adc_status\":\"";
  mq2 += (mq2Raw <= 1 || mq2Raw >= 4094) ? "SATURATED\"}" : "OK\"}";
  publishSensorEvent("city/sensors/mq2", mq2, nowMs);
#endif

  if (lastDhtOk && dhtReadingPending) {
    char dhtTimestamp[25] = {};
    if (timestampIso8601(dhtTimestamp, sizeof(dhtTimestamp), nowMs - lastDhtReadMs)) {
      String dhtPayload = basePayload("DHT22", dhtTimestamp, nextMessageId());
      dhtPayload += ",\"value\":";
      dhtPayload += String(lastTemperatureC, 1);
      dhtPayload += ",\"unit\":\"C\",\"humidity\":";
      dhtPayload += String(lastHumidityPct, 1);
      dhtPayload += ",\"humidity_unit\":\"pct\"";
      dhtPayload += ",\"dht_ok\":true}";
      publishSensorEvent("city/sensors/dht22", dhtPayload, nowMs);
      dhtReadingPending = false;
    }
  }

  const bool ir1Blocked = digitalRead(IR1_PIN) == LOW;
  const bool ir2Blocked = digitalRead(IR2_PIN) == LOW;

  String ir1 = basePayload("IR_A", timestamp, nextMessageId());
  ir1 += ",\"value\":";
  ir1 += (ir1Blocked ? "true" : "false");
  ir1 += ",\"unit\":\"blocked\",\"raw\":\"";
  ir1 += (ir1Blocked ? "LOW" : "HIGH");
  ir1 += "\"}";
  publishSensorEvent("city/sensors/ir_a", ir1, nowMs);

  String ir2 = basePayload("IR_B", timestamp, nextMessageId());
  ir2 += ",\"value\":";
  ir2 += (ir2Blocked ? "true" : "false");
  ir2 += ",\"unit\":\"blocked\",\"raw\":\"";
  ir2 += (ir2Blocked ? "LOW" : "HIGH");
  ir2 += "\"}";
  publishSensorEvent("city/sensors/ir_b", ir2, nowMs);

#if CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY
  const bool buttonPressed = digitalRead(BUTTON_PIN) == LOW;
  String button = basePayload("BUTTON", timestamp, nextMessageId());
  button += ",\"value\":";
  button += (buttonPressed ? "true" : "false");
  button += ",\"raw\":\"";
  button += (buttonPressed ? "LOW" : "HIGH");
  button += "\"}";
  publishSensorEvent("city/sensors/button", button, nowMs);
#endif

  Serial.printf(
      "SN1 MQTT uptime=%lu dht_ok=%d ir1=%s ir2=%s mqtt=%s\n",
      nowMs,
      lastDhtOk ? 1 : 0,
      ir1Blocked ? "BLOCKED" : "CLEAR",
      ir2Blocked ? "BLOCKED" : "CLEAR",
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
  Serial.printf("SN1 Wi-Fi connecting status=%d(%s)\n", status, wifiStatusName(status));
  WiFi.begin(CITYRESPONDER_WIFI_SSID, CITYRESPONDER_WIFI_PASSWORD);
}

void maintainMqtt(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected() || nowMs - lastMqttAttemptMs < RETRY_INTERVAL_MS) {
    return;
  }
  lastMqttAttemptMs = nowMs;
  Serial.println("SN1 MQTT connecting");
  const bool connected = mqttClient.connect(
      NODE_ID,
      CITYRESPONDER_MQTT_USERNAME,
      CITYRESPONDER_MQTT_PASSWORD);
  if (connected) {
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
  analogSetPinAttenuation(MQ2_AO_PIN, ADC_11db);
  dht.begin();

  mqttClient.setServer(CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  if (!mqttClient.setBufferSize(512)) {
    Serial.println("SN1 MQTT buffer allocation failed");
  }
  WiFi.mode(WIFI_STA);
  bootId = esp_random();
  Serial.printf("CityResponder SN1 firmware=%s protocol=%s\n", FIRMWARE_VERSION, PROTOCOL_VERSION);
  Serial.printf("SN1 MQTT node=%s broker=%s:%d topics=dht22,ir_a,ir_b\n", NODE_ID, CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  Serial.println("SN1 telemetry policy: MQ2=DISABLED button=DISABLED");
  if (!credentialsConfigured()) {
    Serial.println("SN1 Wi-Fi/MQTT settings are incomplete or placeholder values; configure local include/secrets.h");
  }
}

void loop() {
  const unsigned long nowMs = millis();
  readDhtIfDue(nowMs);
  if (credentialsConfigured()) {
    maintainWifi(nowMs);
    maintainTime(nowMs);
    maintainMqtt(nowMs);
    mqttClient.loop();
  }
  if (nowMs - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = nowMs;
    publishSensors(nowMs);
  }
}
