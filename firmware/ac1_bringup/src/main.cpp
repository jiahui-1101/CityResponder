#include <Arduino.h>
#include <ESP32Servo.h>

namespace {
constexpr uint8_t TL1_RED_PIN = 25;
constexpr uint8_t TL1_YELLOW_PIN = 26;
constexpr uint8_t TL1_GREEN_PIN = 27;
constexpr uint8_t TL2_RED_PIN = 14;
constexpr uint8_t TL2_YELLOW_PIN = 13;
constexpr uint8_t TL2_GREEN_PIN = 23;
constexpr uint8_t BUZZER_PIN = 19;
constexpr uint8_t SERVO_PIN = 18;

constexpr uint8_t LED_PINS[] = {
    TL1_RED_PIN,
    TL1_YELLOW_PIN,
    TL1_GREEN_PIN,
    TL2_RED_PIN,
    TL2_YELLOW_PIN,
    TL2_GREEN_PIN,
};

String inputLine;
Servo servo;
bool servoAttached = false;

void writeOutput(const char *name, uint8_t pin, uint8_t level) {
  digitalWrite(pin, level);
  Serial.print("AC1 WRITE actuator=");
  Serial.print(name);
  Serial.print(" gpio=");
  Serial.print(pin);
  Serial.print(" state=");
  Serial.println(level == HIGH ? "HIGH" : "LOW");
}

void allLedsOff() {
  for (const uint8_t pin : LED_PINS) {
    digitalWrite(pin, LOW);
  }
  Serial.println("AC1 WRITE actuator=ALL_LEDS gpio=25,26,27,14,13,23 state=LOW");
}

bool handleLedCommand(const String &command) {
  struct CommandSpec {
    const char *command;
    const char *name;
    uint8_t pin;
    uint8_t level;
  };

  static const CommandSpec commands[] = {
      {"TL1_R_ON", "TL1_RED", TL1_RED_PIN, HIGH},
      {"TL1_R_OFF", "TL1_RED", TL1_RED_PIN, LOW},
      {"TL1_Y_ON", "TL1_YELLOW", TL1_YELLOW_PIN, HIGH},
      {"TL1_Y_OFF", "TL1_YELLOW", TL1_YELLOW_PIN, LOW},
      {"TL1_G_ON", "TL1_GREEN", TL1_GREEN_PIN, HIGH},
      {"TL1_G_OFF", "TL1_GREEN", TL1_GREEN_PIN, LOW},
      {"TL2_R_ON", "TL2_RED", TL2_RED_PIN, HIGH},
      {"TL2_R_OFF", "TL2_RED", TL2_RED_PIN, LOW},
      {"TL2_Y_ON", "TL2_YELLOW", TL2_YELLOW_PIN, HIGH},
      {"TL2_Y_OFF", "TL2_YELLOW", TL2_YELLOW_PIN, LOW},
      {"TL2_G_ON", "TL2_GREEN", TL2_GREEN_PIN, HIGH},
      {"TL2_G_OFF", "TL2_GREEN", TL2_GREEN_PIN, LOW},
  };

  for (const CommandSpec &spec : commands) {
    if (command == spec.command) {
      writeOutput(spec.name, spec.pin, spec.level);
      return true;
    }
  }
  return false;
}

void printStatus() {
  Serial.print("AC1 STATUS leds=");
  for (size_t index = 0; index < sizeof(LED_PINS) / sizeof(LED_PINS[0]); ++index) {
    if (index > 0) {
      Serial.print(',');
    }
    Serial.print(LED_PINS[index]);
    Serial.print(':');
    Serial.print(digitalRead(LED_PINS[index]) == HIGH ? "HIGH" : "LOW");
  }
  Serial.print(" buzzer=RELEASED servo=");
  Serial.print(servoAttached ? "HOLDING_90" : "NOT_ATTACHED");
  Serial.println(" ready=YES");
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();
  if (command.length() == 0) {
    return;
  }

  Serial.print("AC1 RX command=");
  Serial.println(command);

  if (handleLedCommand(command)) {
    return;
  }
  if (command == "ALL_LEDS_OFF") {
    allLedsOff();
    return;
  }
  if (command == "BUZZER_HIGH") {
    pinMode(BUZZER_PIN, OUTPUT);
    writeOutput("BUZZER", BUZZER_PIN, HIGH);
    return;
  }
  if (command == "BUZZER_LOW") {
    pinMode(BUZZER_PIN, OUTPUT);
    writeOutput("BUZZER", BUZZER_PIN, LOW);
    return;
  }
  if (command == "BUZZER_RELEASE") {
    digitalWrite(BUZZER_PIN, LOW);
    pinMode(BUZZER_PIN, INPUT);
    Serial.println("AC1 WRITE actuator=BUZZER gpio=19 state=RELEASED");
    return;
  }
  if (command == "SERVO_SET_90") {
    if (!servoAttached) {
      servo.attach(SERVO_PIN);
      servoAttached = true;
    }
    servo.write(90);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 angle=90 state=HOLDING");
    return;
  }
  if (command == "SERVO_SET_30") {
    if (!servoAttached) {
      servo.attach(SERVO_PIN);
      servoAttached = true;
    }
    servo.write(30);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 angle=30 state=HOLDING");
    return;
  }
  if (command == "SERVO_SET_100") {
    if (!servoAttached) {
      servo.attach(SERVO_PIN);
      servoAttached = true;
    }
    servo.write(100);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 angle=100 state=HOLDING");
    return;
  }
  if (command == "SERVO_SET_110") {
    if (!servoAttached) {
      servo.attach(SERVO_PIN);
      servoAttached = true;
    }
    servo.write(110);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 angle=110 state=HOLDING");
    return;
  }
  if (command == "SERVO_SET_120") {
    if (!servoAttached) {
      servo.attach(SERVO_PIN);
      servoAttached = true;
    }
    servo.write(120);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 angle=120 state=HOLDING");
    return;
  }
  if (command == "SERVO_RELEASE") {
    if (servoAttached) {
      servo.detach();
      servoAttached = false;
    }
    pinMode(SERVO_PIN, INPUT);
    Serial.println("AC1 WRITE actuator=SERVO gpio=18 state=RELEASED");
    return;
  }
  if (command == "STATUS") {
    printStatus();
    return;
  }

  Serial.print("AC1 ERROR unknown_command=");
  Serial.println(command);
}

void printStartupBanner() {
  Serial.println();
  Serial.println("=== CityResponder AC1 bring-up ===");
  Serial.println("node=AC1 serial=115200 mode=MANUAL_ONLY");
  Serial.println("TL1 RED=GPIO25 YELLOW=GPIO26 GREEN=GPIO27");
  Serial.println("TL2 RED=GPIO14 YELLOW=GPIO13 GREEN=GPIO23");
  Serial.println("BUZZER SIG=GPIO19 polarity=UNVERIFIED startup=RELEASED");
  Serial.println("SERVO SIGNAL=GPIO18 state=NOT_ATTACHED angle=UNDEFINED");
  Serial.println("LED startup state=ALL_OFF");
  Serial.println("commands=TL1_R_ON/OFF,TL1_Y_ON/OFF,TL1_G_ON/OFF,TL2_R_ON/OFF,TL2_Y_ON/OFF,TL2_G_ON/OFF,ALL_LEDS_OFF,BUZZER_HIGH,BUZZER_LOW,BUZZER_RELEASE,SERVO_SET_30,SERVO_SET_90,SERVO_SET_100,SERVO_SET_110,SERVO_SET_120,SERVO_RELEASE,STATUS");
  Serial.println("AC1 READY");
}
}  // namespace

void setup() {
  for (const uint8_t pin : LED_PINS) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }

  digitalWrite(BUZZER_PIN, LOW);
  pinMode(BUZZER_PIN, INPUT);
  digitalWrite(SERVO_PIN, LOW);
  pinMode(SERVO_PIN, INPUT);

  Serial.begin(115200);
  inputLine.reserve(64);
  delay(250);
  printStartupBanner();
}

void loop() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());
    if (incoming == '\n' || incoming == '\r') {
      if (inputLine.length() > 0) {
        handleCommand(inputLine);
        inputLine = "";
      }
    } else if (inputLine.length() < 63) {
      inputLine += incoming;
    }
  }
}
