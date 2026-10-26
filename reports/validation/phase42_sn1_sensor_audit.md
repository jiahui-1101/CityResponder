# CityResponder Phase 4.2 — SN1 sensor audit

Date: 2026-10-26 (Asia/Singapore)

## Isolation and scope

- Worktree: `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1`
- Branch: `feature/sn1-hardware-validation`
- Base: `45a685e` (`integration/cityresponder-phase2-phase36`), the current shared-worktree commit. The local uncommitted SN1 MQTT firmware diff was reviewed and copied into this branch before editing.
- The original worktree and its AC1 changes were not modified. No commit, push, merge, upload, broker connection, FastAPI restart, SQLite write, firewall change, or serial-port access was performed.
- Both SN1 PlatformIO projects now omit fixed COM ports in this branch. The separate raw bring-up project had been pinned to COM5; the original shared worktree still contains its prior uncommitted SN1 MQTT COM7 setting and was intentionally left untouched.

## Actual SN1 sensor matrix

The production-bound MQTT firmware and the separate local bring-up firmware support the same five inputs. No additional physical sensor is present in either SN1 source.

| Sensor | GPIO and signal | Expected value and software range | Read/publish interval | MQTT field / backend field | Failure handling |
| --- | --- | --- | --- | --- | --- |
| MQ-2 AO | GPIO34, ADC1 input; hardware reference specifies 20 kΩ / 10 kΩ divider from the 5 V module AO | 12-bit raw ADC count, 0–4095. Not ppm or calibrated concentration. | 1 s | `city/sensors/mq2`: numeric `value`, `unit=raw`, `measurement_kind=RAW_ADC`, `adc_status`; backend `MQ2.value` and `quality` | Near-rail counts are retained as raw evidence with `SATURATED` quality and excluded from fusion/severity. A single ADC reading cannot reliably distinguish a disconnected module from other electrical faults. No firmware warm-up gate, burn-in, calibration, averaging, or noise characterization is implemented. |
| DHT22 | GPIO4, one-wire data | Temperature −40–80 °C; relative humidity 0–100% | Poll and publish once per successful 2 s read | `city/sensors/dht22`: `value`, `unit=C`, `humidity`, `humidity_unit=pct`, `dht_ok=true`; backend `DHT22.value` and `humidity_pct` | NaN and out-of-range reads are omitted. Last valid value ages to stale; recovery sends the next valid read. Timestamp refers to the read time. |
| IR1 / `IR_A` | GPIO32, digital input | Boolean blocked state; configured LOW=blocked, HIGH=clear | 1 s | `city/sensors/ir_a`: `value`, `unit=blocked`, `raw`; backend `IR_A.value` | No firmware debounce. Backend freshness is 2 s. A disconnected/floating digital input is not identifiable from its boolean level alone. Physical polarity remains unverified. |
| IR2 / `IR_B` | GPIO33, digital input | Boolean blocked state; configured LOW=blocked, HIGH=clear | 1 s | `city/sensors/ir_b`: `value`, `unit=blocked`, `raw`; backend `IR_B.value` | Same handling as IR1. |
| Push button | GPIO27, digital input with `INPUT_PULLUP` | Boolean pressed state; LOW=pressed, HIGH=released | 1 s | `city/sensors/button`: `value`, `raw`; backend `BUTTON.value` | Backend freshness is 2 s. |

GPIO assignments match the hardware reference and do not conflict within SN1. GPIO34 is input-only, appropriate for ADC input. None of the assigned pins (34, 4, 32, 33, 27) is an ESP32 boot-strapping pin. The documented 5 V MQ-2 supply uses the divider before GPIO34; DHT22 and IR modules are documented on 3.3 V. The physical divider, module logic levels, sensor polarity, and powered board have not been measured in this audit.

The reference document labels IR1 as the main route and IR2 as the alternate route. It does not verify a particular graph edge, and `VISION_ROAD_IR_MAPPING` remains unset by default. The five-consecutive-sample debounce helper in `backend/app/routing/state.py` is not wired to the live MQTT sensor subscriber. No production route edge is assigned or blocked from SN1 IR labels.

## MQTT and backend contract

SN1 MQTT messages include `sensor_type`, `value`, timezone-aware UTC `timestamp` with milliseconds, `node_id=SN1`, unique boot/sequence `message_id`, `firmware_version=sn1-mqtt/1.1.0`, and `protocol_version=1.1`. Messages are non-retained QoS 0. The firmware waits for SNTP time before publishing and uses a 512-byte MQTT buffer.

Backend handling now:

- Validates topic-to-sensor type, exact configured node allowlist, timezone-aware timestamps, a five-second future-skew limit, sensor value types/ranges/units, DHT humidity, and supported payload fields.
- Uses `SENSOR_MQTT_TOPIC_PREFIX` (default `city/sensors`) so isolated tests can use `test/city/sensors` only.
- Rejects retained sensor messages, duplicate message IDs, and source timestamps that are not newer than the recent accepted reading for that node/sensor. Malformed JSON is contained by the MQTT client and does not reach persistence as a valid sensor event.
- Persists accepted raw payloads as sensor events, projects only configured node IDs, and retains source node, source timestamp, units, humidity, quality, and simulated marker in latest state.
- Marks MQ2 stale after 2 s, DHT22 after 3 s, and button/IR after 2 s. Saturated MQ2 readings remain visible as raw values but do not contribute to fusion or severity.

The configured provisional backend breakpoints remain unchanged: MQ-2 raw counts normal=500 and alarm=2000; DHT22 temperature normal=30 °C and alarm=40 °C. They are software thresholds, not MQ-2 calibration or ppm values. The backend has no registry table; `SENSOR_ALLOWED_NODE_IDS` is an exact-ID allowlist and defaults to `SN1`.

The dashboard now displays `LIVE`, `STALE`, `OFFLINE`, and `SIMULATED` states, preserves DHT humidity and MQ2 quality, and warns on saturated readings. Freshness refreshes every 10 s. Demo publisher payloads are marked `simulated=true`; its `mock-sn1` ID is rejected unless explicitly allowed in an isolated test configuration.

## Fixes made in this branch

1. Removed hard-coded COM selections from both SN1 PlatformIO projects. In particular, SN1 bring-up no longer targets the known AC1 COM5 port, and SN1 MQTT does not assume COM7.
2. Made MQTT fallback host a placeholder, added optional paired local MQTT credentials, and kept all credentials out of serial logs. MQTT transport remains plain TCP; credentials must not be sent over an untrusted network.
3. Added firmware/protocol markers, unique message IDs, millisecond UTC timestamps, explicit ADC resolution/attenuation, ADC saturation quality, DHT range checks, and DHT timestamps tied to actual reads. Failed DHT reads are omitted and repeated DHT samples are not republished each second.
4. Added backend schema, identity, topic, future-time, duplicate, out-of-order, retained-message, and digital-freshness handling.
5. Preserved DHT humidity, source identity, raw value, quality, and simulated state through the API, fusion input, and dashboard.
6. Excluded saturated MQ2 counts from fusion and severity without discarding the raw event or changing existing thresholds.
7. Updated the mock publisher to carry explicit simulated metadata and contract-compatible DHT/IR units.

Changed files:

```text
.env.example
backend/app/core/config.py
backend/app/fusion/policies.py
backend/app/fusion/sensors.py
backend/app/main.py
backend/app/mqtt/client.py
backend/app/sensors/handlers.py
backend/app/sensors/projection.py
backend/app/sensors/registry.py
backend/app/sensors/schemas.py
backend/app/severity/policies.py
backend/app/vision/freshness.py
backend/scripts/mock_sensor_publisher.py
backend/tests/test_sn1_sensor_integration.py
firmware/sn1_bringup/README.md
firmware/sn1_bringup/platformio.ini
firmware/sn1_bringup/src/main.cpp
firmware/sn1_mqtt/README.md
firmware/sn1_mqtt/include/secrets.example.h
firmware/sn1_mqtt/platformio.ini
firmware/sn1_mqtt/src/main.cpp
frontend/src/api/overview.ts
frontend/src/hooks/useOperatorOverview.ts
frontend/src/pages/OperatorOverviewPage.tsx
reports/validation/phase42_sn1_sensor_audit.md
```

## Automated verification

- SN1 MQTT PlatformIO `esp32dev` build: **PASS**; RAM 46,336 / 327,680 bytes (14.1%), flash 781,841 / 1,310,720 bytes (59.6%).
- SN1 bring-up PlatformIO `esp32dev` build: **PASS**; RAM 21,664 / 327,680 bytes (6.6%), flash 277,413 / 1,310,720 bytes (21.2%).
- New isolated SN1 tests: **35 passed**. They use in-memory SQLite and mocked MQTT; test topics use `test/city/sensors/#`. Coverage includes normal/elevated values, input validation, saturation exclusion, humidity/quality projection, freshness, duplicate/out-of-order data, unknown identities, topic mismatch, retained messages, malformed JSON, reconnect/resubscribe, independent IR channels, DHT stale/recovery behavior, fusion evidence preservation, and session reopen.
- Relevant backend sensor/fusion/runtime/vision suites: **71 passed**.
- Full backend suite: **179 passed, 27 failed**. Twenty-six road/vision tests require draft artifacts absent from this worktree (for example `reports/debug/camera_alignment/road_graph_phase_b1_realigned_draft.json`). One security-hardening assertion expects local custom runtime security settings that are not present in this environment. The selected sensor/fusion/runtime/vision suites pass.
- Frontend regression scripts: **PASS**. TypeScript typecheck: **PASS**. Production build: **PASS**.
- `git diff --check`: **PASS** (line-ending notices were normalized for rewritten files).
- No serial monitor or upload command was run. No MQTT broker, FastAPI service, or production SQLite was used by the isolated sensor tests.

## Hardware readiness and operator procedure

`SN1_HARDWARE_READY=DEFERRED`; `SN1_REAL_SENSOR_VERIFIED=NO`. SN1 was disconnected, so Wi-Fi, broker authentication, real voltage levels, MQ2 warm-up/baseline, DHT readings, IR polarity/debounce, dashboard live telemetry, and physical route association remain unverified. The build is software-only.

When SN1 is connected, proceed one test at a time:

1. Have the operator connect only the board labeled SN1 and report its newly observed COM port and ESP32 board identity. Never use COM5 or assume COM7.
2. Confirm the physical MQ-2 divider and 3.3 V sensor wiring against the hardware reference. Keep the board idle; do not introduce smoke, flame, or other incident stimuli.
3. Confirm local Wi-Fi/MQTT host and credentials are configured outside version control. The current firmware transport is not TLS; use only a trusted isolated LAN unless TLS is added and configured.
4. Before any firmware upload, ask the operator for explicit approval. This audit only built firmware.
5. After an approved upload, observe SNTP, Wi-Fi and MQTT connection diagnostics without exposing credentials. Verify one ordinary MQ2 raw count and DHT temperature/humidity in serial and MQTT.
6. Test IR1 alone: place and remove a safe opaque object, observe raw LOW/HIGH and dashboard state. Then repeat with IR2 alone. Confirm module polarity physically; do not infer edge IDs from channel names.
7. Confirm the backend accepts the actual SN1 identity, source timestamps, and current values, then verify dashboard freshness and stale recovery. Do not enable incident dispatch or actuator behavior for this sensor test.

## Required integration after this audit

All implementation remains uncommitted on `feature/sn1-hardware-validation`. The running shared FastAPI process still has its existing code until the SN1 branch is reviewed and integrated, and then the backend is restarted under the operator's separate AC1 schedule. This audit did not restart or connect to that process or to Mosquitto. AC1 worktree, broker, firewall, production credentials, and production database remain outside this branch's runtime tests.

## Final status

```text
SN1_FIRMWARE_AUDIT=PASS
SN1_GPIO_MAPPING=PASS (code matches reference; physical levels NOT_VERIFIED)
SN1_FIRMWARE_BUILD=PASS (MQTT and bring-up targets)
MQ2_READING=NOT_VERIFIED
MQ2_THRESHOLD_LOGIC=PASS (500/2000 raw-count breakpoints; unchanged)
MQ2_CALIBRATION=NOT_VERIFIED
DHT_READING=NOT_VERIFIED
DHT_ERROR_HANDLING=PASS (software)
IR1_DETECTION=NOT_VERIFIED
IR2_DETECTION=NOT_VERIFIED
IR_DEBOUNCE=PARTIAL (five-sample helper exists; not connected to MQTT route edges)
IR_PHYSICAL_ROAD_MAPPING=PARTIAL (main/alternate documented; physical edge unverified)
SN1_MQTT_PAYLOAD=PASS (isolated schema/mock tests)
MQTT_TELEMETRY_TESTS=PASS (mock transport, TEST-only topics)
BACKEND_SENSOR_INGESTION=PASS (isolated branch tests; shared runtime not updated)
SENSOR_FRESHNESS=PASS (MQ2 2 s, DHT22 3 s, digital 2 s)
FUSION_COMPATIBILITY=PARTIAL (software contract passes; MQ2 remains uncalibrated)
DASHBOARD_SENSOR_DISPLAY=PASS (branch build; live runtime not updated)
SN1_WIFI=NOT_VERIFIED
SN1_MQTT_CONNECTION=NOT_VERIFIED
REAL_SN1_SENSOR_VALIDATION=DEFERRED
BACKEND_TESTS=PARTIAL (71 relevant pass; full suite 179 pass / 27 unrelated failures)
FRONTEND_TESTS=PASS
AC1_ISOLATION=PASS
GIT_WORKTREE_ISOLATION=PASS
SN1_SOFTWARE_READY=YES (isolated branch)
SN1_HARDWARE_READY=DEFERRED
SN1_REAL_SENSOR_VERIFIED=NO
```
