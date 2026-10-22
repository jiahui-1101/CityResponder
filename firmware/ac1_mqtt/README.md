# AC1 MQTT actuator firmware

This is separate from `firmware/ac1_bringup`, which remains the manual-only
hardware diagnostic firmware. It consumes the existing generic actuator
contract on `city/commands/AC1` and publishes correlated ACKs on
`city/acks/AC1`, both at QoS 1 and non-retained.

The local `include/secrets.h` must define the same four fields as
`include/secrets.example.h`. During local bring-up, the source also accepts
the existing ignored SN1 secrets file so credentials are never copied into
the repository. No credentials belong in Git.

Supported production actions are TRAFFIC/ALL_RED, route-aware
TRAFFIC/GREEN_CORRIDOR, TRAFFIC/NORMAL_CYCLE, TRAFFIC/OFF,
BUZZER/ON, OFF, or PULSE_500_MS, and the calibrated GATE/OPEN or GATE/CLOSE
actions. GREEN_CORRIDOR requires `parameters.corridor` to be `PRIMARY`
(TL1) or `STANDBY` (TL2). NORMAL_CYCLE uses four-second green and one-second
yellow phases. The authoritative hardware map currently has no GPIO assignment
for the master contract's amber affected-zone indicator; no pin is invented here.
The verified gate angles remain CLOSED=30° and OPEN=120°; servo validation is
deferred pending replacement and this traffic-only change does not actuate it.
