#include <Arduino.h>
#include <DHT.h>

namespace {
constexpr uint8_t MQ2_AO_PIN = 34;
constexpr uint8_t DHT_DATA_PIN = 4;
constexpr uint8_t IR1_PIN = 32;
constexpr uint8_t IR2_PIN = 33;
constexpr uint8_t BUTTON_PIN = 27;
constexpr uint8_t DHT_TYPE = DHT22;
constexpr unsigned long REPORT_INTERVAL_MS = 1000;
constexpr unsigned long DHT_INTERVAL_MS = 2000;

DHT dht(DHT_DATA_PIN, DHT_TYPE);
unsigned long lastReportMs = 0;
unsigned long lastDhtReadMs = 0;
float lastTemperatureC = NAN;
float lastHumidityPct = NAN;
bool lastDhtOk = false;
bool haveDhtRead = false;

void printFloatOrNa(const char *label, float value) {
  Serial.print(label);
  if (isnan(value)) {
    Serial.print("NA");
  } else {
    Serial.print(value, 1);
  }
}

void readDhtIfDue(unsigned long nowMs) {
  if (haveDhtRead && nowMs - lastDhtReadMs < DHT_INTERVAL_MS) {
    return;
  }

  lastDhtReadMs = nowMs;
  const float temperatureC = dht.readTemperature();
  const float humidityPct = dht.readHumidity();
  lastDhtOk = !isnan(temperatureC) && !isnan(humidityPct);
  if (lastDhtOk) {
    lastTemperatureC = temperatureC;
    lastHumidityPct = humidityPct;
  } else {
    lastTemperatureC = NAN;
    lastHumidityPct = NAN;
  }
  haveDhtRead = true;
}

void printReport(unsigned long nowMs) {
  Serial.print("SN1 uptime=");
  Serial.print(nowMs);
  Serial.print(" dht_temp=");
  printFloatOrNa("", lastTemperatureC);
  Serial.print(" dht_humidity=");
  printFloatOrNa("", lastHumidityPct);
  Serial.print(" dht_ok=");
  Serial.print(lastDhtOk ? 1 : 0);
  Serial.print(" ir1=");
  Serial.print(digitalRead(IR1_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" ir2=");
  Serial.print(digitalRead(IR2_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" button=");
  Serial.print(digitalRead(BUTTON_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" mq2_raw=");
  Serial.println(analogRead(MQ2_AO_PIN));
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
}

void loop() {
  const unsigned long nowMs = millis();
  readDhtIfDue(nowMs);
  if (nowMs - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = nowMs;
    printReport(nowMs);
  }
}
