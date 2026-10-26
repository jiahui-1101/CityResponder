# AC1 MQTT actuator firmware

The serial port is selected per session after checking the connected USB
device. COM7 is historical; on 2026-10-26 the user identified the only
connected ESP32 as AC1 and Windows/PlatformIO listed its CP2102 adapter on
COM5. One authorized, receive-only COM5 session produced AC1-specific MQTT
logs, confirming the device identity; no startup/version banner was observed.
The monitor baud rate is 115200. Opening the port may reset the ESP32, so
confirm output power state and obtain operator approval before monitoring if
actuation on reset is possible. An upload requires separate explicit approval.

This is separate from `firmware/ac1_bringup`, which remains the manual-only
hardware diagnostic firmware. It subscribes to the existing generic actuator
contract on `city/commands/AC1` at QoS 1 and publishes correlated messages on
`city/acks/AC1` at QoS 0, non-retained. PubSubClient cannot publish QoS 1; ACK
delivery is therefore best-effort and the backend's command-correlated ACK
timeout is still required. The backend waits for broker confirmation of its
QoS 1 command publish, which confirms broker receipt only.

The backend command envelope is:

```json
{"command_id":"<uuid>","node_id":"AC1","command_type":"PHYSICAL_ACTION","payload":{"action_category":"TRAFFIC","action_type":"GREEN_CORRIDOR","parameters":{"corridor":"PRIMARY"},"spec_id":"<spec>","source_recommendation_id":null,"attempt_number":1,"safe_default":false},"timestamp":"<UTC ISO-8601>"}
```

For a supported command, firmware first publishes a `status=RECEIVED`,
`stage=received` message after validation. After issuing the GPIO/PWM output
call it publishes `status=ACK`, `stage=execution_reported`, with matching
action fields and a result (`OUTPUT_SET` or `TARGET_COMMANDED`). A rejection
uses `status=REJECTED`, `stage=failed`, and a reason. An execution report does
not prove a relay changed, a servo moved, or the PE07 gate reached its target.

Firmware suppresses duplicate IDs across a rolling 32-command RAM window and
rejects an ID reused for a different action. The cache clears on ESP32 restart;
the backend therefore does not retry gate motion, normal-cycle restarts, or
timed buzzer pulses after an ACK timeout. Only desired-state traffic and
buzzer ON/OFF actions are eligible for one same-ID retry.

Create the ignored AC1-specific `include/secrets.h` from
`include/secrets.example.h` and fill in the Wi-Fi, broker, and AC1 MQTT
credentials supplied by the operator. The AC1 MQTT identity needs permission
to read `city/commands/AC1` and write `city/acks/AC1`. The backend needs a
separate identity permitted to write commands and read ACKs. The firmware no
longer inherits SN1's local secrets. A build without AC1 MQTT credentials is
valid for compile checks but will not connect to the broker. Serial startup
reports only whether Wi-Fi and MQTT configuration is present, without
printing credentials. The currently installed reversed-mapping image reports
`ack_protocol_version=AC1_ACK_V4_REVERSED_GATE_20261026`; the prior V3 image
reported `AC1_ACK_V3_SG90_SAFE_20261026`. No credentials belong in Git.

Supported actions are TRAFFIC/ALL_RED, route-aware TRAFFIC/GREEN_CORRIDOR,
TRAFFIC/NORMAL_CYCLE, TRAFFIC/OFF, BUZZER/ON, BUZZER/OFF,
BUZZER/PULSE_500_MS, and GATE/OPEN or GATE/CLOSE. GREEN_CORRIDOR requires
`parameters.corridor` to be `PRIMARY` (TL1) or `STANDBY` (TL2). NORMAL_CYCLE
uses four-second green and one-second yellow phases. The authoritative
hardware map currently has no GPIO assignment for the master contract's amber
affected-zone indicator; no pin is invented here. The prior V3 gate targets
were CLOSED=30° and OPEN=120°. The installed V4 mapping reverses those targets
to OPEN=30° and CLOSE=120°. Gate-position feedback is not implemented.

The Phase 4.1F servo control uses GPIO18 at 50 Hz and the SG90 nominal
1000–2000 µs pulse interval. In the prior V3 image, OPEN=120° (about
1666 µs) and CLOSE=30° (about 1166 µs). The first linked OPEN test moved the
gate downward although physical OPEN is raised. The operator stopped, cut
servo power, returned the gate to CLOSED, and detached the linkage. The V4
source swaps only the gate target mapping: OPEN=30° (about 1166 µs) and
CLOSE=120° (about 1666 µs). The V4 unloaded OPEN test moved the horn in the
opposite direction, and the operator explicitly confirms 30° corresponds to
physical OPEN. An earlier claim that 30° aligned with physical CLOSED was an
incorrect interpretation of the detached linkage and the separately secured
gate. A later separately authorized unloaded V4 CLOSE test moved the horn to
120° and the operator confirmed, with SG90 power off, that the detached
linkage naturally meets that target at physical CLOSED without preload or
force. Under separate approvals, the linkage was then reattached at CLOSED
and one linked V4 OPEN→CLOSE cycle passed with broker confirmation, real
two-stage AC1 ACKs, and operator-observed fully OPEN and CLOSED positions.
The final gate was confirmed CLOSED with SG90 power off and linkage attached.
This single supervised cycle does not verify repeated endurance or unattended
position safety. Gate commands do not
accept caller-supplied position parameters. The first gate command attaches
PWM; startup leaves the servo unattached, and PWM remains attached after a
gate command. A terminal `TARGET_COMMANDED` ACK means a PWM target was issued,
not that the gate reached a measured position. The V4 upload was separately
authorized with servo power off and linkage detached. Every further physical
gate movement requires separate authorization and operator observation.
Unattended production gate use remains blocked without independent position
feedback and a reviewed fail-safe procedure.
