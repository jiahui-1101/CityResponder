#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#elif __has_include("../../sn1_mqtt/include/secrets.h")
// Reuse the already ignored local credentials without copying them.
#include "../../sn1_mqtt/include/secrets.h"
#else
#define CITYRESPONDER_WIFI_SSID "YOUR_WIFI_SSID"
#define CITYRESPONDER_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define CITYRESPONDER_MQTT_HOST "YOUR_MQTT_HOST"
#define CITYRESPONDER_MQTT_PORT 1883
#endif

namespace {
constexpr char NODE_ID[] = "AC1";
constexpr char COMMAND_TOPIC[] = "city/commands/AC1";
constexpr char ACK_TOPIC[] = "city/acks/AC1";
constexpr uint8_t TL1_RED_PIN = 25;
constexpr uint8_t TL1_YELLOW_PIN = 26;
constexpr uint8_t TL1_GREEN_PIN = 27;
constexpr uint8_t TL2_RED_PIN = 14;
constexpr uint8_t TL2_YELLOW_PIN = 13;
constexpr uint8_t TL2_GREEN_PIN = 23;
constexpr uint8_t BUZZER_PIN = 19;
constexpr uint8_t SERVO_PIN = 18;
constexpr int GATE_CLOSED_ANGLE = 30;
constexpr int GATE_OPEN_ANGLE = 120;
constexpr unsigned long WIFI_TIMEOUT_MS = 15000;
constexpr unsigned long MQTT_RETRY_MS = 5000;
constexpr char NTP_SERVER[] = "pool.ntp.org";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
bool timeReported = false;
Servo gateServo;
bool gateServoAttached = false;
String lastAppliedCommandId;

bool credentialsConfigured() {
  return String(CITYRESPONDER_WIFI_SSID) != "YOUR_WIFI_SSID" &&
         String(CITYRESPONDER_WIFI_PASSWORD) != "YOUR_WIFI_PASSWORD" &&
         String(CITYRESPONDER_MQTT_HOST) != "YOUR_MQTT_HOST";
}

void allLedsOff() {
  digitalWrite(TL1_RED_PIN, LOW);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, LOW);
  digitalWrite(TL2_RED_PIN, LOW);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void allRed() {
  digitalWrite(TL1_RED_PIN, HIGH);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, LOW);
  digitalWrite(TL2_RED_PIN, HIGH);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void mainRouteGreen() {
  // Existing route semantics prefer MAIN (TL1); ALTERNATE (TL2) is stopped.
  digitalWrite(TL1_RED_PIN, LOW);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, HIGH);
  digitalWrite(TL2_RED_PIN, HIGH);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void setGateAngle(int angle) {
  if (!gateServoAttached) {
    gateServo.attach(SERVO_PIN);
    gateServoAttached = true;
  }
  gateServo.write(angle);
}

String timestampUtc() {
  time_t now = time(nullptr);
  if (now < 1700000000) {
    return "1970-01-01T00:00:00Z";
  }
  struct tm utc;
  gmtime_r(&now, &utc);
  char buffer[32];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return String(buffer);
}

void publishAck(const String &commandId, const char *status, const char *reason = nullptr) {
  JsonDocument ack;
  ack["command_id"] = commandId;
  ack["node_id"] = NODE_ID;
  ack["status"] = status;
  ack["timestamp"] = timestampUtc();
  if (reason != nullptr) {
    ack["reason"] = reason;
  }
  char output[384];
  const size_t length = serializeJson(ack, output, sizeof(output));
  const bool sent = mqttClient.publish(ACK_TOPIC, reinterpret_cast<const uint8_t *>(output), length, false);
  Serial.printf("AC1 ACK command_id=%s status=%s published=%s\n", commandId.c_str(), status, sent ? "YES" : "NO");
}

bool readString(JsonVariantConst value, String &out) {
  if (!value.is<const char *>()) {
    return false;
  }
  out = value.as<const char *>();
  return out.length() > 0;
}

void commandCallback(char *, byte *payload, unsigned int length) {
  JsonDocument command;
  const DeserializationError error = deserializeJson(command, payload, length);
  if (error) {
    Serial.printf("AC1 COMMAND rejected reason=INVALID_JSON detail=%s\n", error.c_str());
    return;
  }

  String commandId;
  String nodeId;
  String commandType;
  String category;
  String action;
  if (!readString(command["command_id"], commandId) ||
      !readString(command["node_id"], nodeId) ||
      !readString(command["command_type"], commandType) ||
      !readString(command["payload"]["action_category"], category) ||
      !readString(command["payload"]["action_type"], action)) {
    Serial.println("AC1 COMMAND rejected reason=INVALID_ENVELOPE");
    return;
  }

  Serial.printf("AC1 COMMAND command_id=%s type=%s category=%s action=%s\n",
                commandId.c_str(), commandType.c_str(), category.c_str(), action.c_str());
  if (nodeId != NODE_ID || commandType != "PHYSICAL_ACTION") {
    publishAck(commandId, "REJECTED", "NODE_OR_COMMAND_TYPE_MISMATCH");
    return;
  }

  // Backend retries use a new command_id, while broker redelivery can repeat
  // the same command_id. ACK duplicates without re-actuating hardware.
  if (commandId == lastAppliedCommandId) {
    publishAck(commandId, "ACK", "DUPLICATE_ALREADY_APPLIED");
    return;
  }
  lastAppliedCommandId = commandId;

  if (category == "TRAFFIC" && action == "ALL_RED") {
    allRed();
    publishAck(commandId, "ACK");
    return;
  }
  if (category == "TRAFFIC" && action == "GREEN_CORRIDOR") {
    mainRouteGreen();
    publishAck(commandId, "ACK");
    return;
  }
  if (category == "TRAFFIC" && action == "OFF") {
    allLedsOff();
    publishAck(commandId, "ACK");
    return;
  }
  if (category == "BUZZER" && action == "ON") {
    digitalWrite(BUZZER_PIN, LOW);
    publishAck(commandId, "ACK");
    return;
  }
  if (category == "BUZZER" && action == "OFF") {
    digitalWrite(BUZZER_PIN, HIGH);
    publishAck(commandId, "ACK");
    return;
  }
  if (category == "GATE" && action == "OPEN") {
    setGateAngle(GATE_OPEN_ANGLE);
    publishAck(commandId, "ACK");
    Serial.printf("AC1 GATE OPEN angle=%d\n", GATE_OPEN_ANGLE);
    return;
  }
  if (category == "GATE" && action == "CLOSE") {
    setGateAngle(GATE_CLOSED_ANGLE);
    publishAck(commandId, "ACK");
    Serial.printf("AC1 GATE CLOSE angle=%d\n", GATE_CLOSED_ANGLE);
    return;
  }

  publishAck(commandId, "REJECTED", "UNSUPPORTED_ACTION");
}

void connectWifi() {
  if (!credentialsConfigured() || WiFi.status() == WL_CONNECTED) {
    return;
  }
  const unsigned long now = millis();
  if (now - lastWifiAttempt < WIFI_TIMEOUT_MS) {
    return;
  }
  lastWifiAttempt = now;
  Serial.printf("AC1 Wi-Fi connecting ssid=%s\n", CITYRESPONDER_WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(CITYRESPONDER_WIFI_SSID, CITYRESPONDER_WIFI_PASSWORD);
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("AC1 Wi-Fi connected ip=%s rssi=%d status=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.status());
    configTime(0, 0, NTP_SERVER);
  } else {
    Serial.printf("AC1 Wi-Fi failed status=%d\n", WiFi.status());
  }
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return;
  }
  const unsigned long now = millis();
  if (now - lastMqttAttempt < MQTT_RETRY_MS) {
    return;
  }
  lastMqttAttempt = now;
  const String clientId = String("AC1-") + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("AC1 MQTT connecting broker=%s:%d\n", CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  if (mqttClient.connect(clientId.c_str())) {
    mqttClient.subscribe(COMMAND_TOPIC, 1);
    Serial.printf("AC1 MQTT connected subscribed=%s qos=1 retain=0\n", COMMAND_TOPIC);
  } else {
    Serial.printf("AC1 MQTT failed state=%d\n", mqttClient.state());
  }
}
}  // namespace

void setup() {
  const uint8_t outputPins[] = {TL1_RED_PIN, TL1_YELLOW_PIN, TL1_GREEN_PIN,
                               TL2_RED_PIN, TL2_YELLOW_PIN, TL2_GREEN_PIN,
                               BUZZER_PIN};
  for (const uint8_t pin : outputPins) {
    pinMode(pin, OUTPUT);
  }
  allLedsOff();
  digitalWrite(BUZZER_PIN, HIGH);
  pinMode(SERVO_PIN, INPUT);

  Serial.begin(115200);
  delay(250);
  Serial.println();
  Serial.println("=== CityResponder AC1 MQTT ===");
  Serial.println("node=AC1 mode=MQTT_SAFE_STARTUP");
  Serial.println("TL1=25,26,27 TL2=14,13,23 BUZZER=19(active-low) SERVO=18 gate_closed=30 gate_open=120");
  Serial.println("startup=ALL_LEDS_OFF BUZZER_OFF SERVO_UNATTACHED");
  Serial.printf("MQTT command=%s ack=%s qos=1 retain=0 duplicate_policy=UNSPECIFIED\n", COMMAND_TOPIC, ACK_TOPIC);
  Serial.printf("credentials_configured=%s\n", credentialsConfigured() ? "YES" : "NO");
  mqttClient.setServer(CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  // The existing PHYSICAL_ACTION envelope is larger than PubSubClient's
  // 256-byte default packet buffer. Keep room for the full JSON contract.
  mqttClient.setBufferSize(1024);
  mqttClient.setCallback(commandCallback);
}

void loop() {
  connectWifi();
  connectMqtt();
  if (mqttClient.connected()) {
    mqttClient.loop();
  }
  if (!timeReported && time(nullptr) >= 1700000000) {
    timeReported = true;
    Serial.printf("AC1 time synchronized timestamp=%s\n", timestampUtc().c_str());
  }
  delay(5);
}
