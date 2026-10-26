# CityResponder Phase 4.1 AC1 ACK Audit

**Audit date:** 2026-10-26
**Scope:** AC1 command/ACK software and firmware contract only
**Current branch:** `integration/cityresponder-phase2-phase36`
**Physical commands sent during this audit:** none

## Acceptance status

```text
ACK_PROTOCOL_AUDIT=PASS
AC1_FIRMWARE_ACK=PARTIAL
MQTT_COMMAND_PUBLISHER=PASS
MQTT_ACK_SUBSCRIBER=PASS
COMMAND_ID_CORRELATION=PASS
ACK_VALIDATION=PASS
ACK_TIMEOUT=PASS
ACK_RETRY_SAFETY=PASS
DUPLICATE_ACK_HANDLING=PASS
RECONNECT_HANDLING=PASS
BACKEND_STATE_UPDATE=PASS
AUDIT_TRAIL=PASS
DASHBOARD_ACK_STATUS=PASS
SIMULATED_ACK_ISOLATION=PARTIAL
FIRMWARE_BUILD=PASS
ISOLATED_MQTT_TESTS=PASS
BACKEND_TESTS=PASS
REAL_AC1_CONNECTION=NOT_VERIFIED
REAL_AC1_ACK=DEFERRED
PHYSICAL_EXECUTION=NOT_VERIFIED
PHYSICAL_EXECUTION_FEEDBACK=NOT_VERIFIED
PE07_GATE_POSITION_FEEDBACK=DEFERRED
PRODUCTION_SAFETY=PARTIAL
SOFTWARE_ACK_PIPELINE=PASS
```

`SOFTWARE_ACK_PIPELINE=PASS` refers to the compiled firmware contract, backend correlation and state handling, and isolated in-memory transport tests. It does not claim that the current firmware was uploaded or exercised on an ESP32.

## Architecture found

- The backend creates an `ActuatorCommand` with a UUID `command_id`, `node_id`, `command_type`, action payload, and UTC timestamp. It publishes AC1 commands to `city/commands/AC1` at QoS 1, non-retained.
- The backend now waits up to two seconds for the MQTT broker's QoS 1 publish confirmation. That confirms broker acceptance only. It does not prove AC1 received the command.
- The FastAPI lifespan subscribes to `city/acks/#` at QoS 1. The exact AC1 ACK topic is `city/acks/AC1`.
- AC1 uses PubSubClient. It subscribes to `city/commands/AC1` at QoS 1 and publishes ACK messages at QoS 0, non-retained. The prior firmware README incorrectly stated that ACK publication used QoS 1; this is corrected. PubSubClient only supports QoS 0 publication.
- The `command_id` is the correlation ID; there is no separate `correlation_id` field. The backend also checks the ACK topic/device, expected command node, and optional action fields.

### Wire payloads

Backend command envelope, with route fields optional:

```json
{
  "command_id": "<uuid>",
  "node_id": "AC1",
  "command_type": "PHYSICAL_ACTION",
  "payload": {
    "action_category": "TRAFFIC",
    "action_type": "GREEN_CORRIDOR",
    "parameters": {"corridor": "PRIMARY"},
    "spec_id": "<spec>",
    "source_recommendation_id": null,
    "attempt_number": 1,
    "safe_default": false
  },
  "timestamp": "<UTC ISO-8601>"
}
```

Supported commands produce two firmware messages. `RECEIVED`/`received` follows validation; `ACK`/`execution_reported` follows the GPIO/PWM output call. The latter includes matching action fields and a result such as `OUTPUT_SET`, `TARGET_COMMANDED`, or `DUPLICATE_SUPPRESSED`. Unsupported or invalid actions produce `REJECTED`/`failed` with a reason. Legacy `status=ACK` messages without a stage remain accepted as execution reports.

The firmware's `execution_reported` status means its output call returned. It is not independent physical feedback. Gate position, traffic lamp state, and buzzer state have no backend feedback sensor contract. The firmware timestamp falls back to 1970-01-01 when NTP is unavailable, so it is not used as proof of freshness.

## Defects repaired

1. The backend previously treated any schema-valid ACK status, including `REJECTED`, as successful completion. It now waits past the `RECEIVED` stage and treats only terminal execution ACKs as success; terminal failures return failure.
2. The subscriber previously trusted the payload `node_id` without requiring the matching topic and did not check that the ACK mapped to a stored command. It now checks topic/device, command ID, node ID, action fields when present, ordering, terminal status, duplicates, and simulation markers. Rejected messages are recorded separately and cannot update command state.
3. The MQTT publisher previously did not wait for broker QoS 1 confirmation. It now records broker confirmation separately from device receipt. A publish-confirmation timeout is marked `execution_unknown` and is never resent automatically.
4. The command service previously wrote a second `actuator_command` for a retry using the same ID. Retries now have their own `actuator_command_retry` event, while the original command remains the projection anchor.
5. A timeout previously retried every action. One same-ID retry is now limited to desired-state traffic (`ALL_RED`, `GREEN_CORRIDOR`, `OFF`) and buzzer `ON`/`OFF`. Gate motion, `NORMAL_CYCLE`, and `PULSE_500_MS` are not resent after an ACK timeout and become `execution_unknown`. The existing safe-default path remains one-shot after both retries of a retry-safe command fail.
6. AC1 previously marked an ID applied before validating the requested operation and remembered only one ID. It now validates before receipt, reports `RECEIVED` then `execution_reported`, records successful IDs in a 32-command RAM window, suppresses duplicate actions, and rejects reuse of an ID for a different action. The cache is volatile and clears on ESP32 restart.
7. The mock actuator previously listened and published on production `city/...` topics, allowing simulated ACKs to collide with real traffic. It now refuses that prefix, uses isolated `cityresponder/test/...` topics, and marks simulated payloads; the production ACK handler rejects those markers.
8. Dashboard projections now distinguish broker-confirmed publish, device receipt, execution report, failure, timeout, and unknown execution. They always show physical state as unverified, and current device connection is not inferred from ACK history.

## Tests and build

- `backend/tests/test_actuator_ack_pipeline.py`: **27 passed**. The isolated cases cover publish confirmation; receipt and terminal ACK stages; missing, late, duplicate, unknown, stale, wrong-device, malformed, out-of-order, failed, unsupported, mismatched-action, and simulated ACKs; broker disconnect and confirmation timeout; reconnect subscription; backend restart with persisted events; restart uncertainty for gate commands; command-ID retry auditing; projection semantics; and an end-to-end fake AC1 flow through the backend service, handler, waiter, event store, and dashboard projection.
- Full backend suite: **198 passed**, one existing Starlette/httpx deprecation warning.
- Frontend regression suite: **all six contracts passed**, including simulation, route geometry/image, live vision, and refresh checks.
- Frontend TypeScript and production build: **passed**.
- AC1 PlatformIO compile: **passed** (`esp32dev`; PlatformIO 6.2.0; ESP32 Arduino; PubSubClient 2.8.0; ArduinoJson 7.4.3; ESP32Servo 3.2.1). No upload was performed. The AC1 local `secrets.h` was absent; a later Phase 4.1B audit found that the source could inherit SN1's ignored secrets, so the credential source of this earlier image was not established.
- `git diff --check`: **passed**; Git printed its existing LF/CRLF conversion notices.
- Automated tests used an in-memory SQLite store and an in-memory MQTT publisher/AC1 responder. They did not connect to a broker or publish to a live actuator.

## Hardware evidence and readiness

This audit did not observe a live AC1. The runtime configuration is `production`, MQTT points to `127.0.0.1:1883`, that TCP endpoint was unreachable, MQTT username/password are not configured, and the configured PlatformIO COM7 port was not present (enumerated ports were COM3, COM4, and COM5). No passive AC1 heartbeat/status topic exists in the current firmware; it publishes only in response to commands. The AC1 local secrets file is absent. No command, firmware upload, or physical test was attempted.

Older records in `TEAM_CHANGE_LOG.md` and `reports/final_validation/hardware_cycles.csv` document real production-topic commands with matching ACKs and operator observations from 2026-10-03/04. The records also show ACK latencies over 500 ms, a wrong gate position, later servo concerns, and gate validation reopened/deferred. Those observations predate this firmware change; they are historical evidence and do not validate the newly compiled code. The broader `HW-IOT-03`/`HW-E2E-*` external status remains unfinished.

PE07 has no independent gate-position sensor or position telemetry in this implementation. The reported execution ACK cannot establish gate position. Gate movement remains deferred pending servo replacement and supervised verification.

The emulator's topic isolation and marker rejection prevent the provided mock from satisfying the real subscriber. However, the current runtime has no MQTT credentials, and the backend cannot cryptographically authenticate an ACK publisher. The repository's development Mosquitto config permits anonymous access. I did not change broker authentication, ACLs, or secrets; simulated-ACK isolation is therefore partial against other clients on an unsecured broker.

## Required operator procedure

1. Identify which connected serial port is AC1 and restore the intended local firmware secrets. Verify the broker endpoint and configure authorized MQTT identity/ACLs before attaching a real device.
2. After approval to upload, flash this compiled firmware to AC1 and monitor Wi-Fi, MQTT connection, and `city/commands/AC1` subscription over serial. This is the current documented passive check; there is no non-actuating MQTT heartbeat or ACK test command.
3. Keep the gate/servo disconnected or mechanically secured until its replacement is verified. With a supervised safe setup and emergency stop available, obtain explicit operator approval for one bounded `TRAFFIC/ALL_RED` test command. Observe the correlated `RECEIVED` and `execution_reported` ACKs on `city/acks/AC1` and the backend event/Dashboard projection. If the ACK is missing, do not manually resend; allow only the bounded same-ID retry policy and report the result as unknown if it remains unconfirmed.
4. Confirm any physical output by direct observation or independent feedback. Do not mark PE07 position verified from an ACK alone.
