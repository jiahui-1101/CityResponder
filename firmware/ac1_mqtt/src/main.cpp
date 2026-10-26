#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>
#include "gate_contract.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define CITYRESPONDER_WIFI_SSID "YOUR_WIFI_SSID"
#define CITYRESPONDER_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define CITYRESPONDER_MQTT_HOST "YOUR_MQTT_HOST"
#define CITYRESPONDER_MQTT_PORT 1883
#endif

#ifndef CITYRESPONDER_MQTT_USERNAME
#define CITYRESPONDER_MQTT_USERNAME "YOUR_AC1_MQTT_USERNAME"
#endif
#ifndef CITYRESPONDER_MQTT_PASSWORD
#define CITYRESPONDER_MQTT_PASSWORD "YOUR_AC1_MQTT_PASSWORD"
#endif

namespace {
constexpr char NODE_ID[] = "AC1";
constexpr char ACK_PROTOCOL_VERSION[] = "AC1_ACK_V4_REVERSED_GATE_20261026";
constexpr char COMMAND_TOPIC[] = "city/commands/AC1";
constexpr char ACK_TOPIC[] = "city/acks/AC1";
// Logical route mapping follows the physical mounting: TL1 is PRIMARY/MAIN
// and TL2 is STANDBY. Keep each complete R/Y/G group together.
constexpr uint8_t TL1_RED_PIN = 14;
constexpr uint8_t TL1_YELLOW_PIN = 13;
constexpr uint8_t TL1_GREEN_PIN = 23;
constexpr uint8_t TL2_RED_PIN = 25;
constexpr uint8_t TL2_YELLOW_PIN = 26;
constexpr uint8_t TL2_GREEN_PIN = 27;
constexpr uint8_t BUZZER_PIN = 19;
constexpr uint8_t SERVO_PIN = gate_contract::SERVO_PIN;
constexpr int GATE_CLOSED_ANGLE = gate_contract::CLOSED_ANGLE;
constexpr int GATE_OPEN_ANGLE = gate_contract::OPEN_ANGLE;
static_assert(SERVO_PIN != TL1_RED_PIN && SERVO_PIN != TL1_YELLOW_PIN &&
              SERVO_PIN != TL1_GREEN_PIN && SERVO_PIN != TL2_RED_PIN &&
              SERVO_PIN != TL2_YELLOW_PIN && SERVO_PIN != TL2_GREEN_PIN &&
              SERVO_PIN != BUZZER_PIN, "Servo pin conflicts with another AC1 output");
constexpr unsigned long WIFI_TIMEOUT_MS = 15000;
constexpr unsigned long MQTT_RETRY_MS = 5000;
constexpr uint8_t COMMAND_DEDUP_SIZE = 32;
constexpr char NTP_SERVER[] = "pool.ntp.org";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
bool timeReported = false;
Servo gateServo;
bool gateServoAttached = false;
String appliedCommandIds[COMMAND_DEDUP_SIZE];
String appliedCommandFingerprints[COMMAND_DEDUP_SIZE];
String appliedCommandTerminalStatuses[COMMAND_DEDUP_SIZE];
String appliedCommandFailureReasons[COMMAND_DEDUP_SIZE];
uint8_t nextAppliedCommandSlot = 0;
bool wifiAttempted = false;
bool mqttAttempted = false;
enum class TrafficMode {
  STATIC,
  NORMAL_CYCLE,
};
TrafficMode trafficMode = TrafficMode::STATIC;
unsigned long trafficPhaseStartedAt = 0;
uint8_t trafficPhase = 0;
bool buzzerPulseActive = false;
unsigned long buzzerLastToggleAt = 0;
bool buzzerOn = false;

bool configuredValue(const char *value, const char *placeholder) {
  return value != nullptr && value[0] != '\0' && strcmp(value, placeholder) != 0;
}

bool wifiConfigured() {
  return configuredValue(CITYRESPONDER_WIFI_SSID, "YOUR_WIFI_SSID") &&
         configuredValue(CITYRESPONDER_WIFI_PASSWORD, "YOUR_WIFI_PASSWORD");
}

bool mqttConfigured() {
  return configuredValue(CITYRESPONDER_MQTT_HOST, "YOUR_MQTT_HOST") &&
         CITYRESPONDER_MQTT_PORT > 0 &&
         configuredValue(CITYRESPONDER_MQTT_USERNAME, "YOUR_AC1_MQTT_USERNAME") &&
         configuredValue(CITYRESPONDER_MQTT_PASSWORD, "YOUR_AC1_MQTT_PASSWORD");
}

void allLedsOff() {
  trafficMode = TrafficMode::STATIC;
  digitalWrite(TL1_RED_PIN, LOW);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, LOW);
  digitalWrite(TL2_RED_PIN, LOW);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void allRed() {
  trafficMode = TrafficMode::STATIC;
  digitalWrite(TL1_RED_PIN, HIGH);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, LOW);
  digitalWrite(TL2_RED_PIN, HIGH);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void mainRouteGreen() {
  trafficMode = TrafficMode::STATIC;
  digitalWrite(TL1_RED_PIN, LOW);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, HIGH);
  digitalWrite(TL2_RED_PIN, HIGH);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, LOW);
}

void standbyRouteGreen() {
  trafficMode = TrafficMode::STATIC;
  digitalWrite(TL1_RED_PIN, HIGH);
  digitalWrite(TL1_YELLOW_PIN, LOW);
  digitalWrite(TL1_GREEN_PIN, LOW);
  digitalWrite(TL2_RED_PIN, LOW);
  digitalWrite(TL2_YELLOW_PIN, LOW);
  digitalWrite(TL2_GREEN_PIN, HIGH);
}

void applyNormalTrafficPhase() {
  switch (trafficPhase) {
    case 0:  // PRIMARY green for four seconds.
      mainRouteGreen();
      break;
    case 1:  // PRIMARY yellow for one second.
      digitalWrite(TL1_RED_PIN, LOW);
      digitalWrite(TL1_YELLOW_PIN, HIGH);
      digitalWrite(TL1_GREEN_PIN, LOW);
      digitalWrite(TL2_RED_PIN, HIGH);
      digitalWrite(TL2_YELLOW_PIN, LOW);
      digitalWrite(TL2_GREEN_PIN, LOW);
      break;
    case 2:  // STANDBY green for four seconds.
      standbyRouteGreen();
      break;
    default:  // STANDBY yellow for one second.
      digitalWrite(TL1_RED_PIN, HIGH);
      digitalWrite(TL1_YELLOW_PIN, LOW);
      digitalWrite(TL1_GREEN_PIN, LOW);
      digitalWrite(TL2_RED_PIN, LOW);
      digitalWrite(TL2_YELLOW_PIN, HIGH);
      digitalWrite(TL2_GREEN_PIN, LOW);
      break;
  }
  trafficMode = TrafficMode::NORMAL_CYCLE;
  trafficPhaseStartedAt = millis();
}

void startNormalTrafficCycle() {
  trafficPhase = 0;
  applyNormalTrafficPhase();
}

void updateNormalTrafficCycle() {
  if (trafficMode != TrafficMode::NORMAL_CYCLE) {
    return;
  }
  const unsigned long duration = (trafficPhase == 0 || trafficPhase == 2) ? 4000 : 1000;
  if (millis() - trafficPhaseStartedAt >= duration) {
    trafficPhase = (trafficPhase + 1) % 4;
    applyNormalTrafficPhase();
  }
}

void setBuzzer(bool on) {
  buzzerPulseActive = false;
  buzzerOn = on;
  digitalWrite(BUZZER_PIN, on ? LOW : HIGH);
}

void startBuzzerPulse() {
  buzzerPulseActive = true;
  buzzerOn = true;
  buzzerLastToggleAt = millis();
  digitalWrite(BUZZER_PIN, LOW);
}

void updateBuzzerPulse() {
  if (!buzzerPulseActive || millis() - buzzerLastToggleAt < 500) {
    return;
  }
  buzzerLastToggleAt = millis();
  buzzerOn = !buzzerOn;
  digitalWrite(BUZZER_PIN, buzzerOn ? LOW : HIGH);
}

bool setGateAngle(int angle) {
  if (!gateServoAttached) {
    gateServo.setPeriodHertz(gate_contract::PWM_HZ);
    gateServo.attach(SERVO_PIN, gate_contract::MIN_PULSE_US,
                     gate_contract::MAX_PULSE_US);
    if (!gateServo.attached()) {
      return false;
    }
    gateServoAttached = true;
  }
  if (!gateServo.attached()) {
    return false;
  }
  gateServo.write(angle);
  return true;
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

void publishAck(
    const String &commandId,
    const char *status,
    const char *reason = nullptr,
    const char *stage = nullptr,
    const char *category = nullptr,
    const char *action = nullptr,
    const char *result = nullptr) {
  JsonDocument ack;
  ack["command_id"] = commandId;
  ack["node_id"] = NODE_ID;
  ack["status"] = status;
  ack["timestamp"] = timestampUtc();
  if (stage != nullptr) {
    ack["stage"] = stage;
  }
  if (category != nullptr) {
    ack["action_category"] = category;
  }
  if (action != nullptr) {
    ack["action_type"] = action;
  }
  if (result != nullptr) {
    ack["result"] = result;
  }
  if (reason != nullptr) {
    ack["reason"] = reason;
  }
  char output[384];
  const size_t length = serializeJson(ack, output, sizeof(output));
  const bool sent = mqttClient.publish(ACK_TOPIC, reinterpret_cast<const uint8_t *>(output), length, false);
  Serial.printf("AC1 ACK command_id=%s status=%s stage=%s transport_qos=0 published=%s\n",
                commandId.c_str(), status, stage == nullptr ? "unspecified" : stage,
                sent ? "YES" : "NO");
}

bool readString(JsonVariantConst value, String &out) {
  if (!value.is<const char *>()) {
    return false;
  }
  out = value.as<const char *>();
  return out.length() > 0;
}

bool actionSupported(
    const String &category,
    const String &action,
    JsonVariantConst parameters,
    const char *&reason) {
  if (category == "GATE") {
    if (gate_contract::parseAction(action.c_str()) == gate_contract::Action::INVALID) {
      reason = "UNSUPPORTED_ACTION";
      return false;
    }
    // Gate movement uses only the two configured targets. Reject any caller-
    // supplied position value, even if it accompanies OPEN or CLOSE.
    if (!parameters.is<JsonObjectConst>() ||
        !gate_contract::acceptsParameterCount(parameters.as<JsonObjectConst>().size())) {
      reason = "UNSUPPORTED_POSITION";
      return false;
    }
    return true;
  }
  if ((category == "TRAFFIC" &&
       (action == "ALL_RED" || action == "NORMAL_CYCLE" || action == "OFF")) ||
      (category == "BUZZER" &&
       (action == "ON" || action == "OFF" || action == "PULSE_500_MS"))) {
    return true;
  }
  if (category == "TRAFFIC" && action == "GREEN_CORRIDOR") {
    String corridor;
    if (!readString(parameters["corridor"], corridor)) {
      reason = "CORRIDOR_REQUIRED";
      return false;
    }
    if (corridor == "PRIMARY" || corridor == "STANDBY") {
      return true;
    }
    reason = "INVALID_CORRIDOR";
    return false;
  }
  reason = "UNSUPPORTED_ACTION";
  return false;
}

String actionFingerprint(const String &category, const String &action, JsonVariantConst parameters) {
  String fingerprint = category + "|" + action;
  if (category == "TRAFFIC" && action == "GREEN_CORRIDOR") {
    String corridor;
    readString(parameters["corridor"], corridor);
    fingerprint += "|" + corridor;
  }
  return fingerprint;
}

int findAppliedCommand(const String &commandId) {
  for (uint8_t index = 0; index < COMMAND_DEDUP_SIZE; ++index) {
    if (appliedCommandIds[index] == commandId) {
      return index;
    }
  }
  return -1;
}

void rememberAppliedCommand(const String &commandId, const String &fingerprint,
                            const char *terminalStatus = "ACK",
                            const char *failureReason = "") {
  appliedCommandIds[nextAppliedCommandSlot] = commandId;
  appliedCommandFingerprints[nextAppliedCommandSlot] = fingerprint;
  appliedCommandTerminalStatuses[nextAppliedCommandSlot] = terminalStatus;
  appliedCommandFailureReasons[nextAppliedCommandSlot] = failureReason;
  nextAppliedCommandSlot = (nextAppliedCommandSlot + 1) % COMMAND_DEDUP_SIZE;
}

void commandCallback(char *topic, byte *payload, unsigned int length) {
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
  if (commandId.length() > 128 || nodeId.length() > 32 || commandType.length() > 64) {
    Serial.println("AC1 COMMAND rejected reason=IDENTIFIER_TOO_LONG");
    return;
  }

  Serial.printf("AC1 COMMAND command_id=%s type=%s category=%s action=%s\n",
                commandId.c_str(), commandType.c_str(), category.c_str(), action.c_str());
  if (String(topic) != COMMAND_TOPIC || nodeId != NODE_ID || commandType != "PHYSICAL_ACTION") {
    publishAck(commandId, "REJECTED", "NODE_OR_COMMAND_TYPE_MISMATCH", "failed", category.c_str(), action.c_str());
    return;
  }

  const char *validationReason = nullptr;
  if (!actionSupported(category, action, command["payload"]["parameters"], validationReason)) {
    publishAck(commandId, "REJECTED", validationReason, "failed", category.c_str(), action.c_str());
    return;
  }
  const String fingerprint = actionFingerprint(category, action, command["payload"]["parameters"]);

  // Backend retries and broker redelivery preserve command_id. ACK duplicates
  // without re-actuating hardware.
  const int priorCommandIndex = findAppliedCommand(commandId);
  if (priorCommandIndex >= 0) {
    if (fingerprint != appliedCommandFingerprints[priorCommandIndex]) {
      publishAck(commandId, "REJECTED", "COMMAND_ID_REUSED_FOR_DIFFERENT_ACTION", "failed", category.c_str(), action.c_str());
      return;
    }
    if (appliedCommandTerminalStatuses[priorCommandIndex] == "FAILED") {
      publishAck(commandId, "FAILED", appliedCommandFailureReasons[priorCommandIndex].c_str(),
                 "failed", category.c_str(), action.c_str(), "DUPLICATE_SUPPRESSED");
    } else {
      publishAck(commandId, "ACK", nullptr, "execution_reported", category.c_str(), action.c_str(), "DUPLICATE_SUPPRESSED");
    }
    return;
  }

  publishAck(commandId, "RECEIVED", nullptr, "received", category.c_str(), action.c_str());

  if (category == "TRAFFIC" && action == "ALL_RED") {
    allRed();
  } else if (category == "TRAFFIC" && action == "GREEN_CORRIDOR") {
    String corridor;
    readString(command["payload"]["parameters"]["corridor"], corridor);
    if (corridor == "PRIMARY") {
      mainRouteGreen();
    } else if (corridor == "STANDBY") {
      standbyRouteGreen();
    }
  } else if (category == "TRAFFIC" && action == "NORMAL_CYCLE") {
    startNormalTrafficCycle();
  } else if (category == "TRAFFIC" && action == "OFF") {
    allLedsOff();
  } else if (category == "BUZZER" && action == "ON") {
    setBuzzer(true);
  } else if (category == "BUZZER" && action == "OFF") {
    setBuzzer(false);
  } else if (category == "BUZZER" && action == "PULSE_500_MS") {
    startBuzzerPulse();
  } else if (category == "GATE" && action == "OPEN") {
    if (!setGateAngle(GATE_OPEN_ANGLE)) {
      rememberAppliedCommand(commandId, fingerprint, "FAILED", "SERVO_ATTACH_FAILED");
      publishAck(commandId, "FAILED", "SERVO_ATTACH_FAILED", "failed", category.c_str(), action.c_str());
      return;
    }
    Serial.printf("AC1 GATE OPEN angle=%d\n", GATE_OPEN_ANGLE);
  } else if (category == "GATE" && action == "CLOSE") {
    if (!setGateAngle(GATE_CLOSED_ANGLE)) {
      rememberAppliedCommand(commandId, fingerprint, "FAILED", "SERVO_ATTACH_FAILED");
      publishAck(commandId, "FAILED", "SERVO_ATTACH_FAILED", "failed", category.c_str(), action.c_str());
      return;
    }
    Serial.printf("AC1 GATE CLOSE angle=%d\n", GATE_CLOSED_ANGLE);
  }

  rememberAppliedCommand(commandId, fingerprint);
  const char *result = category == "GATE" ? "TARGET_COMMANDED" : "OUTPUT_SET";
  publishAck(commandId, "ACK", nullptr, "execution_reported", category.c_str(), action.c_str(), result);
}

void connectWifi() {
  if (!wifiConfigured() || WiFi.status() == WL_CONNECTED) {
    return;
  }
  const unsigned long now = millis();
  if (wifiAttempted && now - lastWifiAttempt < WIFI_TIMEOUT_MS) {
    return;
  }
  wifiAttempted = true;
  lastWifiAttempt = now;
  Serial.println("AC1 Wi-Fi connecting");
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
  if (!mqttConfigured() || WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return;
  }
  const unsigned long now = millis();
  if (mqttAttempted && now - lastMqttAttempt < MQTT_RETRY_MS) {
    return;
  }
  mqttAttempted = true;
  lastMqttAttempt = now;
  const String clientId = String("AC1-") + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("AC1 MQTT connecting broker=%s:%d\n", CITYRESPONDER_MQTT_HOST, CITYRESPONDER_MQTT_PORT);
  if (mqttClient.connect(clientId.c_str(), CITYRESPONDER_MQTT_USERNAME,
                         CITYRESPONDER_MQTT_PASSWORD)) {
    if (mqttClient.subscribe(COMMAND_TOPIC, 1)) {
      Serial.printf("AC1 MQTT connected subscribed=%s qos=1 retain=0\n", COMMAND_TOPIC);
    } else {
      Serial.printf("AC1 MQTT subscription failed topic=%s\n", COMMAND_TOPIC);
      mqttClient.disconnect();
    }
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
  setBuzzer(false);
  pinMode(SERVO_PIN, INPUT);

  Serial.begin(115200);
  delay(250);
  Serial.println();
  Serial.println("=== CityResponder AC1 MQTT ===");
  Serial.println("node=AC1 mode=MQTT_SAFE_STARTUP");
  Serial.printf("ack_protocol_version=%s\n", ACK_PROTOCOL_VERSION);
  Serial.printf("TL1_PRIMARY=14,13,23 TL2_STANDBY=25,26,27 BUZZER=19(active-low) SERVO=%u gate_closed=%d gate_open=%d\n",
                SERVO_PIN, GATE_CLOSED_ANGLE, GATE_OPEN_ANGLE);
  Serial.println("startup=ALL_LEDS_OFF BUZZER_OFF SERVO_UNATTACHED");
  Serial.printf("MQTT command=%s subscription_qos=1 ack=%s publish_qos=0 retain=0 duplicate_policy=last_32_ids_in_ram\n", COMMAND_TOPIC, ACK_TOPIC);
  Serial.printf("wifi_configured=%s mqtt_configured=%s\n",
                wifiConfigured() ? "YES" : "NO", mqttConfigured() ? "YES" : "NO");
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
  updateNormalTrafficCycle();
  updateBuzzerPulse();
  if (!timeReported && time(nullptr) >= 1700000000) {
    timeReported = true;
    Serial.printf("AC1 time synchronized timestamp=%s\n", timestampUtc().c_str());
  }
  delay(5);
}
