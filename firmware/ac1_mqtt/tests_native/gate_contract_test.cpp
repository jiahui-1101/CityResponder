#include <cassert>

#include "gate_contract.h"

int main() {
  using gate_contract::Action;

  // S01/S02: only the documented OPEN/CLOSE actions select targets.
  assert(gate_contract::parseAction("OPEN") == Action::OPEN);
  assert(gate_contract::angleFor(Action::OPEN) == 30);
  assert(gate_contract::parseAction("CLOSE") == Action::CLOSE);
  assert(gate_contract::angleFor(Action::CLOSE) == 120);

  // S03/S04: an arbitrary position or unsupported action is not a gate target.
  assert(gate_contract::acceptsParameterCount(0));
  assert(!gate_contract::acceptsParameterCount(1));
  assert(gate_contract::parseAction("POSITION") == Action::INVALID);
  assert(gate_contract::parseAction("GATE_OPEN") == Action::INVALID);
  assert(gate_contract::parseAction(nullptr) == Action::INVALID);

  // S11: the configured targets map inside the nominal SG90 control interval.
  assert(gate_contract::SERVO_PIN == 18);
  assert(gate_contract::PWM_HZ == 50);
  assert(gate_contract::MIN_PULSE_US == 1000);
  assert(gate_contract::MAX_PULSE_US == 2000);
  assert(gate_contract::pulseForAngle(gate_contract::OPEN_ANGLE) == 1166);
  assert(gate_contract::pulseForAngle(gate_contract::CLOSED_ANGLE) == 1666);
}
