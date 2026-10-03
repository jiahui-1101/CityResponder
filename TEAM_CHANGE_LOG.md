# CityResponder — Team Change Log

**Purpose:** Shared record of requirement, policy, implementation, validation, hardware, UI/UX, and configuration changes.

## Mandatory rule

Whenever a teammate changes a requirement, source threshold, production policy, hardware mapping, sensor interpretation, routing topology, dispatch matrix, calibration policy, area-risk policy, API contract, UI/UX behavior, RBAC behavior, validation result, hardware result, camera/model configuration, production configuration, or evidence-retention behavior, add an entry here in the same work session.

Do not rely only on Git commit messages. Refer to `HARDWARE_EXTERNAL_REQUIREMENTS.md` for external work and `SOURCE_TBD_REQUIREMENTS.md` for undefined policy.

## Status vocabulary

Use: `PASS`, `FAIL`, `PARTIAL`, `NOT_RUN_EXTERNAL`, `BLOCKED_EXTERNAL`, `TBD_SOURCE`.

## Standard change entry

```md
## YYYY-MM-DD HH:MM — Short change title

**Changed by:** Name
**Branch:** branch-name
**Commit:** hash / not committed yet

**Requirement / area:**
- Requirement ID or module

**Files changed:**
- path

**Previous behavior / value:**
- ...

**New behavior / value:**
- ...

**Why this changed:**
- source clarification / team decision / bug fix / validation / UI consistency / other

**Source / decision reference:**
- proposal section, team decision, hardware evidence, or report

**Validation performed:**
- command/test/scenario and result

**Requirement status after change:**
- PASS / FAIL / PARTIAL / NOT_RUN_EXTERNAL / BLOCKED_EXTERNAL / TBD_SOURCE

**Impact on teammates:**
- update, rerun, or avoid

**Follow-up required:**
- next action or None
```

## Policy decision entry

Every team-approved TBD resolution must record the exact rule/formula/threshold, approver, affected backend/frontend/hardware/validation modules, tests to rerun, and the documentation/code updates.

## Hardware validation entry

Record tester, hardware and firmware versions, backend commit, environment, requirement ID/target, measured result, status, evidence path, notes, software/config changes, and follow-up.

## Current software baseline

- Branch: `main`
- Latest software commit: `df7a2f2`
- Deep audit baseline before this tracking-document commit: `a3950ef`
- Requirements reviewed: 328
- PASS: 251
- FAIL: 0
- PARTIAL: 0
- NOT_RUN_EXTERNAL: 19
- TBD_SOURCE: 58
- Backend compile/import/OpenAPI: PASS
- Frontend typecheck/build: PASS
- API contract audit: 29/29 matched
- Controlled routing benchmark: 150/150 under 1 second
- Controlled dashboard latency: 10/10 under 1 second
- Production UI fake/mock audit: PASS

## 2026-10-03 — Final pre-webcam AC1 validation

**Changed by:** Codex / real-hardware validation
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- AC1 production gate, traffic, buzzer, MQTT ACK, retry, duplicate, safe-default, and backend E2E validation

**Files changed:**
- `TEAM_CHANGE_LOG.md`

**Previous behavior / value:**
- Production AC1 gate angles were already approved as CLOSED=30° and OPEN=120°; final backend-originated E2E and failure-path evidence was pending.

**New behavior / value:**
- Ten real AC1 OPEN/CLOSE latency trials all received correlated ACKs under 500 ms; measured values were 147.3, 381.3, 135.9, 167.6, 165.4, 246.3, 256.0, and 487.6 ms, plus initial 51.1 and 44.1 ms publish-side observations. Maximum measured full request/ACK latency: 487.6 ms.
- Backend-originated TRAFFIC ALL_RED, GREEN_CORRIDOR, GATE OPEN, GATE CLOSE, BUZZER ON, and BUZZER OFF commands were physically confirmed and persisted with ACK events. GREEN_CORRIDOR included the required ALL_RED safety transition.
- GATE CLOSE exercised the fixed 500 ms timeout and one retry: attempt 1 timed out; attempt 2 ACKed in 349.4 ms and the gate was physically confirmed closed.
- Duplicate command protection passed: the same command ID produced a normal ACK followed by `DUPLICATE_ALREADY_APPLIED` without a second actuation.
- Controlled ACK withholding passed: two normal ACKs were withheld in a temporary one-off harness; the backend exhausted the normal attempt plus one retry, then applied and ACKed ALL_RED, GATE CLOSE, and BUZZER ON safe defaults. The harness was removed after the test.
- Safe idle was restored and physically confirmed: traffic OFF, gate CLOSED, buzzer OFF.

**Why this changed:**
- Real AC1 pre-webcam production-gate validation and failure-path evidence.

**Source / decision reference:**
- User-directed final pre-webcam AC1 validation; physical confirmations during this session.

**Validation performed:**
- AC1 COM7, `firmware/ac1_mqtt`, Wi-Fi/MQTT broker `172.20.10.12:1883`; no reset, brownout, watchdog, or crash observed.
- Traffic snapshots physically confirmed: ALL_RED and GREEN_CORRIDOR.
- Gate physical confirmations: OPEN=120°, CLOSED=30°, including repeated cycles and backend commands.
- Buzzer polarity and backend ON/OFF physical confirmations: ON=LOW/sounding, OFF=HIGH/silent.
- Persisted backend audit events were observed for command/ACK pairs and safe-default actions. No production backend timeout change was made.

**Requirement status after change:**
- PASS for AC1 production command/ACK, physical actuator, retry, duplicate, safe-default, and safe-idle checks.
- PARTIAL for live WebSocket evidence in these one-off scripts; persistence and the previously validated live path remain separate.

**Impact on teammates:**
- No GPIO assignments, MQTT topics/payload schema, backend timeout, fusion/severity policy, or unrelated response regression was changed.
- Production AC1 firmware remains without temporary trace or ACK-suppression instrumentation; duplicate guard and 30°/120° constants remain.

**Follow-up required:**
- Proceed to webcam/vision integration. Keep the unrelated SN1 MQ-2 analog-path issue and calibration thresholds unresolved.

Future changes must not invalidate this baseline without updating validation evidence and this log.

## 2026-10-02 22:45 — Integrate Jiabao State Machine & Feedback Lifecycle (Side-State Hardware)

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- Dispatch Logic & Hardware Orchestration (Feedback Lifecycle & Side-States)

**Files changed:**
- `backend/app/respond/service.py`
- `backend/app/physical_actions/execution.py`
- `backend/app/physical_actions/schemas.py`
- `backend/app/events/states.py`
- `backend/scripts/validate_dispatch_policies.py`

**Previous behavior / value:**
- Operator actions (REJECT, CANCEL) were ignored in the hardware dispatch pipeline, trapping the orchestration in `not_actionable` without physical remediation.
- State enumerations representing the feedback lifecycle were missing.
- Safe defaults were limited to `NO_SAFE_ROUTE` and `ACTUATOR_ACK_TIMEOUT` without specific cancellation specs for human override.

**New behavior / value:**
- Introduced `IncidentState` enumerations strictly matching the Jiabao specification (`RESPONDING, ACTIVE, CONCLUDED, VERIFIED, VERIFIED_FIRE, REJECTED, CANCELLED, FAILSAFE`).
- Created `build_cancellation_specs` inside `execution.py` to physically reverse active hardware dispatches.
- Intercepted `REJECT` and `CANCEL` Operator commands natively in `RespondOrchestrationService.run` to emit cancellation hardware states (`TRAFFIC OFF, GATE CLOSE, BUZZER OFF`).
- Updated `ActionCategory.TRAFFIC` to support the `OFF` action for corridor releases.
- Side-state `FAILSAFE` retains strict enforcement (`ALL_RED, GATE CLOSE, BUZZER ON`).

**Why this changed:**
- Strict alignment with Jiabao's verification authority and feedback lifecycle rules. Prevents ghost-locks on hardware actuators when false alarms are cancelled or rejected by an operator.

**Source / decision reference:**
- Integrated incident feedback lifecycle requirements and state machine specifications from Jiabao.

**Validation performed:**
- Added `test_side_states` into `validate_dispatch_policies.py`. Asserted generation of ALL_RED/CLOSE/ON for FAILSAFE, and OFF/CLOSE/OFF for CANCEL/REJECT. All tests pass.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Frontend must send `REJECT` or `CANCEL` explicitly via operator interface to properly reset physical building hardware during false alarms.

**Follow-up required:**
- Implement Area Risk calculations using the `VERIFIED_FIRE` closed state feedback.

## 2026-10-02 22:05 — Refactor Dispatch Resource and Hardware Action Logic

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- DISPATCH-01 to DISPATCH-03 (Dispatch Logic & Hardware Orchestration)

**Files changed:**
- `CityResponder_Dispatch_Specification.md`
- `backend/app/dispatch/policies.py`
- `backend/app/respond/service.py`
- `backend/scripts/validate_dispatch_policies.py`

**Previous behavior / value:**
- Manual confirm unconditionally defaulted to CRITICAL.
- Buzzer only sounded on HIGH and CRITICAL severities.
- GREEN_CORRIDOR and low-level gate rules were undefined, and documentation lacked explicit trigger chains.

**New behavior / value:**
- Manual override now strictly uses the existing calculated `R` score, or defaults to **MEDIUM** if no score exists.
- Buzzer is now set to `ON` for **ALL** severities (LOW through CRITICAL) to guarantee building evacuation.
- Gate `OPEN` and `GREEN_CORRIDOR` actions are explicitly restricted to **MEDIUM, HIGH, and CRITICAL** events.
- Updated documentation to use explicit logic chains (e.g., `P=1 -> CRITICAL -> 2 Fire + 1 Amb + 1 Rescue`).

**Why this changed:**
- Addressed code review feedback to prevent wasting medical/rescue resources (adhering to the "≤10% false dispatch KPI") caused by manual overrides always calling ambulances.
- Patched a critical life-safety flaw (referencing the Kuching apartment case study) where LOW/MEDIUM fires would not trigger building evacuation alarms.

**Source / decision reference:**
- Team architectural code review and updated `CityResponder_Dispatch_Specification.md`.

**Validation performed:**
- Executed updated `validate_dispatch_policies.py` to confirm fallback to Medium and Buzzer ON for Low severity.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend routing team must ensure `GREEN_CORRIDOR` logic handles the updated severity threshold. Hardware team must verify the buzzer triggers correctly on Low severity.

**Follow-up required:**
- Proceed to configure the Routing Topology and Cost thresholds module.

## 2026-10-02 21:15 — Finalize and Implement Severity Module Logic (TBD-SEV-01 to 06)

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- TBD-SEV-01 to TBD-SEV-06 (Severity Assessment & Critical Override)

**Files changed:**
- `severity.md`
- `backend/app/vision/hazard.py`
- `backend/app/severity/policies.py`
- `backend/tests/validate_severity_policies.py`
- `backend/tests/validate_severity_orchestration.py`

**Previous behavior / value:**
- Severity variables (A, S, T, P, Z) and R formula thresholds were undefined (TBD_SOURCE).
- The vision module (`hazard.py`) evaluated person bounding boxes inside hazard zones without checking YOLO detection confidence.
- Potential variable collision existed where Severity `S` reused Fire Fusion's maximum value (double-counting temperature) and `T` collided with temporal consistency.

**New behavior / value:**
- Renamed and isolated variables: `S` is now pure MQ-2 (500/2000), and `T` is renamed to `T_heat` for pure DHT22 (30/50).
- Implemented core formula: `R = 100 * (0.30A + 0.20S + 0.20T_heat + 0.20P + 0.10Z)`.
- Modified `hazard.py` to enforce a strict YOLO confidence threshold of >= 0.50 globally.
- Implemented Critical Override: If `P = 1` (person detected in zone), bypass R calculation and immediately return `CRITICAL`.
- Defined default bands for R (when P = 0): LOW (0-29), MEDIUM (30-49), HIGH (50-69), CRITICAL (70-80).
- Set `A` as Pixel Ratio (fire bounding box / hazard polygon) and hardcoded `Z` values (0.30, 0.60, 1.00).

**Why this changed:**
- Team decision to resolve all Severity TBDs, eliminate logic collision with the Fire Fusion module, and securely integrate the life-safety override (P=1) natively into the orchestration pipeline.

**Source / decision reference:**
- Updated `CityResponder_Severity_Specification.md` based on team discussions and Jiabao's proposed resolutions for TBD-SEV-01 through 06.

**Validation performed:**
- Ran `validate_severity_policies.py` (17/17 standalone policy tests passed).
- Ran `validate_severity_orchestration.py` end-to-end; verified orchestration pipeline seamlessly routes metrics and successfully short-circuits to CRITICAL when P=1.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Frontend team should verify dashboard maps correctly to the new 4-tier severity bands. Hardware team must avoid changing `T_heat` back to `T` in downstream components.

**Follow-up required:**
- Hardware team needs to measure actual hazard-zone polygon coordinates on the physical sandbox to calibrate the Pixel Ratio calculation for A.

## 2026-10-02 18:46 — Finalize Fire Fusion (S/T/V/H) Logic and Thresholds

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- TBD-FUSION-01 to TBD-FUSION-06 (Fire Fusion Logic)

**Files changed:**
- fire_fusion.md
- backend/app/fusion/policies.py
- backend/app/fusion/schemas.py
- backend/.../validate_fusion_policies.py

**Previous behavior / value:**
- Fusion thresholds and formulas (S, T, V, H) were uncalibrated and marked as TBD.

**New behavior / value:**
- Defined normal/alarm limits for DHT22 (30°C/50°C) and MQ-2 (500/2000).
- Set temporal consistency threshold: S >= 0.20, V >= 0.40, or button pressed.
- Set YOLO minimum confidence for V to 0.50.
- Cold start H explicitly set to 0.
- Defined supporting channels minimum score as 0.30 (MQ-2 and DHT22 are separate channels).
- Confirmed Operator can dispatch directly based on a manual button press override.

**Why this changed:**
- Finalized the missing values required to implement the core formula C = 100 * (0.30S + 0.20T + 0.35V + 0.15H) for the tabletop demonstrator.

**Source / decision reference:**
- SOURCE_TBD_QUESTIONS_FOR_TEAM.md discussion and team agreement.

**Validation performed:**
- Backend reloaded successfully without errors, and we verified through the Operator dashboard (localhost:5173) that simulated sensor inputs correctly trigger the supporting channels and calculate the C score.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend team can now implement these specific formulas. Frontend dashboard may need to verify UI matches these thresholds.

**Follow-up required:**
- Implement the logic in Python backend and run hardware integration tests on the tabletop model.

## 2026-10-01 — Shared requirement tracking files added

**Changed by:** Team / ChatGPT-assisted documentation
**Branch:** `main`
**Commit:** documentation commit for these files

**Requirement / area:**
- Cross-team requirement, external-validation, and source-TBD tracking

**Files changed:**
- `HARDWARE_EXTERNAL_REQUIREMENTS.md`
- `SOURCE_TBD_REQUIREMENTS.md`
- `TEAM_CHANGE_LOG.md`

**Previous behavior / value:**
- Remaining external and source-undefined work was distributed across audit summaries and validation reports.

**New behavior / value:**
- External hardware/camera acceptance and source-undefined policy decisions are separated into shared root documents with mandatory change control.

**Why this changed:**
- Keep teammates synchronized and prevent silent requirement, policy, mapping, or status changes.

**Source / decision reference:**
- Final deep audit and current project requirements.

**Validation performed:**
- Cross-checked against the final deep-audit coverage and existing validation reports.

**Requirement status after change:**
- Documentation/tracking added; software behavior unchanged.

**Impact on teammates:**
- Record every future requirement, policy, hardware, UI/API, and validation change here.

**Follow-up required:**
- Keep the log entry in the same commit as these tracking files and update it for every subsequent change.

## 2026-10-03 — SN1 Wi-Fi association and MQTT diagnostic

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- SN1 real Wi-Fi/MQTT transport diagnostic / HW-IOT-01

**Confirmed observation:**
- Local `firmware/sn1_mqtt/include/secrets.h` exists, contains a non-empty SSID, and is Git-ignored. Its password was not printed or logged.
- Wi-Fi scan found the configured SSID: `YES`; nearby networks: 7; configured RSSI: `-49 dBm`; encryption: `WPA2_PSK`.
- ESP32 initially reported status `6 (DISCONNECTED)`, then associated successfully with status `3 (CONNECTED)`.
- Assigned ESP32 IP: `172.20.10.2`.
- MQTT connected successfully to broker `172.20.10.12:1883` after Wi-Fi association.
- Real serial publish cycles followed with `dht_ok=1`, raw MQ-2 readings, IR states, button state, and `mqtt=CONNECTED`.
- No reset loop, brownout, watchdog, crash, or Wi-Fi disconnect was observed during the monitored connected period.

**Diagnostic change:**
- Added Wi-Fi scan visibility/RSSI/encryption reporting, numeric status names, bounded association timeout reporting, and assigned-IP reporting inside `firmware/sn1_mqtt` only.
- MQTT topics and payload contract were unchanged.

**Interpretation:**
- The prior failure stage was Wi-Fi association/authentication, not MQTT broker reachability. The configured SSID was visible and association now succeeds with the local secrets present.

**Validation performed:**
- Firmware build passed and uploaded to COM5 with hash verification.
- COM5 monitor at 115200 captured scan, association, IP, MQTT connection, and real sensor cycles.

**Impact on teammates:**
- No GPIO assignments, backend/frontend, MQTT contract, fusion, severity, dispatch, thresholds, or calibration policy changed.
- MQ-2 remains raw-only; temporary 20k/10k divider and calibration-pending status remain unchanged.

**Follow-up required:**
- Continue with prompted real MQTT/backend ingestion evidence and physical IR/button transitions; do not commit `secrets.h`.

## 2026-10-03 — SN1 MQTT firmware contract and build

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- SN1 real MQTT transport integration / HW-IOT-01

**MQTT contract recorded:**
- Topics: `city/sensors/mq2`, `city/sensors/dht22`, `city/sensors/ir_a`, `city/sensors/ir_b`, `city/sensors/button`.
- Required payload fields: `sensor_type`, `value`, ISO-8601 UTC `timestamp`, and `node_id`; optional `unit` and extra fields are accepted by the existing schema.
- Node ID: `SN1`.
- MQ-2 value is raw GPIO34 ADC only; no threshold or classification.
- DHT22 value is temperature in C with humidity and `dht_ok` extra fields.
- IR values use verified logical conversion: LOW means blocked (`true`), HIGH means clear (`false`).
- Button value uses verified logical conversion: LOW means pressed (`true`), HIGH means unpressed (`false`).
- Existing backend subscribes to `city/sensors/#` at QoS 1. Publisher QoS/retain behavior is not defined by the sensor contract; the firmware uses non-retained PubSubClient QoS 0 events.

**Implementation / validation:**
- Created separate `firmware/sn1_mqtt` project; preserved `firmware/sn1_bringup` unchanged.
- PlatformIO build passed for `esp32dev` with Arduino ESP32, DHT sensor library, and PubSubClient.
- Current active laptop Wi-Fi IPv4: `192.168.1.33`.
- Local broker reachability: `127.0.0.1:1883` TCP check passed.
- Backend MQTT ingestion is configured for `127.0.0.1:1883` and subscribes to `city/sensors/#`.
- Wi-Fi credentials were not present locally; upload and real MQTT E2E testing were not performed.

**Requirement status after change:**
- `PARTIAL` — firmware built, but secrets and real Wi-Fi/MQTT validation remain pending.

**Impact on teammates:**
- No backend contract, fusion/severity policy, GPIO assignment, threshold, or production behavior was changed.
- The temporary MQ-2 20k/10k divider remains temporary; calibration is pending and the final 10k/15k divider is not installed.

**Follow-up required:**
- Copy `firmware/sn1_mqtt/include/secrets.example.h` to ignored `include/secrets.h` and provide `CITYRESPONDER_WIFI_SSID`, `CITYRESPONDER_WIFI_PASSWORD`, and the laptop LAN `CITYRESPONDER_MQTT_HOST` before uploading to COM5.

## 2026-10-03 — SN1 MQ-2 temporary 20k/10k divider observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 MQ-2 baseline observation / HW-IOT-01

**Hardware context:**
- Earlier 100k/100k divider readings are non-final and are not treated as directly comparable calibration data.
- Current temporary divider: 20k upper resistor, 10k lower resistor, GPIO34 at the midpoint; MQ-2 VCC on VIN/5V, common GND, DO unused.
- Final project divider remains 10k upper / 15k lower and is not installed in this observation.

**Confirmed observation:**
- COM5 remained connected at 115200 for 310.3 seconds with the existing bring-up firmware.
- 310 structured samples were captured.
- MQ-2 raw ADC: first 99, last 48, minimum 9, maximum 112, average 61.41; zero readings: 0.
- Minute averages: minute 1 `84.28`; minute 2 `66.15`; minute 3 `58.20`; minute 4 `52.18`; minute 5 `48.20`.
- Final-minute minimum `9`, maximum `75`, average `48.16`, standard deviation `9.11`.
- Largest consecutive-sample change was 48 ADC (`51 -> 99`); no readings were removed.
- Trend classification: `STILL_DRIFTING`.
- DHT22 was valid on all 310 samples. IR1, IR2, and button remained readable; each reported HIGH throughout this window.
- No reset loop, brownout, watchdog, crash, or serial disconnect was observed.

**Validation performed:**
- Read-only serial capture and raw statistical analysis only.
- No flame/smoke/gas exposure, normalization, thresholding, alarm classification, or calibration was performed.

**Requirement status after change:**
- `PARTIAL` — new temporary-divider baseline recorded; MQ-2 calibration and production thresholds remain undefined.

**Impact on teammates:**
- No firmware, GPIO assignments, backend, MQTT, fusion, severity, or production behavior changed.

**Follow-up required:**
- Install the final 10k/15k divider when available and start a separate baseline series; do not compare raw scales as equivalent or validate backend 500/2000 values.

## 2026-10-03 — SN1 MQ-2 twenty-minute warm-up observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 MQ-2 baseline observation / HW-IOT-01

**Confirmed observation:**
- COM5 remained connected at 115200 for 1,210.9 seconds with the existing bring-up firmware.
- 1,210 structured samples were captured.
- MQ-2 raw ADC: first 76, last 64, minimum 0, maximum 110, overall average 68.41.
- Window averages: minute 1 `71.88`; minutes 1-5 `72.76`; minutes 6-10 `70.56`; minutes 11-15 `66.82`; minutes 16-20 `63.61`; final minute `62.90`.
- Final five minutes: minimum `0`, maximum `108`, average `63.74`, standard deviation `9.72`.
- Trend classification: `STILL_DRIFTING`, with notable noise/outliers. Lowest observed values were 0, 16, and 27; highest were 110, 108, and 108.
- DHT22 was valid on all 1,210 samples. IR1, IR2, and button remained readable; each reported HIGH throughout this window.
- No reset loop, brownout, watchdog, crash, or serial disconnect was observed.

**Validation performed:**
- Read-only serial capture and raw statistical analysis only.
- No flame/smoke exposure, normalization, thresholding, alarm classification, or calibration was performed.

**Requirement status after change:**
- `PARTIAL` — extended warm-up observation recorded; MQ-2 calibration and production thresholds remain undefined.

**Impact on teammates:**
- No firmware, GPIO assignments, backend, MQTT, fusion, severity, or production behavior changed.

**Follow-up required:**
- Continue controlled baseline captures after confirming sensor power/warm-up conditions; do not use the observed range as an alarm threshold.

## 2026-10-03 — SN1 MQ-2 ten-minute warm-up observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 MQ-2 baseline observation / HW-IOT-01

**Confirmed observation:**
- COM5 remained connected at 115200 for 610.4 seconds with the existing bring-up firmware.
- 610 structured samples were captured.
- MQ-2 raw ADC: first 98, last 74, minimum 9, maximum 154, overall average 78.76.
- First-minute average: 84.26; final-minute average: 77.02; approximate early-to-late change: -7.24 ADC (-8.6%).
- Trend classification: `STILL_DRIFTING` (modest downward change; no production interpretation).
- DHT22 was valid on all 610 samples. IR1, IR2, and button remained readable; each reported HIGH throughout this window.
- No reset loop, brownout, watchdog, crash, or serial disconnect was observed.

**Validation performed:**
- Read-only serial capture and raw statistical analysis only.
- No flame/smoke exposure, normalization, thresholding, alarm classification, or calibration was performed.

**Requirement status after change:**
- `PARTIAL` — warm-up observation recorded; MQ-2 calibration and production thresholds remain undefined.

**Impact on teammates:**
- No firmware, GPIO assignments, backend, MQTT, fusion, severity, or production behavior changed.

**Follow-up required:**
- Allow further warm-up/repeated baseline captures under controlled conditions before defining calibration values; do not use these observations as alarm thresholds.

## 2026-10-03 — SN1 button INPUT_PULLUP confirmed

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed physical observation:**
- COM5 at 115200 was observed with the existing bring-up firmware after correcting the GND-side wiring.
- Button unpressed: `HIGH`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `HIGH`, stable across consecutive readings.
- Exact observed sequence: `HIGH -> LOW -> HIGH`.
- `INPUT_PULLUP_CONFIRMED`.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Preserve the corrected physical wiring and use this verified button behavior in future hardware integration work.

## 2026-10-03 — SN1 button corrected GND-side characterization third repeat

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed repeat observation:**
- COM5 at 115200 was observed with the existing bring-up firmware after the reported GND-side correction.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- Exact observed sequence: `LOW -> LOW -> LOW` (`BUTTON_STUCK_LOW`).

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Recheck the physical switch contact pair, orientation, and GND-side continuity with a meter; compare with the known-good disconnected HIGH test.

## 2026-10-03 — SN1 button corrected GND-side characterization repeat

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed repeat observation:**
- COM5 at 115200 was observed with the existing bring-up firmware after the reported GND-side correction.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- Exact observed sequence: `LOW -> LOW -> LOW` (`BUTTON_STUCK_LOW`).

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Recheck the physical switch contact pair, orientation, and GND-side continuity with a meter; compare with the known-good disconnected HIGH test.

## 2026-10-03 — SN1 button corrected GND-side characterization

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed physical observation:**
- After the reported GND-side correction, COM5 at 115200 was observed with the existing bring-up firmware.
- Button unpressed: `HIGH`, stable across consecutive readings.
- Button pressed and held: `HIGH`, stable across consecutive readings.
- Button released: `HIGH`, stable across consecutive readings.
- Exact observed sequence: `HIGH -> HIGH -> HIGH`.
- `INPUT_PULLUP_CONFIRMED` was not observed because pressing did not pull GPIO27 LOW.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Verify the switch’s actual contact pairs and orientation with a continuity meter; ensure GPIO27 and GND are on opposite sides of the normally-open contact, not on the same internally connected side.

## 2026-10-03 — SN1 button GND-jumper isolation test

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button wiring diagnostic / HW-IOT-01

**Confirmed observation:**
- GPIO27 remained connected to the button.
- Only the button-to-GND jumper was removed; the button was left unpressed.
- COM5 at 115200 reported button `HIGH` across consecutive readings.
- This isolates the permanent LOW to the button GND-side wiring, button leg/orientation, or breadboard row/short when the GND jumper is installed.

**Validation performed:**
- Read-only serial observation; no firmware upload or source changes.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Correct the button GND leg/orientation and breadboard row placement; reconnect GND only after verifying it is on the intended button leg.

## 2026-10-03 — SN1 button post-rewire characterization repeat

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed repeat observation:**
- After reported physical rewiring, COM5 at 115200 was observed using the existing bring-up firmware.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- Result remains `BUTTON_STUCK_LOW`; `INPUT_PULLUP_CONFIRMED` was not observed.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Recheck the complete physical button circuit against the authoritative hardware reference and the known-good disconnected HIGH test.

## 2026-10-03 — SN1 button post-rewire characterization

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed physical observation:**
- After reported physical rewiring, COM5 at 115200 was observed using the existing bring-up firmware.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- The expected `HIGH -> LOW -> HIGH` INPUT_PULLUP behavior was not observed; result remains `BUTTON_STUCK_LOW`.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Recheck the physical wiring against the authoritative reference, including button orientation, GPIO27 row/jumper, GND row/jumper, and continuity; compare with the known-good disconnected HIGH result.

## 2026-10-03 — SN1 button disconnected GPIO27 diagnostic

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button wiring diagnostic / HW-IOT-01

**Confirmed observation:**
- The ESP32 was power-cycled with the push button and its GPIO27/GND jumper connections disconnected.
- COM5 at 115200 streamed the existing bring-up firmware.
- GPIO27 raw button reading was `HIGH` across consecutive samples.
- This confirms the ESP32 GPIO27 input and firmware `INPUT_PULLUP` behavior function without the button connected.
- Prior `BUTTON_STUCK_LOW` result is therefore localized to the physical button wiring, button orientation, breadboard row, or an unintended connection while installed.

**Validation performed:**
- Read-only serial observation; no firmware upload or source changes.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Reconnect the button wiring carefully, verify its orientation and GPIO27/GND rows, then repeat unpressed/pressed/released testing.

## 2026-10-03 — SN1 button characterization second repeat

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed repeat observation:**
- COM5 streamed the existing SN1 bring-up firmware at 115200.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- Result remains `BUTTON_STUCK_LOW`; expected `HIGH -> LOW -> HIGH` INPUT_PULLUP behavior was not observed.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical button state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Inspect button orientation, GPIO27 continuity, breadboard row placement, and ground connection before any firmware change.

## 2026-10-03 — SN1 button characterization repeat

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 button hardware characterization / HW-IOT-01

**Confirmed repeat observation:**
- COM5 streamed the existing SN1 bring-up firmware at 115200.
- Button unpressed: `LOW`, stable across consecutive readings.
- Button pressed and held: `LOW`, stable across consecutive readings.
- Button released: `LOW`, stable across consecutive readings.
- Result remains `BUTTON_STUCK_LOW`; expected `HIGH -> LOW -> HIGH` INPUT_PULLUP behavior was not observed.

**Validation performed:**
- Read-only serial observation only; no firmware upload or source changes.
- Each physical button state was held and sampled for multiple seconds.

**Impact on teammates:**
- No GPIO assignments, firmware, polarity assumptions, thresholds, backend, MQTT, or production behavior changed.

**Follow-up required:**
- Inspect button orientation, GPIO27 continuity, breadboard row placement, and ground connection before any firmware change.

## 2026-10-03 — SN1 IR/button physical characterization

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 hardware characterization / HW-IOT-01

**Files changed:**
- `TEAM_CHANGE_LOG.md`

**Confirmed physical observations:**
- IR1: clear `HIGH`, blocked `LOW`, clear-again `HIGH`.
- IR2: clear `HIGH`, blocked `LOW`, clear-again `HIGH`.
- Button: unpressed `LOW`, pressed `LOW`, released `LOW`; recorded as `BUTTON_STUCK_LOW`.
- No firmware polarity or GPIO changes were made.

**Raw health observations:**
- MQ-2 raw readings during staged characterization ranged approximately 142-213 ADC; a final clean 20-second window measured 149-161 ADC, average 157.25. Values decreased over the session; no threshold or alarm interpretation was applied.
- DHT22 remained valid (`dht_ok=1`); observed temperature was 30.7-31.1 C and humidity 73.1-74.1%.

**Source / decision reference:**
- `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`
- `HARDWARE_EXTERNAL_REQUIREMENTS.md` HW-IOT-01

**Validation performed:**
- Read-only COM5 serial observation at 115200 using the existing isolated SN1 bring-up firmware.
- Each IR state was held and sampled across consecutive readings; each button state was held and sampled across consecutive readings.

**Requirement status after change:**
- `PARTIAL` — IR transitions characterized; button does not exhibit the expected INPUT_PULLUP transition and requires physical inspection.

**Impact on teammates:**
- No backend, MQTT/Wi-Fi/API, fusion, severity, dispatch, thresholds, sensor polarity configuration, GPIO assignment, or production firmware was changed.

**Follow-up required:**
- Inspect button wiring/orientation, GPIO27 continuity, and ground connection. Do not change firmware until wiring is verified.

## 2026-10-03 — SN1 isolated bring-up firmware and real baseline

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 hardware bring-up / HW-IOT-01

**Files changed:**
- `firmware/sn1_bringup/platformio.ini`
- `firmware/sn1_bringup/src/main.cpp`
- `firmware/sn1_bringup/README.md`
- `TEAM_CHANGE_LOG.md`

**New behavior / value:**
- Built and uploaded the isolated raw-only SN1 bring-up firmware to COM5.
- PlatformIO monitor at 115200 produced real structured sensor output for more than 20 seconds.
- DHT22 reported `dht_ok=1`, 30.8 C, and 73.9-74.0% humidity.
- IR1, IR2, and button each remained raw `LOW` during the observation; no polarity or physical meaning was inferred.
- MQ-2 raw ADC readings ranged from 206 to 250, average 235.26 across 23 samples; no threshold was applied.
- ESP32 boot output showed `POWERON_RESET`; no brownout, watchdog, crash, or reset-loop diagnostic was observed after startup.

**Why this changed:**
- Record only verified real-device bring-up output while preserving production firmware, hardware assignments, and calibration policy.

**Source / decision reference:**
- `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`
- `HARDWARE_EXTERNAL_REQUIREMENTS.md` HW-IOT-01

**Validation performed:**
- PlatformIO Core 6.1.19, Espressif32 7.0.0, Arduino ESP32 framework, `esp32dev`.
- Build passed; upload to COM5 passed with flash hash verification and automatic RTS reset.
- Serial output observed at 115200 for approximately 23 seconds.

**Requirement status after change:**
- `PARTIAL` — raw serial bring-up verified; calibration, polarity, route behavior, and full HW-IOT-01 integration remain unverified.

**Impact on teammates:**
- No production backend, frontend, MQTT/Wi-Fi/API, fusion, severity, dispatch, AC1, GPIO assignment, or threshold behavior was changed.

**Follow-up required:**
- Physically test IR1 clear/blocked, IR2 clear/blocked, and button unpressed/pressed states; perform MQ-2 warm-up and later calibration on the real prototype.

## 2026-10-03 — SN1 COM5 serial observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 hardware bring-up / HW-IOT-01

**Files changed:**
- `TEAM_CHANGE_LOG.md`

**Previous behavior / value:**
- COM5 was reported as the connected SN1 port but had not yet been observed in this session.

**New behavior / value:**
- COM5 opened successfully at 115200 with DTR/RTS disabled.
- A 30-second read-only observation received zero bytes.
- No boot log, reset/brownout/watchdog message, DHT22 output, IR output, button output, or MQ-2 raw ADC output was observed.

**Why this changed:**
- Record the verified serial-port access and absence of observable firmware output without uploading or inferring sensor behavior.

**Source / decision reference:**
- `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`
- `HARDWARE_EXTERNAL_REQUIREMENTS.md` HW-IOT-01

**Validation performed:**
- Repository/config search found no defined serial baud rate.
- Safe .NET serial access at 115200 with DTR/RTS disabled.
- 30-second COM5 observation; zero bytes received.

**Requirement status after change:**
- `BLOCKED_EXTERNAL` — serial port accessible, but no observable SN1 firmware output.

**Impact on teammates:**
- No GPIO, firmware, calibration, backend, fusion, severity, dispatch, or requirement values were changed.

**Follow-up required:**
- `SN1 bring-up firmware required`.

## 2026-10-03 — SN1 serial-port detection bring-up observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 hardware bring-up / HW-IOT-01

**Files changed:**
- `TEAM_CHANGE_LOG.md`

**Previous behavior / value:**
- No real serial-port observation recorded for this bring-up session.

**New behavior / value:**
- Windows exposed COM3 and COM4, both identified as `Standard Serial over Bluetooth link`.
- COM3 opened safely at 115200 with DTR/RTS disabled and produced zero bytes during a 30-second observation.
- COM4 could not be opened because its Bluetooth serial link returned a semaphore timeout.
- No ESP32 USB VID/PID, SN1 firmware output, boot log, or sensor readings were observed.

**Why this changed:**
- Record the real device-detection result without treating Bluetooth ports or empty output as SN1 evidence.

**Source / decision reference:**
- `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`
- `HARDWARE_EXTERNAL_REQUIREMENTS.md` HW-IOT-01

**Validation performed:**
- Windows `Win32_SerialPort` and Plug-and-Play enumeration.
- Safe .NET serial access check with DTR/RTS disabled.
- 30-second COM3 observation at 115200; zero bytes received.

**Requirement status after change:**
- `BLOCKED_EXTERNAL` — no ESP32 SN1 USB serial device identified.

**Impact on teammates:**
- No GPIO, firmware, calibration, backend, fusion, severity, dispatch, or requirement values were changed.

**Follow-up required:**
- Connect the SN1 ESP32 USB device and repeat serial detection; next implementation task is `SN1 bring-up firmware required` if no sensor firmware is present.

## 2026-10-03 — SN1 real MQTT end-to-end validation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 MQTT transport, backend ingestion, persistence, and live-update observation / HW-IOT-01

**Confirmed observation:**
- Direct broker observation on `127.0.0.1:1883` received real SN1 messages on `city/sensors/dht22`, `city/sensors/mq2`, `city/sensors/ir_a`, `city/sensors/ir_b`, and `city/sensors/button`.
- Payloads contained the expected sensor fields, `node_id=SN1`, and valid UTC timestamps.
- Existing backend MQTT ingestion connected to the broker and accepted the real messages as `sensor_reading` events. API queries returned persisted DHT22, raw MQ-2, IR, and button events.
- Authenticated `/ws/live` delivered a real SN1 sensor event with backend event and broadcast timestamps.
- IR1 blocked stage: consecutive `IR_A` messages were `raw=LOW`, `value=true`; IR1 clear stage: consecutive messages were `raw=HIGH`, `value=false`. Matching backend events were observed for both.
- IR2 blocked stage remained `raw=LOW`, `value=true`, matching the pre-test observed state; no blocked transition was demonstrated. IR2 clear stage then produced consecutive `raw=HIGH`, `value=false` messages and a matching persisted event.
- Button pressed stage: consecutive `BUTTON` messages were `raw=LOW`, `value=true`; released stage: consecutive messages were `raw=HIGH`, `value=false`. Matching backend events were observed.
- Repeated one-second readings had unique backend event IDs; no duplicate or malformed payload was observed in the captured windows.

**Boundary / interpretation:**
- MQ-2 transport was verified as raw ADC data only. Calibration, fire threshold, backend `500/2000` validation, and final `10k/15k` divider installation remain incomplete.
- No routing, fusion, severity, dispatch, GPIO, firmware, MQTT contract, backend production code, or frontend code was changed for this validation.

**Validation performed:**
- Real broker subscription, existing backend startup on port 8010, authenticated sensor API queries, and authenticated live WebSocket observation.
- No synthetic MQTT publishes or manual database mutations were used.

**Requirement status after change:**
- `PARTIAL` — transport, ingestion, persistence, and live path verified; IR2 blocked transition remains unverified.

**Follow-up required:**
- Repeat IR2 blocked with a confirmed physical transition, then continue AC1/actuator validation. Keep MQ-2 raw-only and calibration-pending.

## 2026-10-03 — IR2 real MQTT transition verification

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 IR2 physical transition through MQTT, backend persistence, and live updates

**Confirmed observation:**
- Clear precondition passed: six consecutive real `IR_B` MQTT readings were `raw=HIGH`, `value=false`.
- After the physical block, real `IR_B` readings changed to `raw=LOW`, `value=true`; the first blocked persistence observed was event ID `2164`.
- The backend accepted and persisted the blocked event, and the live WebSocket delivered event ID `2164` with the same payload.
- After the object was removed, real `IR_B` readings changed back to `raw=HIGH`, `value=false`; the live WebSocket delivered the clear transition (event ID `2224` observed).
- No synthetic MQTT messages or manual database mutations were used.

**Requirement status after change:**
- `PASS` — real transition `HIGH -> LOW -> HIGH` demonstrated through ESP32 MQTT output, backend ingestion, persistence, and live delivery.

**Impact on teammates:**
- No production code, firmware, GPIO assignments, sensor polarity, MQTT contract, calibration, routing, or thresholds changed.

**Follow-up required:**
- Continue with the next explicitly requested hardware validation; keep MQ-2 calibration and production thresholds pending.

## 2026-10-03 — Final MQ-2 divider hardware decision

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Current CityResponder SN1 MQ-2 hardware source of truth

**Final team hardware decision:**
- MQ-2 AO upper resistor: `20kΩ`.
- MQ-2 divider lower resistor: `10kΩ`.
- GPIO34 is connected to the divider midpoint.
- This 20k upper / 10k lower divider is the final project configuration selected for the physical prototype.
- The previous 10k upper / 15k lower reference is superseded for current wiring.

**Calibration boundary:**
- Baseline and calibration data collected with 10k/15k, 20k/10k temporary, or 100k/100k arrangements are not directly reusable as equivalent calibration data.
- A new MQ-2 calibration baseline must start with the final 20k/10k divider.
- Backend `500/2000` values remain not physically validated; no production threshold is established.

**Documentation updated:**
- `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`
- `firmware/sn1_bringup/README.md`

**Impact on teammates:**
- No GPIO number, MQTT topic/payload, firmware behavior, backend logic, fusion policy, or threshold was changed.

## 2026-10-03 — Final 20-minute MQ-2 baseline with 20k/10k divider

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real SN1 MQ-2 baseline observation after final hardware decision

**Hardware:**
- Final divider: `20kΩ` upper / `10kΩ` lower, with GPIO34 at the midpoint.
- The prior 10k/15k reference is superseded. Earlier data from other divider ratios is not treated as directly reusable calibration data.

**Confirmed observation:**
- Real MQTT observation duration: `1200.86 s`.
- Usable MQ-2 samples: `1201`; first raw `0`; last raw `0`; minimum `0`; maximum `22`; overall average `0.1074`.
- Window averages: minute 1 `0.0000`; minutes 1-5 `0.1100`; minutes 6-10 `0.1572`; minutes 11-15 `0.0532`; minutes 16-20 `0.1100`; final minute `0.1833`.
- Final five minutes: minimum `0`, maximum `18`, average `0.1100`, population standard deviation `1.1451`.
- Zero readings: `1181/1201`.
- Obvious isolated spikes included raw `22`, `18`, and `14` readings with abrupt returns to zero; no samples were removed.
- Trend classification: `NOISY`; the series is mostly zero but has intermittent spikes and is not treated as stable enough for response characterization.
- DHT22 health-check messages: `1200/1200` valid (`30.3–30.8°C`, `73.7–75.0% RH`). IR1, IR2, and button messages remained readable. MQTT connected once and had no disconnect before the planned observation stop.

**Calibration boundary:**
- MQ-2 calibration remains incomplete.
- No production threshold was established.
- Backend `500/2000` values remain not physically validated.

**Impact on teammates:**
- No firmware, GPIO, MQTT contract, backend logic, fusion/severity policy, or threshold was changed.

**Follow-up required:**
- Do not create production thresholds from this run. Investigate the intermittent near-zero/spike behavior and repeat controlled baseline/response characterization only after the final-divider signal is confirmed healthy.

## 2026-10-03 — AC1 USB serial detection attempt

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 actuator-node detection / HW-IOT-03

**Confirmed observation:**
- Windows exposed Bluetooth serial links on COM3 and COM4; these were excluded.
- The only present USB serial device was `Silicon Labs CP210x USB to UART Bridge (COM5)`, PnP ID `USB\VID_10C4&PID_EA60\0001` (`VID_10C4`, `PID_EA60`).
- COM5 is the previously assigned SN1 port, so it was not treated as AC1.
- No second USB serial port, unknown USB-UART device, or present USB device with a driver error was detected.
- No AC1 serial port could be identified safely; therefore no AC1 port was opened and no serial output was observed.

**Requirement status after change:**
- `BLOCKED_EXTERNAL` — AC1 is not currently enumerating as a distinct USB serial device.

**Impact on teammates:**
- No actuator was tested, no command was sent, and no firmware, GPIO, backend, frontend, MQTT, or SN1 configuration was changed.

**Follow-up required:**
- Reconnect AC1 using a known data-capable USB cable/port and repeat Windows PnP enumeration until a USB serial device distinct from SN1 COM5 appears.

## 2026-10-03 — AC1 USB serial detection and passive observation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 actuator-node detection / HW-IOT-03

**Confirmed observation:**
- Windows detected a second `Silicon Labs CP210x USB to UART Bridge` on COM7.
- AC1 PnP identity: `USB\VID_10C4&PID_EA60\6&4420B4E&0&2` (`VID_10C4`, `PID_EA60`).
- AC1 COM7 is distinct from SN1 COM5, whose PnP identity remains `USB\VID_10C4&PID_EA60\0001`.
- Bluetooth COM3 and COM4 were excluded.
- COM7 opened successfully at 115200 with DTR/RTS disabled.
- A 25.41-second read-only observation received zero bytes and zero serial lines.
- No ESP32 boot log, actuator firmware output, reset loop, brownout, watchdog, Guru Meditation, or crash output was observed.

**Requirement status after change:**
- `BLOCKED_EXTERNAL` — AC1 is reachable as a USB serial device, but no useful actuator firmware output exists; AC1 hardware validation is not PASS.

**Impact on teammates:**
- No actuator was energized or tested, no command was sent, and no firmware, GPIO, backend, frontend, MQTT, or SN1 configuration was changed.

**Follow-up required:**
- `AC1 bring-up firmware required`; create and flash it only in a separately authorized task, testing LEDs first, buzzer polarity later, and the unpowered servo last.

## 2026-10-03 — AC1 isolated bring-up firmware and safe startup

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 actuator-node bring-up / HW-IOT-03

**Implementation:**
- Added isolated PlatformIO project `firmware/ac1_bringup` for ESP32 DevKit V1 on COM7.
- Preserved the authoritative GPIO map: TL1 red/yellow/green GPIO25/26/27; TL2 red/yellow/green GPIO14/13/23; buzzer GPIO19; servo signal GPIO18.
- Startup leaves all LED outputs LOW, the buzzer released as a high-impedance input, and the servo signal unattached as an input.
- Added manual serial commands for individual LED ON/OFF control, all LEDs OFF, controlled buzzer HIGH/LOW/release, and non-actuating status reporting.
- No Wi-Fi, MQTT, ACK, backend dispatch, servo control, or automatic actuator sequence was added.

**Verified observation:**
- PlatformIO build passed.
- Upload to AC1 COM7 passed with flash hash verification; SN1 COM5 was not used.
- A non-actuating `STATUS` command returned all six LED GPIOs LOW, buzzer `RELEASED`, servo `NOT_ATTACHED`, and `ready=YES`.
- No reset loop, brownout, watchdog, Guru Meditation, or crash output was observed during the serial checks.
- Traffic Light 1 Red on GPIO25 was physically confirmed visibly ON after `TL1_R_ON`/HIGH and OFF after `TL1_R_OFF`/LOW.
- Traffic Light 1 Yellow on GPIO26 was physically confirmed visibly ON after `TL1_Y_ON`/HIGH and OFF after `TL1_Y_OFF`/LOW.
- Traffic Light 1 Green on GPIO27 was physically confirmed visibly ON after `TL1_G_ON`/HIGH and OFF after `TL1_G_OFF`/LOW.
- Traffic Light 2 Red on GPIO14 was physically confirmed visibly ON after `TL2_R_ON`/HIGH and OFF after `TL2_R_OFF`/LOW.
- Traffic Light 2 Yellow on GPIO13 was physically confirmed visibly ON after `TL2_Y_ON`/HIGH and OFF after `TL2_Y_OFF`/LOW.
- Traffic Light 2 Green on GPIO23 was physically confirmed visibly ON after `TL2_G_ON`/HIGH and OFF after `TL2_G_OFF`/LOW.
- All six traffic-light channels are physically verified; buzzer polarity and servo remain unverified.
- Buzzer GPIO19 polarity was physically tested with short pulses: HIGH was silent, LOW produced sound; the pin was released after each pulse.
- User confirmed SG90 signal GPIO18, 5V/VIN power, common GND, a visible horn reference, and an unobstructed horn before testing. `SERVO_SET_30` was accepted, but the user observed no physical movement; `SERVO_SET_90` was not attempted. The servo was released and is not marked PASS.
- No jitter, stall behavior, brownout, reset, watchdog, Guru Meditation, or serial interruption was observed during the single attempted movement.

**Requirement status after change:**
- `PARTIAL` — AC1 firmware build/upload/serial readiness passed; physical actuator validation remains pending.

**Follow-up required:**
- Inspect the servo signal/power path and repeat a single controlled movement only after the physical cause of the no-movement result is addressed; do not infer PASS from serial command acceptance.

## 2026-10-03 — AC1 SG90 servo physical validation PASS

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 servo movement / HW-IOT-03

**Confirmed observation:**
- User reconfirmed servo signal GPIO18, 5V/VIN or regulated 5V power, common GND, visible horn reference, and unobstructed movement.
- `SERVO_SET_30` produced a physically observed 30° position.
- `SERVO_SET_90` produced a physically observed movement from 30° to 90°.
- A second `SERVO_SET_30` produced a physically observed return to 30°.
- Servo was then released/detached with `SERVO_RELEASE`.
- No jitter, stall, brownout, reset, watchdog, Guru Meditation, crash, or serial interruption was observed.

**Requirement status after change:**
- `PASS` — physical 30° → 90° → 30° movement verified with stable AC1 runtime.

**Impact on teammates:**
- No backend, frontend, MQTT, ACK, GPIO assignment, or production command logic changed.

**Follow-up required:**
- Keep the servo power/common-ground arrangement documented; do not infer production open/closed angles from this movement check without a separately approved calibration step.

## 2026-10-03 — AC1 real MQTT command/ACK validation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 Wi-Fi → MQTT actuator command → correlated ACK / HW-IOT-03

**Contract confirmed from existing backend:**
- Commands: `city/commands/AC1`, QoS 1, non-retained.
- ACKs: `city/acks/AC1`, QoS 1, non-retained.
- Node ID: `AC1`; command type: `PHYSICAL_ACTION`.
- Required envelope: `command_id`, `node_id`, `command_type`, `payload`, ISO timestamp.
- Physical payload fields: `action_category`, `action_type`, `parameters`, `spec_id`, `attempt_number`, and `safe_default`.
- ACK correlation is exact `command_id` + `node_id`; backend timeout is 500 ms with one retry.
- Existing backend does not define duplicate-command behavior; no duplicate policy was claimed or validated.

**Implementation:**
- Added isolated `firmware/ac1_mqtt`; `firmware/ac1_bringup` was not changed.
- Preserved AC1 GPIO assignments and active-low buzzer mapping (ON=GPIO19 LOW, OFF=HIGH).
- Safe startup is all traffic LEDs off, buzzer off, servo unattached.
- `TRAFFIC/ALL_RED`, `TRAFFIC/GREEN_CORRIDOR` (documented MAIN/TL1 preference), `TRAFFIC/OFF`, and `BUZZER/ON|OFF` are implemented.
- `GATE/OPEN|CLOSE` is rejected with `SERVO_PRODUCTION_ANGLES_REQUIRED`; no servo command was executed because production angles remain undefined.
- Increased the PubSubClient packet buffer to 1024 bytes after the first full contract envelope exceeded its 256-byte default; no backend contract change was made.
- Added an AC1 secrets example and Git-ignore rule; no password was committed.

**Network / firmware evidence:**
- Active laptop Wi-Fi IPv4: `172.20.10.12`; Mosquitto listened on `0.0.0.0:1883`.
- AC1 serial: COM7; assigned IP `172.20.10.3`; Wi-Fi RSSI observed at `-82 dBm` after upload; MQTT connected to `172.20.10.12:1883`; NTP synchronized.
- Build passed and upload to COM7 passed with flash hash verification.

**Real command/ACK evidence (all matching ACKs within backend 500 ms):**
- `TRAFFIC/ALL_RED`: command `b9f98032-67d5-4588-85ff-6914e18859ff`, 282.9 ms; TL1 red physically confirmed ON.
- `TRAFFIC/GREEN_CORRIDOR`: command `7f304aeb-3233-426a-82d9-401196c35d7d`, 360.7 ms; TL1 green physically confirmed ON.
- `TRAFFIC/OFF`: command `d1a73903-f74b-410e-81a7-ac4ce6571a7e`, 85.4 ms; all traffic lights physically confirmed OFF.
- `BUZZER/ON`: command `3d4994d6-4763-4dca-ba15-b97fa5a1fb1e`, 414.7 ms; sound physically confirmed.
- `BUZZER/OFF`: command `9b4debe0-e86f-4018-8afc-309c406d7d28`, 199.2 ms; silence physically confirmed.
- Repeat `TRAFFIC/ALL_RED`: command `bbbb9b7e-7506-4aa2-bf55-294b2e130ed8`, 86.7 ms; both red lamps physically confirmed ON (TL1 and TL2).
- First pre-buffer command attempt produced no ACK; it was not counted as a successful test. The packet-buffer correction above resolved the issue.

**Validation boundaries:**
- Yellow lamps and TL2 green were not independently commandable through the existing backend contract, so no independent MQTT PASS is claimed for those channels.
- Servo movement was verified previously, but production open/closed angles remain uncalibrated; gate commands were not tested.
- Full failsafe sequence was not tested. No reset loop, brownout, watchdog, or crash was observed during the successful AC1 MQTT checks.

**Requirement status after change:**
- `PARTIAL` — real AC1 Wi-Fi/MQTT/ACK and selected physical actuator paths passed; contract coverage does not independently expose all lamp channels, and servo production angles remain required.

**Follow-up required:**
- Define approved per-lamp traffic command parameters (if independent yellow/TL2-green validation is required) without changing GPIO assignments; separately calibrate and approve production servo open/closed angles before enabling gate actions.

## 2026-10-03 — AC1 production gate servo calibration and MQTT validation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Requirement / area:**
- Real AC1 gate calibration and MQTT GATE OPEN/CLOSE validation / HW-IOT-03

**Physical calibration evidence:**
- Using controlled manual COM7 calibration, 30° was physically confirmed as the smallest tested clearly closed position.
- 90° and 100° were physically not open enough; 110° was also physically not open enough.
- 120° was physically confirmed as sufficiently open, with no reported mechanical strain.
- Repeatability passed for three closed/open cycles: 30° CLOSED → 120° OPEN → 30° CLOSED → 120° OPEN → 30° CLOSED.
- No jitter, stall, mechanical strain, brownout, reset, watchdog, or crash was reported during calibration.

**Production firmware change:**
- Applied `GATE_CLOSED_ANGLE=30` and `GATE_OPEN_ANGLE=120` in `firmware/ac1_mqtt`.
- Added ESP32Servo support while preserving GPIO18 and all existing AC1 GPIO assignments.
- GATE OPEN/CLOSE now actuate only these approved angles; startup remains servo-unattached and non-actuating.
- A repeated same-command delivery was observed during the first final-build close observation. Added exact `command_id` duplicate protection: duplicates are ACKed with `DUPLICATE_ALREADY_APPLIED` and do not re-actuate hardware.
- Manual calibration commands were added temporarily to `firmware/ac1_bringup` for 100°, 110°, and 120°; no GPIO mapping changed.

**Final-build MQTT evidence:**
- GATE OPEN command `bccb7982-e39a-4146-bbce-7ddcdc702bc3`: matching ACK, physical OPEN confirmed, latency 584.7 ms (outside the backend 500 ms target).
- GATE CLOSE command `110a0d4d-3da9-4e31-9773-0f327beb2044`: matching ACK, physical CLOSED confirmed, latency 287.4 ms (within the backend 500 ms target).
- AC1 reconnected to Wi-Fi/MQTT/NTP after final upload at `172.20.10.3` / broker `172.20.10.12:1883`; a 25-second serial monitor showed no reset loop, brownout, watchdog, crash, or repeated gate command after duplicate protection.

**Requirement status after change:**
- `PARTIAL` — production angles and physical repeatability are verified; final OPEN ACK exceeded the 500 ms target while CLOSE met it. Full backend retry/failsafe E2E remains untested.

**Follow-up required:**
- Investigate the occasional >500 ms OPEN ACK latency before claiming timing reliability. Then perform the separately authorized full AC1 backend command/ACK/retry/failsafe E2E validation; do not run the failsafe in this calibration task.

## Change entries

<!-- Add newest entries above older entries. -->

## 2026-10-03 15:17 — Approved policy for Area Risk (TBD-RISK-01 to 09)

**Changed by:** Zhen Jie
**Branch:** main
**Commit:** not committed yet
**Approved by:** Zhen Jie (section owner); no separate team sign-off requested

**Requirement / area:**
- TBD-RISK-01 to TBD-RISK-09 (Area Risk F / R / E / A / M, `SOURCE_TBD_REQUIREMENTS.md` section 7)

**Files changed:**
- `area_risk.md` (new requirement file)

**Previous behavior / value:**
- `TBD_SOURCE`. The proposal gives the formula `100 * (0.30F + 0.25R + 0.20E + 0.15A + 0.10M)` and the 180-day verified-only rule, but does not say what F, R, E, A, M mean.

**New behavior / value (approved, not yet implemented):**
- Every component is in [0, 1]. A component that cannot be calculated makes the score `not_calculated` (no silent zero).
- Counted incidents: operator-verified real fires (state `VERIFIED_FIRE`) with an assigned area, whose start time is within the last 180 days.
- `F = n_a / max over all areas n_b` (frequency, relative to the busiest area).
- `R = max(0, 1 - d / 180)`, `d` = days since the area's latest verified incident (recency).
- `E` = average of `s_i` over the area's verified incidents, `s_i = severity R / 100`, or `1.0` if the Critical person override applied (escalation).
- `A` = share of the area's verified incidents whose dispatch route had a blocked or conflict-pruned edge or needed a reroute (access).
- `M` = failed checks / 3 from the area config: fire certificate valid, alarm audible, escape routes unobstructed (readiness gap). Set by the City Risk Planner.
- Area = one structure ROI on the tabletop model. Incident area = ROI containing the fire detection center (larger overlap if two); if there is no detection, the operator chooses the area when verifying. `area_id` is stored on the incident.
- Cold start: `n_a = 0` shows "No verified history"; `n_a = 1` shows "Insufficient history (1 of 2)"; `n_a >= 2` shows the score. `N_min = 2` is a config value.
- No Low / Medium / High bands until defined. The "possible electrical-risk hotspot; inspection recommended" wording appears only at 3 or more verified incidents (config value).
- No what-if or predictive simulation; the page is described as a historical Area Risk Index.

**Why this changed:**
- Section 7 was assigned to Zhen Jie. The proposal leaves F, R, E, A, M undefined, so the meanings are design choices built from data the system already records and from proposal section 3.2. They are not source-defined.

**Source / decision reference:**
- Proposal sections 4.4 and 5.1; Zhen Jie decisions (choice of meanings, `N_min = 2`, repeated = 3); Hong Jia Bao log entry 2026-10-02 22:45 for incident states.

**Validation performed:**
- None. Documentation only; no code, test or scenario was run.

**Requirement status after change:**
- `PARTIAL`. The policy is approved by Zhen Jie and the TBD item is resolved at policy level; implementation and validation are not done yet. No software behavior changed.

**Impact on teammates:**
- Once implemented, backend needs: `area_id` on incidents, the five component calculations, and cold-start messages on the `/risk` page.
- Depends on: Hong Jia Bao's `VERIFIED_FIRE` state, the severity score (E), routing blockage events logged per incident (A), and the final area/ROI list (TBD-ROUTE-07).

**Follow-up required:**
- Fill in the area list and names (from TBD-ROUTE-07). Confirm with Hong Jia Bao how H (TBD-FUSION-04) uses history, and the difference between `VERIFIED` and `VERIFIED_FIRE`.

## 2026-10-03 15:17 — Approved policy for Adaptive Calibration (TBD-CAL-01 to 10)

**Changed by:** Zhen Jie
**Branch:** main
**Commit:** not committed yet
**Approved by:** Zhen Jie (section owner); no separate team sign-off requested

**Requirement / area:**
- TBD-CAL-01 to TBD-CAL-10 (Adaptive Calibration Learning Policy, `SOURCE_TBD_REQUIREMENTS.md` section 8)

**Files changed:**
- `adaptive_calibration.md` (new requirement file)

**Previous behavior / value:**
- `TBD_SOURCE` for feature/label representation, loss, update equation, validation metric, gate, dataset selection, baseline version, activation and rollback policy. Already source-defined: step 0.02, weights in [0.10, 0.50], sum 1.00, 30 training / 15 validation outcomes, Admin approval, versioning, rollback.

**New behavior / value (approved, not yet implemented):**
- Sample: `x = (S, T, V, H)` from the window that completed the 3-window rule; eligible only if all four channels were `available`.
- Label: `VERIFIED_FIRE` gives `y = 1`, `REJECTED` gives `y = 0`; `CANCELLED` is not used.
- Loss and validation metric: Brier score `(1/n) * sum (w·x - y)^2`.
- Update: batch gradient over the 30 training samples, `w_candidate = Project(w_active - 0.02 * g)`, `g = (2/30) * sum (w·x_i - y_i) * x_i`. `Project` = exact projection onto `0.10 <= w_i <= 0.50`, `sum = 1.00`. One step per run; result is only a candidate.
- Gate: `Brier_val(candidate) <= Brier_val(active)` on the same 15 validation outcomes. No improvement margin required.
- Selection: 45 most recent eligible outcomes by verification time; newest 15 = validation, previous 30 = training, no overlap; both sets need at least one true and one false alarm, otherwise calibration is blocked.
- Initial version `v1` = S 0.30, T 0.20, V 0.35, H 0.15.
- Approval makes the version active for incidents that start afterwards. An incident already being tracked keeps its starting version. Every stored `C` records the version id.
- Rollback: Admin only, written reason, restores exact weights for later incidents, no version deleted, never automatic.

**Why this changed:**
- Section 8 was assigned to Zhen Jie. Because the weights sum to 1 and scores are in [0, 1], `C / 100 = w · x` is already in [0, 1], so a simple regression fits the source constraints.

**Source / decision reference:**
- Proposal sections 2, 4.4, 5.1; `SOURCE_TBD_REQUIREMENTS.md` (0.02 is the "batch gradient setting", so it is the learning rate); Zhen Jie decisions (in-flight incidents keep their version); Hong Jia Bao log entries for incident states and fusion channels.

**Validation performed:**
- None. Documentation only; no code, test or scenario was run.

**Requirement status after change:**
- `PARTIAL`. The policy is approved by Zhen Jie and the TBD item is resolved at policy level; implementation and validation are not done yet. No software behavior changed.

**Impact on teammates:**
- Once implemented: calibration service, weight-version table, `/admin` preview/approve/rollback, and a stored weight-version id on every `C`.
- Tests to add: projection keeps bounds and sum, gate blocks regression, train/validation split has no overlap.
- Depends on Hong Jia Bao's channel definitions (S, T, V, H) and incident states.

**Follow-up required:**
- Implement and validate. Check that the audit ledger stores all four channel scores per alert window. Confirm which state a rejected false alarm ends in.

## 2026-10-03 15:17 — Approved policy for Evidence Retention (TBD-PRIV-01 to 04)

**Changed by:** Zhen Jie
**Branch:** main
**Commit:** not committed yet
**Approved by:** Zhen Jie (section owner); no separate team sign-off requested

**Requirement / area:**
- TBD-PRIV-01 to TBD-PRIV-04 (Evidence Retention, `SOURCE_TBD_REQUIREMENTS.md` section 9)

**Files changed:**
- `evidence_retention.md` (new requirement file)

**Previous behavior / value:**
- `TBD_SOURCE` for retention duration, purge policy, storage backend and automatic frame selection. Already defined (per the TBD file): no permanent continuous video, at most 5 annotated frames per incident.

**New behavior / value (approved, not yet implemented):**
- Retention: 180 days counted from the incident start time (config value, change-control only).
- Automatic purge: scheduled job once per day deletes frame files older than the retention period. Manual purge: System Administrator only, with a written reason, may delete earlier.
- Purge deletes image files only; incident record, scores, detections and frame metadata (including a SHA-256 hash) stay in the append-only history. Every purge appends an audit event (who, when, how many, reason).
- Storage: local folder on the host, paths in SQLite, served only through the authenticated API. Encryption at rest and off-site backup are out of scope for the prototype.
- Frame selection stays explicit; automatic selection is out of scope until deterministic criteria are approved.

**Why this changed:**
- Section 9 was assigned to Zhen Jie. 180 days was chosen for auditability and to match the Area Risk window.

**Source / decision reference:**
- `SOURCE_TBD_REQUIREMENTS.md` section 9; proposal scope statement (prototype, not a certified life-safety product); Zhen Jie decision (180 days).

**Validation performed:**
- None. Documentation only.

**Requirement status after change:**
- `PARTIAL`. The policy is approved by Zhen Jie and the TBD item is resolved at policy level; implementation and validation are not done yet. No software behavior changed.

**Impact on teammates:**
- Once implemented: purge job, Admin purge action with audit event, frame metadata table with hash.

**Follow-up required:**
- Find where the "5 annotated frames" rule is written (it is in the TBD file, but I could not find it in the proposal text).

## 2026-10-03 15:17 — Approved policy for Admin / Operational Configuration (TBD-ADMIN-01)

**Changed by:** Zhen Jie
**Branch:** main
**Commit:** not committed yet
**Approved by:** Zhen Jie (section owner); no separate team sign-off requested

**Requirement / area:**
- TBD-ADMIN-01 (Editable operational settings, `SOURCE_TBD_REQUIREMENTS.md` section 10)

**Files changed:**
- `admin_configuration.md` (new requirement file)

**Previous behavior / value:**
- `TBD_SOURCE`. The proposal defines Admin calibration governance and an Admin account for "User RBAC, system health, and freshness calibration", but no general settings editor.

**New behavior / value (approved, not yet implemented):**
- Admin can edit in the UI: calibration approve/rollback, user roles, and sensor freshness timeouts inside these ranges (server enforces them, reason required, audited, applies from the next window, reset-to-default available):
  - MQ-2: 1.5 s to 3.0 s (default 2.0 s)
  - DHT22: 2.5 s to 4.0 s (default 3.0 s)
  - Camera: 0.5 s to 1.0 s (default 1.0 s; can only be tightened)
- Admin cannot edit in the UI (change only through change-control): fusion thresholds, severity thresholds/weights, routing weights, ACK timeout, risk thresholds, `N_min`, retention duration, sensor alarm thresholds, MQTT settings, model paths. Fusion weights change only through calibration.

**Why this changed:**
- Section 10 was assigned to Zhen Jie. Safety-critical values should not be edited at runtime without review. The freshness ranges are engineering judgment, not source values.

**Source / decision reference:**
- Proposal section 7 (Admin account description) and section 4.3 (freshness timeouts); Zhen Jie decision (timeouts editable). SN1 hardware log entries show roughly one MQ-2 and one DHT22 message per second, which supports the lower limits.

**Validation performed:**
- None. Documentation only.

**Requirement status after change:**
- `PARTIAL`. The policy is approved by Zhen Jie and the TBD item is resolved at policy level; implementation and validation are not done yet. No software behavior changed.

**Impact on teammates:**
- Once implemented: `/admin` freshness form, server-side range check, audit event for each change. Hardware team: confirm the real DHT22 reading interval, because the 2.5 s lower limit assumes about 2 s.

**Follow-up required:**
- Hardware team to confirm DHT22 timing. Implement the freshness form and the server-side range check.

## 2026-10-03 15:17 — Approved policy for Deployment and Reliability (TBD-OPS-01 to 03)

**Changed by:** Zhen Jie
**Branch:** main
**Commit:** not committed yet
**Approved by:** Zhen Jie (section owner); no separate team sign-off requested

**Requirement / area:**
- TBD-OPS-01 to TBD-OPS-03 (Production Deployment / Reliability, `SOURCE_TBD_REQUIREMENTS.md` section 11)

**Files changed:**
- `deployment_reliability.md` (new requirement file)

**Previous behavior / value:**
- `TBD_SOURCE` for topology/load, acceptance criteria and availability/recovery policy.

**New behavior / value (approved, not yet implemented):**
- Topology: one host workstation, Mosquitto on `localhost:1883`, backend on `127.0.0.1:8010`, dashboard on port 5173, SN1, AC1, one overhead camera, SQLite. Design target 4 simultaneous dashboard sessions (one per role); graph size depends on TBD-ROUTE-07.
- Event rates from the proposal: IR every 200 ms, detection at 5 FPS or more, segmentation at 2 FPS or more, fusion in 1-second windows.
- Acceptance uses only the proposal targets: routes under 1 s, dashboard update under 1 s, ACK success 95% over 20 cycles, 85% verification correctness over at least 40 scenarios, false-dispatch 10% or lower, button alert under 1 s. Scaling beyond the tabletop is out of scope.
- No uptime target. SQLite survives restart; unfinished incidents reload and are shown to the operator for review; old commands are not re-sent.
- When the backend is lost, AC1 goes to the existing safe default: traffic ALL_RED, gate CLOSE, buzzer ON. Detection: backend MQTT Last Will message, plus a 3-second AC1 heartbeat watchdog (backend heartbeat every 1 s; the 3 s value is an engineering choice to be tested on hardware). AC1 leaves fail-safe only on a valid command with a higher version number.
- Backup is manual: copy the SQLite file and the evidence folder before demos.

**Why this changed:**
- Section 11 was assigned to Zhen Jie. Inventing new load numbers would be fake values, so the proposal's own targets are used.

**Source / decision reference:**
- Proposal sections 2.3, 4.3, 5.1 and the setup/run steps; Zhen Jie decision (actuators go to fail-safe when the backend is lost); existing `FAILSAFE` safe default in Hong Jia Bao's log entry 2026-10-02 22:45.

**Validation performed:**
- None. Documentation only. No firmware or backend change was made.

**Requirement status after change:**
- `PARTIAL`. The policy is approved by Zhen Jie and the TBD item is resolved at policy level; implementation and validation are not done yet. No software behavior changed.

**Impact on teammates:**
- Once implemented: backend must publish a 1 s heartbeat and register an MQTT Last Will; AC1 firmware needs a heartbeat/offline watchdog (to my knowledge not implemented yet, please verify); both need a hardware test.

**Follow-up required:**
- Hardware/firmware owners to confirm the 3 s heartbeat value. Provide the final graph size (TBD-ROUTE-07). Implement and test on hardware.

## 2026-10-03 16:15 — Finalize Fire Fusion Master Specification

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- FUSION-01 to FUSION-07 (Fire Fusion Module)

**Files changed:**
- `fire_fusion.md`

**Previous behavior / value:**
- The document contained unresolved questions and mixed proposals (Zhenjie's drafts vs. Jiabao's ideas).
- Lacked strict hardware constraints (warm-up times, wiring) and lacked a clear resolution for the race condition between automatic and manual confirmations.

**New behavior / value:**
- Consolidated into a clean master specification following team decisions exclusively.
- Finalized sensor baselines (MQ-2: 500/2000, DHT22: 30°C/50°C) and stale limits (MQ-2: 2.0s, DHT22: 3.0s, Camera: 1.0s).
- Added the "Lock Rule": if the automatic gate passes before the Operator confirms, the system's automated confirmation takes precedence and ignores the manual confirm.
- Enforced hardware rules: DHT22 values are held across 1s windows, MQ-2 requires a 60s warm-up, and MQ-2 must be wired to an ESP32 ADC1 pin with a voltage divider

**Why this changed:**
- team decision / logic compilation. The file was rewritten to serve as a finalized, developer-ready master specification by removing outdated discussions and integrating the Hidden Conflicts Review solutions.

**Source / decision reference:**
- Team decisions and "Hidden Conflicts Review".

**Validation performed:**
- Logic review for state machine race conditions and hardware limitations.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend developers must implement the lock rule for the `ALERT` to `CONFIRMED` state transition.
- Hardware team must ensure ESP32 ADC1 wiring and calibrate the MQ-2 sensor only after the 60s warm-up.

**Follow-up required:**
- Hardware team to physically measure and confirm if 60s is sufficient for the MQ-2 warm-up.

## 2026-10-03 16:27 — Finalize Severity Definitions and Floor Rule 
 
**Changed by:** Hong Jia Bao 
**Branch:** main 
**Commit:** not committed yet 
 
**Requirement / area:** 
- TBD-SEV-01 to TBD-SEV-06 (Severity Module)
 
**Files changed:** 
- `severity.md`
 
**Previous behavior / value:** 
- Variables `A` and `Z` were undefined in the proposal.
- Confusion existed on whether severity `S` and `T` reused the Fusion module's scores.
- Hazard zone geometry and person (`P`) trigger frames were missing.
- Numeric bands for severity levels were undefined, and system behavior was unclear when `R` could not be calculated.
 
**New behavior / value:** 
- Defined `A` (fire bounding box area / hazard zone polygon area) and `Z` (Zone Vulnerability Score from config).
- Renamed variables to `S_smoke` (pure MQ-2 score) and `T_heat` (pure DHT22 score) to separate them completely from Fusion logic.
- Defined `P = 1` trigger: box center inside the polygon, confidence ≥ 0.50, requiring only **1 frame** to escalate to Critical.
- Established severity bands (Low 0-29, Medium 30-49, High 50-69, Critical 70-80).
- Added the "Floor Rule": If `R` is unavailable, the Operator chooses the severity. When `R` recovers, the system automatically uses the higher severity (Operator's choice acts as a floor).
 
**Why this changed:** 
- team decision / logic compilation. Variables had to be defined for backend implementation, and the missing data behavior needed strict rules to prevent manual dispatch errors.
 
**Source / decision reference:** 
- Team decisions and "Hidden Conflicts Review".
 
**Validation performed:** 
- Logic review for missing variables and edge cases (e.g., missing R score, false-dispatch rate mitigation).
 
**Requirement status after change:** 
- PASS
 
**Impact on teammates:** 
- Backend developers must implement the "Floor Rule" and calculate pure sensor values separately from Fusion.
- Hardware team must physically measure and map the hazard polygon coordinates in the sandbox.
 
**Follow-up required:** 
- Physically measure the polygon pixels in the sandbox.
- Add specific test scenarios to check the false-dispatch rate for the 1-frame `P = 1` rule (goal ≤ 10%).