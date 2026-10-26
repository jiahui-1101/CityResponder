# CityResponder Phase 4.2B — SN1 repair, integration, and hardware preparation

Date: 2026-10-26 (Asia/Singapore)

## Isolation and Git state

- SN1 development worktree: `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1`
- SN1 branch: `feature/sn1-hardware-validation` (uncommitted)
- SN1 branch base: `45a685e` (`integration/cityresponder-phase2-phase36`)
- Latest remote main was checked read-only with `git ls-remote`: `492b233` (`Update live vision and overview UI`), four commits ahead of the SN1 base.
- Isolated integration preview: `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1-main-integration`, branch `codex/sn1-main-integration-preview`, based on `origin/main` at `492b233`.
- The preview includes SN1 changes, a read-only snapshot of the current AC1 acknowledgement backend/API changes, and a composed overview page. No commit, push, merge, production service restart, broker connection, COM5 open, or firmware upload was performed. The original shared AC1 worktree remains unmodified.

## Resolution of the previous 27 backend failures

The full suite was rerun and all 27 failures were investigated. They were test setup dependencies, not failing SN1 behavior.

| Prior failures | Affected tests | Root cause and repair |
| --- | --- | --- |
| 7 | `test_camera_realignment_draft.py` | Required source, realigned, and final-review ROI/road-graph drafts, the source camera frame, and `historical_t0_t7_sha256.json` were under ignored `reports/debug/camera_alignment/`. |
| 3 | `test_phase35_routing_visualization.py` | Required the final-review graph and its 1920×1080 raw camera frame from the same ignored artifact directory. |
| 7 | `test_phase_b2_t7_offline.py` | Required `roi_calibration_phase_a_draft.json` for synthetic mask checks. |
| 9 | `test_polygon_roi_integration.py` | Required `roi_calibration_phase_a_draft.json` for loader and polygon-pipeline checks. |
| 1 | `test_security_hardening.py::test_local_security_values_are_custom_and_cors_is_bearer_only` | Asserted workstation-local secrets while pytest had no operator runtime config, so it read development defaults. |

The exact camera-alignment inputs are:

```text
reports/debug/camera_alignment/roi_calibration_phase_a_draft.json
reports/debug/camera_alignment/roi_calibration_phase_a_realigned_draft.json
reports/debug/camera_alignment/roi_calibration_phase_a_final_review_draft.json
reports/debug/camera_alignment/road_graph_phase_b1_draft.json
reports/debug/camera_alignment/road_graph_phase_b1_realigned_draft.json
reports/debug/camera_alignment/road_graph_phase_b1_final_review_draft.json
reports/debug/camera_alignment/camera_alignment_20261025T084211_819245Z_index0_raw.jpg
reports/debug/camera_alignment/historical_t0_t7_sha256.json
reports/debug/road_vision_tests/ (79 exact manifest entries):

```text
reports/debug/road_vision_tests/phase_b2_t7_offline_support_exclusion_validation.md
reports/debug/road_vision_tests/pytest_phase_b2_gui_20261023/test_fv034_database_claim_allo0/targeted.db
reports/debug/road_vision_tests/pytest_phase_b2_gui_20261023/test_fv034_late_confirm_is_log0/targeted.db
reports/debug/road_vision_tests/pytest_phase_b2_gui_20261023/test_route_version_increment_a0/targeted.db
reports/debug/road_vision_tests/pytest_phase_b2_gui_final/test_fv034_database_claim_allo0/targeted.db
reports/debug/road_vision_tests/pytest_phase_b2_gui_final/test_fv034_late_confirm_is_log0/targeted.db
reports/debug/road_vision_tests/pytest_phase_b2_gui_final/test_route_version_increment_a0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_final/test_fv034_database_claim_allo0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_final/test_fv034_late_confirm_is_log0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_final/test_route_version_increment_a0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_phase_b2/test_fv034_database_claim_allo0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_phase_b2/test_fv034_late_confirm_is_log0/targeted.db
reports/debug/road_vision_tests/pytest_tmp_phase_b2/test_route_version_increment_a0/targeted.db
reports/debug/road_vision_tests/session_20261022T152957Z_32bcc6/results.csv
reports/debug/road_vision_tests/session_20261022T152957Z_32bcc6/results.json
reports/debug/road_vision_tests/session_20261022T152957Z_32bcc6/session_metadata.json
reports/debug/road_vision_tests/session_20261022T153450Z_9a42ee/session_metadata.json
reports/debug/road_vision_tests/session_20261022T154427Z_1e031d/results.csv
reports/debug/road_vision_tests/session_20261022T154427Z_1e031d/results.json
reports/debug/road_vision_tests/session_20261022T154427Z_1e031d/session_metadata.json
reports/debug/road_vision_tests/session_20261022T155849Z_962899/samples/TEST_ONLY_T0_20261022T160000_125563Z.json
reports/debug/road_vision_tests/session_20261022T155849Z_962899/samples/TEST_ONLY_T0_20261022T160000_125563Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T155849Z_962899/samples/TEST_ONLY_T0_20261022T160000_125563Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T155849Z_962899/session_metadata.json
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/results.csv
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/results.json
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/samples/TEST_ONLY_T1_20261022T164223_077147Z.json
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/samples/TEST_ONLY_T1_20261022T164223_077147Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/samples/TEST_ONLY_T1_20261022T164223_077147Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T164204Z_194bbf/session_metadata.json
reports/debug/road_vision_tests/session_20261022T170110Z_686767/results.csv
reports/debug/road_vision_tests/session_20261022T170110Z_686767/results.json
reports/debug/road_vision_tests/session_20261022T170110Z_686767/samples/TEST_ONLY_T2_20261022T170127_068632Z.json
reports/debug/road_vision_tests/session_20261022T170110Z_686767/samples/TEST_ONLY_T2_20261022T170127_068632Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T170110Z_686767/samples/TEST_ONLY_T2_20261022T170127_068632Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T170110Z_686767/session_metadata.json
reports/debug/road_vision_tests/session_20261022T170601Z_829338/samples/TEST_ONLY_T3_20261022T170627_246751Z.json
reports/debug/road_vision_tests/session_20261022T170601Z_829338/samples/TEST_ONLY_T3_20261022T170627_246751Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T170601Z_829338/samples/TEST_ONLY_T3_20261022T170627_246751Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T170601Z_829338/session_metadata.json
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/results.csv
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/results.json
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/samples/TEST_ONLY_T4_20261022T172019_405377Z.json
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/samples/TEST_ONLY_T4_20261022T172019_405377Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/samples/TEST_ONLY_T4_20261022T172019_405377Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T171949Z_dc4318/session_metadata.json
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/results.csv
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/results.json
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/samples/TEST_ONLY_T5_20261022T172835_461023Z.json
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/samples/TEST_ONLY_T5_20261022T172835_461023Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/samples/TEST_ONLY_T5_20261022T172835_461023Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T172814Z_8abb58/session_metadata.json
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/results.csv
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/results.json
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/samples/TEST_ONLY_T6_20261022T173439_039565Z.json
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/samples/TEST_ONLY_T6_20261022T173439_039565Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/samples/TEST_ONLY_T6_20261022T173439_039565Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T173425Z_cf6d9f/session_metadata.json
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/results.csv
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/results.json
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/samples/TEST_ONLY_T7_20261022T173837_027777Z.json
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/samples/TEST_ONLY_T7_20261022T173837_027777Z_annotated.jpg
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/samples/TEST_ONLY_T7_20261022T173837_027777Z_raw.jpg
reports/debug/road_vision_tests/session_20261022T173821Z_179aa3/session_metadata.json
reports/debug/road_vision_tests/session_20261025T081239Z_462764/results.csv
reports/debug/road_vision_tests/session_20261025T081239Z_462764/results.json
reports/debug/road_vision_tests/session_20261025T081239Z_462764/session_metadata.json
reports/debug/road_vision_tests/session_20261025T081323Z_b043e6/results.csv
reports/debug/road_vision_tests/session_20261025T081323Z_b043e6/results.json
reports/debug/road_vision_tests/session_20261025T081323Z_b043e6/session_metadata.json
reports/debug/road_vision_tests/session_20261025T081630Z_93855a/results.csv
reports/debug/road_vision_tests/session_20261025T081630Z_93855a/results.json
reports/debug/road_vision_tests/session_20261025T081630Z_93855a/session_metadata.json
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/results.csv
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/results.json
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/samples/TEST_ONLY_T7_20261025T082113_787911Z.json
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/samples/TEST_ONLY_T7_20261025T082113_787911Z_annotated.jpg
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/samples/TEST_ONLY_T7_20261025T082113_787911Z_raw.jpg
reports/debug/road_vision_tests/session_20261025T081939Z_d50434/session_metadata.json
```
```

All of these are ignored by `.gitignore` at `reports/debug/`. They are absent from the SN1 worktree and `origin/main`, and present in the original local development worktree. The 79-file historical manifest passed its size and SHA-256 checks. Tests now accept `CITYRESPONDER_TEST_DATA_ROOT`, pointing at a CityResponder root that contains `reports/debug/`; the referenced inputs are read-only and were not copied or altered. This preserves the real geometry assertions. `backend/tests/README.md` documents the portable configuration for local and CI runs.

`backend/tests/conftest.py` isolates pytest from operator/runtime settings: it sets a unique temporary file-backed SQLite database, bypasses the operator config file, generates ephemeral JWT and seed values in process memory, points MQTT to loopback port 18884 without credentials, uses test-only sensor topics, and disables live vision/evidence publishing. The temporary state directory is removed at session end. No production database or broker was used.

## Integration and regression results

- SN1 targeted suite: **36 passed**.
- Relevant sensor/fusion/runtime/vision suites: **72 passed**.
- Complete backend suite on the SN1 branch: **207 passed**.
- Complete backend suite in the latest-main integration preview with the current AC1 acknowledgement snapshot: **234 passed**.
- Integration preview frontend regression scripts: **PASS**; TypeScript typecheck: **PASS**; production build: **PASS**. `npm ci` installed 124 packages and reported zero vulnerabilities.
- SN1 MQTT firmware `esp32dev` build: **PASS**; RAM 46,336 / 327,680 bytes (14.1%), flash 781,841 / 1,310,720 bytes (59.6%).
- SN1 bring-up firmware `esp32dev` build: **PASS**; RAM 21,664 / 327,680 bytes (6.6%), flash 277,637 / 1,310,720 bytes (21.2%). It now prints `sn1-bringup/1.1.0` at startup.
- Firmware builds emitted no C++ compile warnings. The installed PlatformIO Core prints an environment notice that v6.1.19 is obsolete; both builds completed successfully.
- `git diff --check`: **PASS**.

An API regression test now calls `/api/sensors/latest` with an in-memory SQLite dependency override and verifies DHT units/humidity, node identity, timestamp, simulated marker, MQ2 raw units, and saturation quality serialize as the dashboard contract expects. It does not enter FastAPI lifespan, connect MQTT, or write any shared database.

The latest-main preview resolved the active code overlaps in isolation: the MQTT client retains AC1's `publish_confirmed` implementation and also rejects retained sensor messages; the overview API type carries both AC1 command lifecycle fields and SN1 sensor metadata; the overview page retains the newer main UI while showing SN1 freshness/simulation/quality and AC1 ACK stages. This preview is not merged into the active AC1 worktree.

## Hardware identification and sensor-only bring-up results

- The user identified the board as ESP32 DevKit V1 / ESP32-WROOM-32, matching PlatformIO target `esp32dev`.
- Read-only enumeration identified SN1 as CP210x **COM6** (PNP ID `USB\\VID_10C4&PID_EA60\\6&4420B4E&0&1`). **COM5** remained the separate AC1 CP210x (PNP ID ends in `0001`) and was never opened.
- After the user's explicit `APPROVE SN1 BRING-UP UPLOAD`, PlatformIO flashed only COM6 with `firmware/sn1_bringup/.pio/build/esp32dev/firmware.bin` (278,000 bytes; SHA-256 `b9d90dfeeaa4684e727754a049371f1bc03669483773fb50b4dcbe28ca891938`). Esptool identified ESP32-D0WD-V3 and verified hashes for the bootloader, partition table, and application. Upload completed with `[SUCCESS]`; the board reset into `CityResponder SN1 firmware=sn1-bringup/1.1.0`.
- The image reads MQ2 on GPIO34, DHT22 on GPIO4, IR_A on GPIO32, IR_B on GPIO33, and the pull-up button input on GPIO27. It has no Wi-Fi, MQTT, or actuator code. Serial was monitored only on COM6 at 115200 baud.
- Over the observed ~5.8-minute run, DHT readings remained `dht_ok=1`, temperature **31.6–32.0 °C**, humidity **73.2–74.5% RH**. These are live sensor readings, not a calibration comparison.
- MQ2 raw ADC was usually **0**, with brief values up to **16** during this short run. No smoke, flame, or gas stimulus was used. This is not a calibrated concentration; sensor warm-up and response range remain unverified.
- Both IR inputs were HIGH unobstructed. Covering IR_A changed only `ir1` to LOW; removing the object restored HIGH. Covering IR_B changed only `ir2` to LOW while `ir1` remained HIGH; removing the object restored HIGH. Active-low polarity is physically verified for both. No road-edge mapping was made.
- The GPIO27 button input was HIGH at idle, produced a LOW sample during the user's press, and returned to HIGH after release. This verifies the physical input polarity only; the one-second bring-up sampler does not test debounce timing or MQTT event delivery. The image cannot publish an event or actuate equipment.
- Two isolated serial lines had garbled leading bytes in the monitor output; subsequent lines and sensor fields were readable. This is noted as host/serial capture noise, not interpreted as a sensor reading.
- The MQTT firmware still has no local `secrets.h` in the integration preview and is not ready for live MQTT. Real MQTT/backend/dashboard telemetry remains deferred under the AC1 isolation boundary. No production broker, FastAPI service, SQLite, firewall, or runtime was accessed.

## Changed files in the SN1 development branch

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
backend/tests/README.md
backend/tests/conftest.py
backend/tests/test_camera_realignment_draft.py
backend/tests/test_phase35_routing_visualization.py
backend/tests/test_phase_b2_t7_offline.py
backend/tests/test_polygon_roi_integration.py
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
reports/validation/phase42b_sn1_autonomous_repair_integration.md
```

## Final status

```text
SN1_SOFTWARE_READY=YES
FULL_BACKEND_TESTS=PASS (207 SN1 branch; 234 latest-main/AC1 snapshot preview)
PREVIOUS_27_FAILURES=PASS (resolved with explicit test artifact and test settings configuration)
SN1_FIRMWARE_BUILD=PASS (MQTT and no-network bring-up targets)
SN1_MQTT_CONTRACT=PASS (isolated mock/test topics; no live broker)
BACKEND_SENSOR_INGESTION=PASS (including isolated API serialization test)
DASHBOARD_SENSOR_INTEGRATION=PASS (latest-main preview regression, typecheck, production build)
FUSION_COMPATIBILITY=PARTIAL (software path passes; MQ2 remains uncalibrated)
IR_A_SOFTWARE=PASS
IR_B_SOFTWARE=PASS
MQ2_SOFTWARE=PASS (raw ADC and saturation behavior; calibration not verified)
DHT22_SOFTWARE=PASS
BUTTON_SOFTWARE=PASS (payload and input path only)
REAL_SN1_CONNECTION=PASS (COM6 identified; approved sensor-only image flashed and serial marker/readings verified)
REAL_SN1_MQTT=DEFERRED (no production broker connection)
REAL_MQ2=PARTIAL (raw 0–16 observed; short warm-up window, response, and calibration unverified)
REAL_DHT22=PASS (valid live readings; no external calibration reference)
REAL_IR_A=PASS (obstruction LOW; clear HIGH)
REAL_IR_B=PASS (obstruction LOW; clear HIGH)
REAL_BUTTON=PARTIAL (physical GPIO27 LOW-on-press/HIGH-on-release verified; debounce and event delivery deferred)
AC1_ISOLATION=PASS
PRODUCTION_SAFETY=PASS
INTEGRATION_READY=PARTIAL (isolated preview passes; active worktree not merged or restarted)
SN1_UPLOAD=PASS (user-approved no-network `sn1-bringup/1.1.0` flashed and esptool hashes verified)
```
