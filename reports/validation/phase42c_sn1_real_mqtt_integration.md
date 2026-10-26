# CityResponder Phase 4.2C — SN1 MQTT integration preparation

Date: 2026-10-26 (Asia/Singapore)

## Scope and isolation

- SN1 changes remain in `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1`, branch `feature/sn1-hardware-validation`; all changes are uncommitted.
- The integration preview remains separate at `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1-main-integration`, based on latest read-only `origin/main` `492b233`.
- COM6 was identified by USB device metadata as SN1; COM5 remained the distinct AC1 CP210x. Neither port was opened during Phase 4.2C.
- The installed SN1 firmware remains the no-network `sn1-bringup/1.1.0` image. No network firmware was uploaded.
- Production Mosquitto was inspected read-only. No production broker connection, ACL/password edit, reload, FastAPI restart, database access, firewall change, merge, commit, or push occurred.

## Firmware and telemetry contract

- Network firmware marker: `sn1-mqtt/1.2.0`; protocol marker: `1.1`; board target: ESP32 DevKit V1 / `esp32dev`.
- The default firmware publishes only these non-retained QoS 0 topics:

  | Topic | Payload meaning | Cadence |
  | --- | --- | --- |
  | `city/sensors/dht22` | `sensor_type=DHT22`, temperature °C in `value`, humidity percent in `humidity`, `dht_ok=true` | Each valid two-second read |
  | `city/sensors/ir_a` | `sensor_type=IR_A`, boolean `value` means blocked, `raw` is LOW/HIGH | 1 second |
  | `city/sensors/ir_b` | `sensor_type=IR_B`, boolean `value` means blocked, `raw` is LOW/HIGH | 1 second |

- Each payload includes `node_id=SN1`, an ISO-8601 UTC timestamp, a boot-scoped `message_id`, `firmware_version`, and `protocol_version`. IR telemetry provides the heartbeat; backend freshness supplies online/stale/offline state. No new status topic was invented because the existing project has no status-message contract.
- DHT failures are omitted so the backend ages the last valid sample to stale. Firmware retries Wi-Fi and MQTT connections and does not publish until NTP time is available.
- The firmware requires an ignored `include/secrets.h`; compilation fails if it is absent. Its runtime gate rejects empty or placeholder values and requires both MQTT username and password. No credentials are logged.
- `CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY=0` and `CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY=0` are explicit build flags. MQ2 is not sampled or published. Button telemetry is disabled because the existing sensor ingestion path calls automatic coordination for button state and can persist a dashboard alert when pressed. No button message is sent during observation-only testing.
- The dashboard labels MQ2 `DEFERRED · UNVERIFIED`, hides any previous value, and labels button telemetry as safety-disabled. It displays firmware version for received sensor states and derives SN1 online/stale/offline from fresh DHT22/IR readings. IR physical road mapping remains unverified.

## Broker ACL audit and proposal

- The Mosquitto service configuration at `<MOSQUITTO_CONFIG_FILE>` was read without connecting to the broker. It has anonymous access disabled, a password file and ACL file configured, and loopback/private listeners on port 1883. The listener is plain MQTT without TLS.
- The ACL was read with user names redacted. It contains no SN1 publisher identity and no `write city/sensors/...` rule. Existing backend read access covers sensor topics; the backend code now subscribes only to the active DHT22 and IR topics.
- Proposed additive production ACL block, **not applied**:

  ```text
  user sn1_sensor_pub
  topic write city/sensors/dht22
  topic write city/sensors/ir_a
  topic write city/sensors/ir_b
  ```

- This grants no read access, wildcard write, MQ2/button access, vision access, ACK access, or AC1 command access. A dedicated SN1 password entry and SN1-only Wi-Fi settings are still required. Removing the four-line ACL block and deleting the `sn1_sensor_pub` password entry is the rollback. Applying it may require a broker ACL/password reload; no reload or service restart was attempted.
- Since the production listener has no TLS, authenticated traffic is still unencrypted on the network. Any later device connection must use a trusted private WLAN; no TLS or firewall changes were prepared or applied.

## Isolated MQTT-to-backend test

- Added an automated test that starts a separate Mosquitto process on an ephemeral loopback port with anonymous access disabled, temporary test credentials, a temporary ACL, and an in-memory SQLite database.
- The test authenticated separate publisher and backend-reader accounts; published sanitized DHT22, IR_A, and IR_B samples through the actual Paho-backed backend MQTT client and sensor handler; and verified the resulting sensor projection, humidity, firmware version, and IR states.
- The loopback broker denied the publisher's attempts to write MQ2, button, and `city/commands/AC1`. The test confirmed those messages were not ingested. Temporary credentials were test-only; no production credential or broker was used.
- This proves isolated broker authentication, ACL scope, topic/payload compatibility, backend ingestion, and state projection. It does **not** prove that the physical SN1 board joined Wi-Fi or published real MQTT telemetry.

## Verification

- SN1 branch backend suite: **209 passed**.
- Latest-main/AC1 integration preview backend suite: **236 passed**.
- SN1 frontend regression scripts, typecheck, and production build: **PASS**.
- Integration preview frontend regression scripts, typecheck, and production build: **PASS**.
- Bring-up `esp32dev` build: **PASS**, RAM 21,664 / 327,680 bytes (6.6%), flash 277,637 / 1,310,720 bytes (21.2%).
- Network `esp32dev` build: **PASS** with temporary test-only credentials outside the worktree; RAM 46,336 / 327,680 bytes (14.1%), flash 778,557 / 1,310,720 bytes (59.4%). Temporary test image SHA-256: `CC0AAE55164FDCF7BD5AB499155E6123C8045E4D8484DEE76FC8F74CA1B25C42` (785,136 bytes). This image is not a deployment image and was not uploaded.
- The temporary build root remains at `<ISOLATED_TEST_BUILD_DIRECTORY>`; it contains test-only credentials and is being preserved with the other work files. Do not upload or reuse that image.
- Both PlatformIO runs completed without C++ warnings. PlatformIO emitted only the existing obsolete-Core notice for Core 6.1.19.
- `git diff --check` is run after the report update.

## Remaining deployment dependencies

1. Authorize the additive least-privilege production ACL/password change before it is applied; no SN1 production principal currently exists.
2. Provide SN1-only Wi-Fi credentials through the approved secure channel. No `firmware/sn1_mqtt/include/secrets.h` exists in the worktree.
3. Build the deployment image with those SN1-only credentials, review its hash, and obtain separate explicit approval to upload it to the re-identified COM6 device. Approval of `sn1-bringup/1.1.0` does not authorize this network image.
4. After ACL and credential readiness, validate real Wi-Fi/MQTT and physical DHT22/IR telemetry. Backend code must be integrated in the active project; if that requires a shared runtime restart, coordinate AC1 idle state and obtain separate restart approval first.
5. Do not publish button or MQ2 telemetry during this phase. Do not create production incidents or dispatch actuators. Do not assign IR_A/IR_B to a road edge without verified mapping.

## Final status

```text
SN1_NETWORK_FIRMWARE_BUILD=PASS (esp32dev; isolated test credentials; not a deployment image)
SN1_FIRMWARE_UPLOAD=DEFERRED (network image has not been approved for upload)
SN1_WIFI_CONNECTED=NOT_VERIFIED
SN1_MQTT_AUTHENTICATED=PARTIAL (authenticated loopback test only)
SN1_MQTT_TELEMETRY=PARTIAL (synthetic isolated telemetry only)
BACKEND_SENSOR_INGESTION=PASS (loopback broker to isolated database)
LIVE_DHT22=NOT_VERIFIED over MQTT (serial sensor reading verified in Phase 4.2B)
LIVE_IR_A=NOT_VERIFIED over MQTT (physical polarity verified in Phase 4.2B)
LIVE_IR_B=NOT_VERIFIED over MQTT (physical polarity verified in Phase 4.2B)
LIVE_BUTTON=DEFERRED (production alert path is not observation-only)
MQ2=DEFERRED_BY_USER
DASHBOARD_LIVE_SENSOR_DATA=PARTIAL (API/UI contract and freshness states verified; no real MQTT values)
FUSION_COMPATIBILITY=PARTIAL (regression tests pass; real telemetry/shadow run not performed)
IR_PHYSICAL_ROAD_MAPPING=NOT_VERIFIED
AC1_RUNTIME_PRESERVED=PASS
PRODUCTION_DATABASE_PRESERVED=PASS
FULL_BACKEND_TESTS=PASS (209 SN1; 236 integration preview)
FRONTEND_TESTS=PASS (both worktrees; scripts, typecheck, production build)
SN1_END_TO_END=PARTIAL (isolated test path passes; physical network path awaits approval and credentials)
```
