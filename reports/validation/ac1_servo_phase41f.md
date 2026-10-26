# Phase 4.1F — AC1 servo and gate audit (2026-10-26)

## Scope and current decision

This phase completed the hardware/source audit, servo protocol repair,
isolated tests, and separately authorized V3 and V4 COM5 uploads. The V3
linked `GATE/OPEN` moved downward and failed physically, despite real ACKs.
The operator cut SG90 power and stopped. The operator-requested V4 reversal
maps OPEN=30° and CLOSE=120°. Under separate approval for each step, V4 passed
unloaded target checks, power-off endpoint fit checks, and one linked
OPEN→CLOSE cycle with real two-stage ACKs and operator-observed positions.
The final observed tabletop state is gate fully CLOSED with linkage attached,
SG90 power OFF, both red LEDs on, other traffic LEDs off, and buzzer silent.
No independent position sensor has been verified; unattended production use
remains blocked.

## Hardware and firmware audit

| Item | Evidence and result |
| --- | --- |
| Servo | Operator reads label as micro servo SG90; replacement installed. Manufacturer/authenticity not independently verified. |
| Supply | Operator reports SG90 VCC on the AC1 USB-fed VIN/5V rail, shared AC1 GND, and rail stable under servo load. No voltage/current trace was collected in this phase. Power is not supplied by ESP32 GPIO. |
| Signal | Operator reports SG90 signal alone on GPIO18. Hardware reference assigns GPIO18; traffic uses 14, 13, 23, 25, 26, 27 and buzzer uses 19. GPIO18 is not an ESP32 boot strap pin. No other AC1 PWM peripheral found. |
| Linkage | Initially attached to a CLOSED gate. Operator confirmed the path clear and free, can directly observe gate and horn, then disconnected the linkage with servo power off and gate secured CLOSED. Servo is now mechanically unloaded per operator. |
| Installed image | One separately authorized V3 upload to COM5 passed PlatformIO/esptool verification. A receive-only 20-second COM5 session at 115200 baud with DTR/RTS low displayed `AC1_ACK_V3_SG90_SAFE_20261026`, safe startup, Wi-Fi at <PRIVATE_LAN_IP>, and MQTT subscription to `city/commands/AC1`. The operator reported no unexpected change during upload/observation. |
| V2 servo source | ESP32Servo 3.2.1 on GPIO18. Library default attach range is 544–2400 µs at 50 Hz; `write(30)` maps near 853 µs and `write(120)` near 1781 µs. First gate command attaches PWM; setup leaves GPIO18 INPUT/unattached. Servo remains attached after a command. `TARGET_COMMANDED` is not position proof. |
| Staged V3 source | Explicit 50 Hz, nominal SG90 control range 1000–2000 µs. Existing 30° and 120° targets map to 1166 and 1666 µs in the new source, still uncalibrated. Rejects gate position parameters and invalid actions; reports failed attach as FAILED. Startup remains unattached. |
| Sensor | No independent gate limit switch, encoder, or position signal is present in the AC1 hardware map or firmware. SG90 internal feedback is not exposed as AC1 position telemetry. |

The hardware reference treats USB/VIN servo power as provisional and calls for
regulated external servo power with common ground if load causes brownout.
The operator reports the current rail was verified stable under load. The
hardware README says angles must be measured on the prototype. The staged
nominal pulse bounds do not establish safe mechanical endpoints or guarantee
that this particular SG90 accepts them without binding.

## MQTT contract and safety

Real contract: backend publishes non-retained QoS 1 `PHYSICAL_ACTION` on
`city/commands/AC1` with a UUID `command_id`, `node_id=AC1`, and
`payload.action_category=GATE`, `payload.action_type=OPEN` or `CLOSE`, and
empty `parameters`. AC1 subscribes at QoS 1 and publishes correlated
`RECEIVED/received`, then `ACK/execution_reported` with
`result=TARGET_COMMANDED`, or a terminal failure/rejection, on `city/acks/AC1`.
PubSubClient ACK publish is QoS 0. Broker confirmation proves broker receipt;
AC1 ACK proves firmware reporting; neither proves gate position.

The backend rejects caller-supplied gate positions, and `_is_retry_safe`
excludes gate commands. After missing/late ACK or uncertain broker publish,
gate outcome remains unknown and the backend does not automatically resend.
Firmware suppresses duplicate IDs across its most recent 32 applied commands
in RAM. That memory clears on ESP32 restart. MQTT uses a clean session, broker
persistence is disabled, and the prior broker check found no retained commands;
these reduce replay risk but do not create a hard interlock. Production
orchestration can still generate GATE/CLOSE safe defaults and GATE/OPEN
recommendations; keep physical gate operation out of production until
calibration, physical verification, and any required operational interlock are
complete.

## Isolated software checks (no broker or hardware)

| Test | Result | Evidence / limit |
| --- | --- | --- |
| S01 valid OPEN | PASS | Native contract parse and target test; backend spec test. |
| S02 valid CLOSE | PASS | Native contract parse and target test; backend spec test. |
| S03 unsupported position | PASS | Native parameter-count and backend position/angle/pulse rejection tests; firmware source rejects any nonempty gate parameters. |
| S04 invalid command | PASS | Native invalid-action cases and firmware validation branch. |
| S05 duplicate command | PARTIAL | Firmware 32-ID cache and mismatch rejection reviewed statically; backend duplicate terminal ACK test passes. Actual ESP32 callback was not host-executed. |
| S06 missing ACK | PASS | Isolated backend timeout test. |
| S07 late ACK | PASS | Isolated backend late-ACK test. |
| S08 wrong command ID | PASS | Isolated backend unknown-ID rejection test. |
| S09 MQTT reconnect | PARTIAL | Isolated backend resubscription test passes; AC1 V3 boot connected to MQTT, but an induced reconnect was not tested. |
| S10 firmware startup | PASS | Source setup leaves servo unattached and GPIO18 INPUT; V3 serial startup marker reports SERVO_UNATTACHED and operator observed no motion. |
| S11 PWM bounds | PASS | Native test verifies 50 Hz, 1000–2000 µs, target mappings; physical mechanical safety remains unverified. |
| S12 no automatic gate retry | PASS | Isolated backend lost-ACK/device-restart test confirms one publish and execution unknown. |

Native host test compiled with `g++ -std=c++11 -Wall -Wextra -Werror` and
passed. Focused isolated backend suite: **32 passed**. PlatformIO `esp32dev`
build: **PASS**. Reviewed V3 firmware image SHA-256:
`ECBEDD299188EC12472F58A650F4ACBD40A863DE1CAB9768841A7F2295749E46`.
The build artifact and logs remain local, outside Git. One authorized COM5
upload succeeded with flash hashes verified; the subsequent local binary hash
matched the reviewed image. Mosquitto remained Running, and read-only TCP
enumeration showed established AC1 (`<PRIVATE_LAN_IP>`) and loopback broker
connections. No secrets or credential values are recorded here.

## Authorized unloaded hardware observations

The operator authorized reconnecting SG90 power while its linkage was
detached and the gate secured CLOSED. The operator saw no unexpected horn
movement, buzzing, heat, AC1 reset, or other output change; power remained on.
Each subsequent unloaded command had its own separate authorization. The
backend service published each exactly once, non-retained at QoS 1, with
broker confirmation and AC1 real correlated ACK events:

| Command | ID | AC1 ACK | Operator observation |
| --- | --- | --- | --- |
| `GATE/CLOSE` (30°, nominal 1166 µs) | `3eb838fa-f41c-479e-99ac-587b9f4bf182` | `RECEIVED/received`; `ACK/execution_reported`, `TARGET_COMMANDED` | Detached horn moved and settled; gate stayed CLOSED; no unexpected behavior. |
| `GATE/OPEN` (120°, nominal 1666 µs) | `408711c7-cc49-46ae-9695-16dd4a62d384` | `RECEIVED/received`; `ACK/execution_reported`, `TARGET_COMMANDED` | Detached horn moved to opposite target and settled; gate stayed CLOSED; no unexpected behavior. |
| `GATE/CLOSE` (return for alignment, 30°, nominal 1166 µs) | `a8a4806e-bc79-47f4-956a-7491f4868dbf` | `RECEIVED/received`; `ACK/execution_reported`, `TARGET_COMMANDED` | Detached horn moved back and settled; gate stayed CLOSED; no unexpected behavior. |

No application retry occurred. These observations verify the servo responds
to both PWM targets while unloaded. They do not calibrate the angles to the
gate's mechanical endpoints or verify linked gate OPEN/CLOSE. The operator
then disconnected SG90 power; the unloaded horn stayed at the OPEN target.
The operator separately authorized one manual unpowered movement of the
detached gate to its OPEN stop, secured the gate OPEN, and found the linkage
naturally aligned with the stationary horn at the OPEN target without binding
or unexpected behavior. They then separately authorized a manual return to
CLOSED, secured it without binding, and reconnected SG90 power with no
unexpected change while the linkage stayed detached. A separately authorized
unloaded CLOSE command returned the horn to 30°, and the operator cut SG90
power. The earlier responses were interpreted as 30° aligning with physical
CLOSED; the operator later explicitly corrected this: **30° corresponds to
physical OPEN**. The previous CLOSED alignment claim is invalid and must not
be used to infer the V4 linked range. No application retry occurred.

## Linked OPEN test — stopped on physical failure

The operator reattached the linkage at CLOSED without force and authorized a
stationary linked power-on check. Gate remained fully CLOSED with no issue.
They then separately authorized **one** linked `GATE/OPEN` from CLOSED.
Backend health and AC1 broker connection were checked before publication.
Command `6164387c-f388-454c-97ba-c12f3d1b9a34` was published once with
broker confirmation. AC1 returned matching `RECEIVED/received` and
`ACK/execution_reported`, `TARGET_COMMANDED`. The operator saw the gate move
**downward into another position when it was expected to rise**, so physical
OPEN verification **FAILED** despite the valid ACK. The operator was
instructed to disconnect SG90 power immediately and not send a blind CLOSE.
They confirmed servo power OFF, then manually returned the gate to CLOSED and
reported no strain. They then detached the linkage freely with SG90 power
still OFF and gate secured CLOSED. No further physical command was sent.

The source assigns OPEN=120° and CLOSE=30°, but documentation does not define
which SG90 rotation direction raises the actual linked gate. The unexpected
motion is consistent with reversed linkage/target orientation or a misleading
static alignment check; the exact mechanical cause is not yet established.
The later V4 target swap is an operator-requested hypothesis, not proof of
safe mechanical alignment.

## V4 reversal hypothesis and unloaded test

At the operator's subsequent explicit direction, the source was
changed to OPEN=30° and CLOSE=120° while retaining GPIO18, 50 Hz,
1000–2000 µs bounds, MQTT topics, ACK behavior, traffic and buzzer code.
Startup reports `AC1_ACK_V4_REVERSED_GATE_20261026` and prints the target
angles from the constants. Native gate-contract checks passed; the focused
isolated backend ACK suite passed 32 tests; PlatformIO `esp32dev` build passed.
V4 image SHA-256:
`1953E25BB3C5A8EC0084CC240E2EC89156D52CB866879AA16053FD586E4F73E9`.
One separately authorized V4 upload to COM5 passed PlatformIO/esptool flash
verification. A receive-only 20-second COM5 serial session at 115200 baud
with DTR/RTS low showed `AC1_ACK_V4_REVERSED_GATE_20261026`,
`SERVO_UNATTACHED`, Wi-Fi at `<PRIVATE_LAN_IP>`, and MQTT subscription to
`city/commands/AC1`. The operator reported no unexpected change during
upload/monitoring and confirmed SG90 power OFF, linkage detached, gate
secured CLOSED. Installed AC1 is now V4.

With separate approval, the operator reconnected SG90 power while the linkage
stayed detached and gate secured CLOSED. No issue occurred at power-on; the
horn was at the earlier 120° target. The backend then published **one** V4
unloaded `GATE/OPEN`, command `74741c74-1a74-42ab-b6ef-2eef55cbbe29`,
with broker confirmation and real correlated AC1 `RECEIVED/received` plus
`ACK/execution_reported`, `TARGET_COMMANDED`. No retry occurred. The operator
observed the horn move opposite the prior 30°→120° rotation and settle
normally; the detached gate remained CLOSED with no unexpected behavior.
The operator then disconnected SG90 power. Their later explicit correction
states that the V4 30° target corresponds to **physical OPEN**, not CLOSED.
The earlier CLOSED alignment interpretation is invalid because it conflated
the separately secured gate's position with the detached horn's target and
linkage alignment. This supports V4 OPEN=30° and makes the reversal plausible.
At that stage, V4 CLOSE=120° and linked travel remained unverified; no
linked V4 command had been sent.

Under a later separate authorization, the operator performed **one** unloaded
V4 `GATE/CLOSE` from the observed 30° horn target to 120°: command
`ab347054-8ed4-4c7d-bef2-4d08aba2564d`. Broker confirmation and real AC1
`RECEIVED/received` and `ACK/execution_reported`, `TARGET_COMMANDED`, passed.
No retry occurred. The operator saw the detached horn move to 120° and settle,
with the separately secured gate CLOSED and no unexpected behavior. After
cutting SG90 power, they confirmed the horn did not shift and the detached
linkage's attachment point naturally meets the 120° horn while the gate is
physically CLOSED, without preload or force. This supports the V4 CLOSE
endpoint **statically**. Linked movement was still untested at that stage.

## Linked V4 validation and final state

The operator separately authorized reattachment at the 120° CLOSE fit with
SG90 power OFF. They reported the linkage attached freely without force or
preload and the gate remained physically CLOSED. A separately authorized
stationary power-on check held CLOSED without binding, buzzing, heating,
reset, or other output change. The operator confirmed the gate was free to
rise; no latch or restraint blocked it.

Under a separate one-command approval, the backend published V4 `GATE/OPEN`
`17a881c8-7f6d-47a4-9426-0f28e2ac45b5` once. Broker confirmation passed;
AC1 returned real matching `RECEIVED/received` and `ACK/execution_reported`,
`TARGET_COMMANDED`. The operator observed the linked gate rise smoothly from
CLOSED to fully OPEN with no unexpected behavior. No retry or automatic
CLOSE occurred. The servo remained powered at the OPEN target.

Under a further separate approval, the backend published V4 `GATE/CLOSE`
`0494ec4e-5e65-4b26-89d1-562ab299fcc7` once. Broker confirmation and
the same two real AC1 ACK stages passed. The operator observed a smooth
return to fully CLOSED with no binding, sustained buzzing, heat, reset, or
traffic/buzzer change. The operator then separately authorized SG90 power-off
and confirmed the gate stayed fully CLOSED with linkage attached. They
confirmed exact ALL_RED lights, buzzer silent, and no unexpected change.
Read-only final checks found Mosquitto Running, AC1 broker TCP Established,
and backend `/health` healthy. No further hardware command is needed for
this single supervised OPEN/CLOSE validation. ACKs remain distinct from
operator position observation; no independent position feedback exists.

The authorized V3 upload had reset traffic LEDs to OFF. The operator confirmed
all six were dark and the buzzer silent. Under separate authorization, the
backend published one `TRAFFIC/ALL_RED` restore,
`12269cf9-a247-46ef-86ea-71b16767ac78`, with broker confirmation. AC1
returned matching real `RECEIVED/received` and `ACK/execution_reported`,
`OUTPUT_SET`. The operator confirmed both reds on, all yellow/green off,
buzzer silent, gate secured CLOSED, SG90 power OFF, linkage detached, and no
unexpected behavior. This was the observed state after the V3 test. The later
V4 upload reset traffic LEDs to OFF again. The operator observed them dark,
then separately authorized one V4 `TRAFFIC/ALL_RED` restore,
`68106dcc-2c93-4f8a-8fe7-8b42120f0431`, which was broker-confirmed with
real correlated `RECEIVED/received` and `ACK/execution_reported`,
`OUTPUT_SET`. The operator confirmed both reds on, all yellow/green off,
buzzer silent, gate secured CLOSED, SG90 power OFF, linkage detached, and no
unexpected change. The subsequent linked V4 tests left those lights and
buzzer unchanged, and the operator reconfirmed them at final power-off.

## Requested result fields

SERVO_MODEL=SG90 (operator label; PARTIAL identification)

SERVO_POWER_CONFIGURATION=PARTIAL (USB-fed VIN/5V, common ground, stable under load per operator)

SERVO_GPIO=PASS (GPIO18 by source and operator wiring report)

PWM_CONFIGURATION=PARTIAL (V4 installed; commanded pulse width not independently measured)

OPEN_POSITION_CONFIGURATION=PASS (V4 OPEN=30°; operator observed linked gate fully OPEN)

CLOSE_POSITION_CONFIGURATION=PASS (V4 CLOSE=120°; operator observed linked gate fully CLOSED)

GPIO_CONFLICT_CHECK=PASS (source map and ESP32 pin review)

FIRMWARE_BUILD=PASS (V3 compiled, uploaded once, startup marker observed)

V4_FIRMWARE_BUILD=PASS (reversed mapping compiled; native and backend tests passed)

V4_UPLOAD=PASS (one authorized COM5 upload; V4 serial marker and Wi-Fi/MQTT connection observed)

V4_UNLOADED_DIRECTION=PASS (opposite rotation observed; command `74741c74-1a74-42ab-b6ef-2eef55cbbe29`)

V4_MECHANICAL_ALIGNMENT=PASS (static fits and one supervised linked OPEN→CLOSE cycle operator-confirmed)

V4_CLOSE_120_STATIC_ALIGNMENT=PASS (operator reports natural linkage fit at physical CLOSED with power OFF)

V4_LINKED_GATE_TEST=PASS (one supervised linked OPEN and CLOSE, real ACKs and operator positions)

V4_REVERSAL_FIX=PASS (wrong direction corrected in one supervised linked OPEN→CLOSE cycle)

MQTT_GATE_CONTRACT=PASS (broker confirmation and real correlated two-stage ACK for V3 and V4 test commands)

REAL_ACK=PASS (including linked `GATE/OPEN`; ACK does not establish physical position)

GATE_OPEN_ACK=PASS (V4 linked command `17a881c8-7f6d-47a4-9426-0f28e2ac45b5`)

GATE_CLOSE_ACK=PASS (V4 linked command `0494ec4e-5e65-4b26-89d1-562ab299fcc7`)

GATE_OPEN_OPERATOR_VERIFIED=PASS (V4 fully OPEN; V3 failure remains in history)

GATE_CLOSE_OPERATOR_VERIFIED=PASS (V4 fully CLOSED)

SERVO_MOVEMENT=PASS (operator-observed unloaded motion to both targets)

GATE_MECHANICAL_OPERATION=PASS (one supervised V4 OPEN→CLOSE cycle; no binding reported)

GATE_FINAL_SAFE_STATE=PASS (operator confirmed fully CLOSED, linkage attached, SG90 power OFF, exact ALL_RED, buzzer silent)

DUPLICATE_COMMAND_SAFETY=PARTIAL (static firmware review and mock ACK test)

RETRY_SAFETY=PASS (mock timeout test; no gate resend)

PE07_POSITION_FEEDBACK=NOT_AVAILABLE

BACKEND_TESTS=PASS (32 isolated focused tests)

AC1_CONNECTION=PASS (V4 serial Wi-Fi/MQTT logs and final established broker TCP connection)

TRAFFIC_FINAL_STATE=PASS (V4 ALL_RED command `68106dcc-2c93-4f8a-8fe7-8b42120f0431`; operator confirmed exact state)

BUZZER_FINAL_STATE=PASS (operator confirmed silent)

PRODUCTION_SAFETY=BLOCKED (one supervised cycle does not establish unattended safety; no independent position feedback)

COMMAND_ID=`3eb838fa-f41c-479e-99ac-587b9f4bf182`; COMMAND=`GATE/CLOSE`;
EXPECTED_GATE_POSITION=CLOSED (gate secured, detached);
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS;
OPERATOR_OBSERVATION=HORN_MOVED, GATE_CLOSED, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_UNLOADED_SERVO_ONLY.

COMMAND_ID=`6164387c-f388-454c-97ba-c12f3d1b9a34`; COMMAND=`GATE/OPEN`;
EXPECTED_GATE_POSITION=FULLY_OPEN_RAISED;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_TARGET_COMMANDED;
OPERATOR_OBSERVATION=MOVED_DOWN_WRONG_DIRECTION, POWER_OFF, MANUALLY_RETURNED_CLOSED_NO_STRAIN;
FINAL_RESULT=FAIL_PHYSICAL_OPEN_STOPPED_NO_RETRY.

COMMAND_ID=`12269cf9-a247-46ef-86ea-71b16767ac78`; COMMAND=`TRAFFIC/ALL_RED`;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_OUTPUT_SET;
OPERATOR_OBSERVATION=BOTH_REDS_ON_OTHERS_OFF_BUZZER_SILENT_GATE_CLOSED_SERVO_POWER_OFF_LINKAGE_DETACHED;
FINAL_RESULT=PASS_SAFE_TRAFFIC_RESTORE.

COMMAND_ID=`74741c74-1a74-42ab-b6ef-2eef55cbbe29`; COMMAND=`GATE/OPEN` (V4, unloaded);
EXPECTED_HORN_TARGET=30_DEGREES_PHYSICAL_OPEN_ALIGNMENT_PER_OPERATOR;
ACTUAL_GATE_POSITION=CLOSED_SECURED_LINKAGE_DETACHED;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_TARGET_COMMANDED;
OPERATOR_OBSERVATION=HORN_MOVED_OPPOSITE_TO_30_DEGREES, GATE_CLOSED, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_UNLOADED_DIRECTION, PARTIAL_OPEN_ALIGNMENT_OPERATOR_CONFIRMED.

COMMAND_ID=`ab347054-8ed4-4c7d-bef2-4d08aba2564d`; COMMAND=`GATE/CLOSE` (V4, unloaded);
EXPECTED_HORN_TARGET=120_DEGREES_PHYSICAL_CLOSED_ALIGNMENT;
ACTUAL_GATE_POSITION=CLOSED_SECURED_LINKAGE_DETACHED;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_TARGET_COMMANDED;
OPERATOR_OBSERVATION=HORN_MOVED_TO_120_AND_SETTLED, NO_UNEXPECTED_BEHAVIOR, POWER_OFF_120_FITS_PHYSICAL_CLOSED_WITHOUT_FORCE;
FINAL_RESULT=PASS_UNLOADED_SERVO_AND_STATIC_CLOSED_ALIGNMENT.

COMMAND_ID=`17a881c8-7f6d-47a4-9426-0f28e2ac45b5`; COMMAND=`GATE/OPEN` (V4, linked);
EXPECTED_GATE_POSITION=FULLY_OPEN_RAISED;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_TARGET_COMMANDED;
OPERATOR_OBSERVATION=SERVO_MOVED, GATE_FULLY_OPEN, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_LINKED_OPEN_OPERATOR_VERIFIED.

COMMAND_ID=`0494ec4e-5e65-4b26-89d1-562ab299fcc7`; COMMAND=`GATE/CLOSE` (V4, linked);
EXPECTED_GATE_POSITION=FULLY_CLOSED;
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_TARGET_COMMANDED;
OPERATOR_OBSERVATION=SERVO_MOVED, GATE_FULLY_CLOSED, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_LINKED_CLOSE_OPERATOR_VERIFIED.

FINAL_POWER_STATE=SG90_OFF_OPERATOR_CONFIRMED;
FINAL_LINKAGE=ATTACHED;
FINAL_GATE_POSITION=FULLY_CLOSED_OPERATOR_CONFIRMED;
FINAL_TRAFFIC=ALL_RED_OPERATOR_CONFIRMED;
FINAL_BUZZER=SILENT_OPERATOR_CONFIRMED.

COMMAND_ID=`68106dcc-2c93-4f8a-8fe7-8b42120f0431`; COMMAND=`TRAFFIC/ALL_RED` (V4);
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS_OUTPUT_SET;
OPERATOR_OBSERVATION=BOTH_REDS_ON_OTHERS_OFF_BUZZER_SILENT_GATE_CLOSED_SERVO_POWER_OFF_LINKAGE_DETACHED;
FINAL_RESULT=PASS_SAFE_TRAFFIC_RESTORE.

COMMAND_ID=`408711c7-cc49-46ae-9695-16dd4a62d384`; COMMAND=`GATE/OPEN`;
EXPECTED_GATE_POSITION=CLOSED (gate secured, detached);
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS;
OPERATOR_OBSERVATION=HORN_MOVED, GATE_CLOSED, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_UNLOADED_SERVO_ONLY.

COMMAND_ID=`a8a4806e-bc79-47f4-956a-7491f4868dbf`; COMMAND=`GATE/CLOSE`;
EXPECTED_GATE_POSITION=CLOSED (gate secured, detached);
RECEIVED_ACK=PASS; TERMINAL_ACK=PASS;
OPERATOR_OBSERVATION=HORN_MOVED, GATE_CLOSED, NO_UNEXPECTED_BEHAVIOR;
FINAL_RESULT=PASS_UNLOADED_SERVO_ONLY.

AC1_SERVO_CONTROL_READY=YES (supervised testing only)

AC1_GATE_OPEN_VERIFIED=YES (operator observed linked V4 OPEN)

AC1_GATE_CLOSE_VERIFIED=YES (operator observed linked V4 CLOSE)

AC1_GATE_DEMO_READY=PARTIAL (supervised gate demo verified once; unattended use and independent feedback unverified)
