# AC1 MQTT actuator firmware

This is separate from `firmware/ac1_bringup`, which remains the manual-only
hardware diagnostic firmware. It consumes the existing generic actuator
contract on `city/commands/AC1` and publishes correlated ACKs on
`city/acks/AC1`, both at QoS 1 and non-retained.

The local `include/secrets.h` must define the same four fields as
`include/secrets.example.h`. During local bring-up, the source also accepts
the existing ignored SN1 secrets file so credentials are never copied into
the repository. No credentials belong in Git.

Supported production actions are TRAFFIC/ALL_RED, TRAFFIC/GREEN_CORRIDOR,
TRAFFIC/OFF, BUZZER/ON or OFF, and the calibrated GATE/OPEN or GATE/CLOSE
actions. GREEN_CORRIDOR uses the documented main route preference (TL1
green, TL2 red). The verified gate angles are CLOSED=30° and OPEN=120°.
