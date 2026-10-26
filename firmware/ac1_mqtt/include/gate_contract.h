#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace gate_contract {

constexpr uint8_t SERVO_PIN = 18;
// V4 targets passed one operator-observed linked OPEN/CLOSE cycle.
// There is no independent position feedback or long-term safety evidence.
constexpr int OPEN_ANGLE = 30;
constexpr int CLOSED_ANGLE = 120;
// Nominal SG90 control interval from the manufacturer data sheet. The
// mechanical endpoints still require unloaded calibration on this gate.
constexpr int MIN_PULSE_US = 1000;
constexpr int MAX_PULSE_US = 2000;
constexpr int PWM_HZ = 50;

enum class Action { INVALID, OPEN, CLOSE };

inline Action parseAction(const char *value) {
  if (value == nullptr) return Action::INVALID;
  if (strcmp(value, "OPEN") == 0) return Action::OPEN;
  if (strcmp(value, "CLOSE") == 0) return Action::CLOSE;
  return Action::INVALID;
}

constexpr int angleFor(Action action) {
  return action == Action::OPEN ? OPEN_ANGLE :
         action == Action::CLOSE ? CLOSED_ANGLE : -1;
}

constexpr bool acceptsParameterCount(size_t count) { return count == 0; }

constexpr int pulseForAngle(int angle) {
  return MIN_PULSE_US + angle * (MAX_PULSE_US - MIN_PULSE_US) / 180;
}

static_assert(OPEN_ANGLE >= 0 && OPEN_ANGLE <= 180 &&
              CLOSED_ANGLE >= 0 && CLOSED_ANGLE <= 180 &&
              OPEN_ANGLE != CLOSED_ANGLE,
              "Gate target angles must be distinct and within the servo API range");
static_assert(pulseForAngle(CLOSED_ANGLE) >= MIN_PULSE_US &&
              pulseForAngle(CLOSED_ANGLE) <= MAX_PULSE_US &&
              pulseForAngle(OPEN_ANGLE) >= MIN_PULSE_US &&
              pulseForAngle(OPEN_ANGLE) <= MAX_PULSE_US,
              "Gate target pulses must stay within the configured SG90 interval");

}  // namespace gate_contract
