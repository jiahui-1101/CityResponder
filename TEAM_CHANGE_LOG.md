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

## 2026-10-03 — Detection pilot dataset integrity cleanup and QA

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Integrity cleanup:**
- Removed the one orphan metadata row for `raw/person/person_session_001_0049_20261003T145644Z.jpg`; the image was absent on disk and was not recreated or fabricated.
- Audit record preserved at `datasets/cityresponder_detection_pilot/metadata/orphan_metadata_audit.md`.
- Active metadata now has 272 rows for 272 image files; every row maps to exactly one existing file and every file has exactly one active row.

**Validation:**
- All 272 images are readable, non-empty, and `1080×840`; class folders and session filename prefixes match metadata.
- Exact SHA-256 duplicate groups: 0.
- Consecutive within-session dHash review (distance ≤8) produced 260 near-duplicate candidate pairs: fire 44, smoke 47, person 61, negative 108. Nothing was deleted automatically; all are marked `REVIEW`.
- Duplicate review CSV: `reports/validation/vision/detection_pilot_duplicate_review.csv`.
- Human-QA contact sheets: `reports/validation/vision/detection_pilot_qa/`; summary: `reports/validation/vision/detection_pilot_qa/dataset_integrity_summary.json`.

**Distribution and split boundary:**
- Fire: 50 images, 1 real session; smoke: 50 images, 1 real session; person: 62 images, 1 real session; negative: 110 images, 2 real sessions; total 272.
- Session-aware train/validation/test splitting is **NOT READY**. No synthetic sessions or splits were created.
- Minimum additional real capture recommended: fire 2 sessions × 8–12 varied images; smoke 2 × 8–12; person 2 × 8–12; negative 1 × 8–12.
- YOLO training, annotation, auto-labeling, firmware/backend changes, crop/ROI changes, and commit/push were not performed.

## 2026-10-04 — Added session-aware detection pilot captures

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Capture scope:**
- Added exactly 70 real webcam crops using the locked camera index `1`, native `1920×1080` capture, and locked `1080×840` crop `(340,80,1080,840)`.
- Added sessions: `fire_session_002` (10), `fire_session_003` (10), `smoke_session_002` (10), `smoke_session_003` (10), `person_session_002` (10), `person_session_003` (10), and `negative_session_003` (10).
- Existing images were not deleted, renamed, or modified. One early smoke session-003 image was preserved and the remaining session count was completed explicitly.
- Capture runs reported zero failed reads and zero corrupt-frame rejections; near-duplicate warnings were retained as metadata and did not cause automatic deletion.

**Final integrity verification:**
- 342 readable image files and 342 active metadata rows; no orphan references, untracked images, filename collisions, class-folder/session-prefix mismatches, or dimension mismatches.
- All images are `1080×840`; exact SHA-256 duplicate groups: 0.
- Final distribution: fire 70/3 sessions, smoke 70/3, person 82/3, negative 120/3.

**Boundary:**
- Session-aware split is now structurally ready for review, but no train/validation/test split was created.
- Annotation, auto-labeling, YOLO training, firmware/backend changes, camera/crop changes, and commit/push were not performed.

## 2026-10-04 — Final human-QA preparation for detection pilot

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Rebuilt non-destructive contact sheets for all 342 images, organized by class, session, and filename order under `reports/validation/vision/detection_pilot_qa_final/`.
- Generated `qa_flags.csv` with Laplacian blur metric, grayscale brightness metric, consecutive within-session dHash near-duplicate flags, and `KEEP`/`REVIEW` recommendations. No image was deleted.
- Near-duplicate review uses dHash Hamming distance `<=8` for consecutive frames: 321 candidate pairs involving 339 candidate images. Two images fell below the conservative blur metric threshold; no extreme brightness flags were found.
- Automated semantic class consistency was deliberately left `UNVERIFIED_HUMAN_REVIEW`; no model-based class claim was made. All 342 rows are therefore recommended for human review.
- Created `datasets/cityresponder_detection_pilot/metadata/human_qa_manifest.csv` with one `PENDING` row per image and blank QA reason.
- No annotation, train/validation/test split, YOLO training, firmware/backend change, or commit/push was performed.

## 2026-10-04 — Interactive human QA reviewer launched

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Added `backend/scripts/review_detection_pilot.py`, a local OpenCV reviewer for the 342-image pilot dataset.
- Review order is FIRE → SMOKE → PERSON → NEGATIVE, grouped by session and capture order.
- KEEP and reason-required REJECT decisions update `datasets/cityresponder_detection_pilot/metadata/human_qa_manifest.csv` atomically after each decision; source images are never moved or deleted.
- Automated flags, blur/brightness metrics, near-duplicate warnings, and class-specific human review guidance are shown per image. No semantic class is pre-approved.
- Reviewer launched locally; QA remains pending until explicit human decisions are made. No annotation, split, training, or commit/push was performed.

## 2026-10-04 — YOLO manual annotation workspace launched

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Added `backend/scripts/annotate_detection_pilot.py` for manual bounding-box annotation of QA-approved images only.
- Created `datasets/cityresponder_detection_pilot/annotations/annotation_manifest.csv` and `annotations/labels/`.
- Current QA-approved set: 208 positive images pending annotation and 117 negative images marked `NEGATIVE_CONFIRMED` with empty label files; 17 QA-REJECT images are excluded.
- YOLO class map is fixed at `0=fire`, `1=smoke`, `2=person`; no negative class is created.
- Annotation UI launched locally and is waiting on the first positive FIRE image. Source images are not modified, moved, or deleted.
- No train/validation/test split, YOLO training, or commit/push was performed.

## 2026-10-03 — Detection pilot capture workflow completed

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Pilot scope:**
- Detection-only classes: `fire`, `smoke`, `person`, and `negative`.
- Reusable capture script: `backend/scripts/capture_detection_pilot.py`.
- Dataset root: `datasets/cityresponder_detection_pilot/` with per-class raw directories and `metadata/captures.csv`.
- Every saved image uses the locked native `1920×1080` frame and 1:1 `1080×840` crop `(340,80,1080,840)`; no upsampling, auto-labeling, or training is performed.
- Session IDs, timestamps, source settings, SHA-256 hashes, and near-duplicate warnings are recorded per image.

**Boundary:**
- Pilot engineering targets are not acceptance requirements.
- Camera/crop/ROI configuration remains locked. No firmware, backend, hardware, or production logic changed.

**Capture result:**
- Current metadata totals: fire 50 (1 session), smoke 50 (1 session), person 63 (1 session), negative 110 (2 sessions); 273 metadata rows total.
- Current image files: 272 readable `1080×840` crops. One metadata row references the missing file `raw/person/person_session_001_0049_20261003T145644Z.jpg`; no untracked image files were found.
- No duplicate SHA-256 hash groups were found in the current metadata; capture runs reported no failed reads or corrupt frames. The missing referenced file remains an evidence-integrity issue and must be resolved or explicitly excluded before annotation.
- Camera remained fixed; no upsampling, auto-labeling, or training was performed. Human dataset review is required before annotation or training.

**Follow-up required:**
- Resolve the one missing person image reference (or exclude its metadata row with an auditable correction), then perform human dataset review before annotation or training.

## 2026-10-03 — Webcam calibration locked after visual confirmation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Locked configuration:**
- Physical camera position: LOCKED.
- Native RAW_CAMERA resolution: `1920×1080`.
- RAW_BOARD_CROP: `x=340, y=80, width=1080, height=840`.
- Building A ROI in RAW_BOARD_CROP: `x=460, y=350, width=340, height=360`; source requirement `>=300×180`: PASS.
- Road ROI in RAW_BOARD_CROP: `x=10, y=675, width=1035, height=145`.
- Calibrated working frame: `1536×1195`, scale factor `1.4222×`.

**Requirement boundary:**
- Board source crop `1080×840` versus required `>=1536×1017`: FAIL; this source-resolution limitation is accepted and remains explicit.
- The calibrated resize is processing-only and does not add raw source detail.
- All older webcam framing/crop/ROI evidence remains historical/superseded; no dataset was captured using superseded coordinates.
- No firmware, backend, crop, ROI, or camera-position changes are permitted without a new explicit decision.

**Evidence:**
- Raw crop: `reports/validation/vision/webcam_board_raw_crop_final_20261003.jpg`.
- Calibrated working frame: `reports/validation/vision/webcam_board_calibrated_final_20261003.jpg`.
- Inspection: `reports/validation/vision/webcam_roi_inspection_final_20261003.jpg`.
- The inspection filename was already correct; no rename was required.

**Follow-up required:**
- Ready for pilot dataset capture; do not begin training until dataset/annotation instructions are provided.

## 2026-10-03 — Final raw webcam reference accepted

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Verified state:**
- User manually repositioned and accepted the webcam position as the intended final fixed position.
- Board-facing webcam: OpenCV index `1`; requested and actual resolution `1920×1080`.
- After exposure settling, one uncropped native reference was captured: `reports/validation/vision/webcam_reference_final_20261003_142219Z.jpg`.
- Capture statistics: 72 valid frames, 0 failed reads, approximately 23.870 FPS over 3.016 seconds.
- The raw frame visibly contains the complete model board, Building A, Fire Station, routing roads, IR-A/IR-B areas, TL1/TL2, servo gate, MQ-2 area, and DHT22 area without an obvious framing cut-off.

**Boundary:**
- This is raw reference evidence only. No crop, ROI coordinates, resize, dataset capture, annotation, or YOLO training was performed.
- Previous crop/ROI calibration remains superseded.

**Follow-up required:**
- Perform crop/ROI definition only after explicit user instruction.

## 2026-10-03 — Webcam calibration restarted; framing adjustment required

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Verified state:**
- The webcam was physically repositioned again. All previous webcam reference frames, crops, ROI coordinates, and calibrated-frame measurements are superseded and were not reused.
- Camera discovery found valid OpenCV indexes 0 and 1. Index 0 is room-facing; index 1 is the board-facing USB webcam and was selected.
- Index 1 returned real `1280×720` and `1920×1080` frames. A `2560×1440` request fell back to actual `1920×1080` and was not counted as a higher native mode.
- Current-position mode probes: `1280×720` returned 73 valid frames, 0 failed reads, approximately 24.284 FPS; `1920×1080` returned 74 valid frames, 0 failed reads, approximately 24.379 FPS; `2560×1440` returned actual `1920×1080`, 74 valid frames, 0 failed reads, approximately 24.343 FPS.
- New raw reference: `reports/validation/vision/webcam_reference_final_20261003T141115Z.jpg` (`1920×1080`, 134 valid frames, 0 failed reads, approximately 26.641 FPS over 5.030 seconds).
- The current raw frame cuts off the upper portion of the intended model/road area, so full required model coverage is not established.

**Decision:**
- `FRAMING_ADJUSTMENT_REQUIRED`.
- No raw board crop or calibrated board frame was generated for this attempt; no ROI coordinates or source-resolution compliance claim was made.
- No dataset was captured using any superseded framing. MQ-2, SN1, AC1, backend logic, and production firmware were not changed.

**Follow-up required:**
- Reposition or re-aim the webcam to include the complete model boundary and all required routes/components, then begin a new reference capture.

## 2026-10-03 — Webcam final-position calibration restarted

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Verified state:**
- The USB webcam was physically repositioned; all previous webcam reference frames, crops, ROI coordinates, and calibrated measurements are superseded and were not reused for this calibration.
- Camera discovery found valid OpenCV indexes 0 and 1. Index 0 is the room-facing camera; index 1 is the board-facing USB webcam and was selected.
- Index 1 returned real `1280×720` and `1920×1080` frames. A `2560×1440` request fell back to actual `1920×1080` and was not counted as a higher native mode.
- At `1920×1080`, the mode produced 74 valid frames in 3.006 seconds, 0 failed reads, approximately 24.619 FPS during the probe.
- New raw reference: `reports/validation/vision/webcam_reference_final_20261003T140459Z.jpg` (`1920×1080`, 134 valid frames, 0 failed reads, approximately 26.714 FPS over 5.016 seconds).
- Full visible model coverage was checked before cropping; required roads/buildings, visible traffic-light areas, servo/gate area, and the model boundary remain in frame. No dataset was captured using superseded framing.
- New raw crop, independently selected from the current frame: `(x=300, y=160, width=1200, height=880)`.
- New calibrated board frame: `reports/validation/vision/webcam_board_calibrated_final_20261003T140617Z.jpg`, `1536×1126`, aspect-preserving resize factor `1.28×`.

**Boundary:**
- Raw-camera and calibrated-frame coordinate systems remain separate. Digital resizing is not counted as additional raw spatial detail.
- Building A and road ROI coordinates remain pending explicit user confirmation; no ROI compliance claim was made.
- Source targets remain explicit: corrected/source board `>=1536×1017` and Building A source ROI `>=300×180`.

**Follow-up required:**
- User must inspect the new calibrated frame and confirm ROIs using the exact requested format before any stability test or dataset capture.

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

## 2026-10-03 — Webcam bring-up and fixed software board framing

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Real camera evidence:**
- Windows exposed two camera devices, including `USB2.0 HD UVC WebCam`; OpenCV index 1 was visually identified as the board-facing USB webcam. Index 0 showed the laptop-facing view.
- Index 1 opened at 1280×720 and produced 1,758 valid frames across three 20-second stability samples (~60 seconds total), with 0 failed reads and measured rates of 29.19–29.31 FPS.
- OpenCV/MSMF and DirectShow both reported `CAP_PROP_ZOOM=-1`; no usable UVC zoom control was exposed. Focus/autofocus controls were not changed.

**Fixed software framing evidence:**
- User confirmed the fixed board crop preserves 100% of the intended tabletop model.
- RAW_CAMERA crop: `(x=240, y=5, width=710, height=680)` from the 1280×720 frame.
- CALIBRATED_BOARD_FRAME: 1280×1226, approximately 1.803× resize in each axis. This is digital resizing only and does not add raw spatial detail.
- User-selected calibrated ROIs: Building A `(x=535, y=440, width=350, height=325)`; road `(x=330, y=810, width=850, height=120)`.
- Equivalent raw-camera measurements: Building A ≈194.1×180.3 px; road width ≈471.5 px. Building A therefore passes the 280×180 target only in the calibrated frame, not in raw-camera pixels; road width passes in both.
- Repository requirements say “real view”/pixel sizes but do not define raw versus calibrated coordinates, and the audit records exact ROI coordinates as TBD. No requirement PASS was claimed.

**MQ-2 boundary:**
- The previously verified `MQ2_MODULE_AO_OUTPUT_FAULT_SUSPECTED` remains unresolved; no MQ-2 firmware, thresholds, wiring, or calibration was changed during webcam work.

## 2026-10-03 — Fixed-camera native-resolution verification

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Real mode observations (USB webcam index 1, physical camera unchanged):**
- 1280×720 requested and returned; 28.267 FPS measured; 0 failed reads.
- 1920×1080 requested and returned; 28.444 FPS measured; 0 failed reads.
- 2560×1440 requested but the driver returned 1920×1080; it is not a distinct higher native mode (28.417 FPS, 0 failed reads).
- Selected native source mode: 1920×1080, the highest actual stable mode observed.

**Fixed-framing raw-coordinate mapping:**
- The prior 1280×720 board crop `(240,5,710,680)` maps to approximately `(360,8,1065,1020)` at 1920×1080.
- Building A maps to approximately `291.2×270.4` raw pixels; road width maps to approximately `707.2` raw pixels.
- The stated source targets `1536×1017` board source and `300×180` Building A source are not both met by the native board crop/ROI. Software upsampling is not counted as raw detail.

**Requirement boundary:**
- The repository’s current external requirements do not contain the stated 1536×1017/300×180 source wording; the audit records exact ROI coordinates as TBD. No compliance PASS was claimed. Dataset/model work may proceed only with this source-resolution limitation recorded.

## 2026-10-03 — Webcam moved; prior framing superseded

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Verified state:**
- The physical USB webcam moved after the previous calibration. The prior reference, crop, and ROI measurements remain preserved as historical evidence but are superseded and were not reused for dataset capture.
- New native reference captured from OpenCV index 1 at `1920×1080`: `reports/validation/vision/webcam_reference_20261003T091412Z.jpg`.
- The new reference stream produced 92 valid frames, 0 failed reads, and approximately 30.21 FPS during the capture window.
- The tabletop model roads, buildings, fire-station area, gate/model region, and board boundary appear visible in the new frame. External left-side wiring/breadboard background is outside the model crop; final ROI acceptance remains pending user confirmation.

**New independently selected framing:**
- RAW_CAMERA crop: `(x=330, y=25, width=1020, height=1015)`.
- CALIBRATED_BOARD_FRAME: `1280×1274`, resize factor approximately `1.255×` per axis.
- New calibrated frame: `reports/validation/vision/webcam_board_calibrated_20261003T091412Z.jpg`.

**Dataset boundary:**
- No dataset was captured using the superseded framing. No YOLO annotation or training was started.

## 2026-10-03 — Replacement MQ-2 analog-path validation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Verified SN1 hardware:**
- Replacement module labels were confirmed left-to-right as `VCC, GND, DO, AO`; DO remained unused.
- Replacement VCC/GND/AO were connected without changing the independently verified 20k upper / 10k lower divider or GPIO34 midpoint.
- Module status LED was ON, heater/sensor area was warm, and no abnormal heating, smell, or smoke was observed.
- Existing `firmware/sn1_bringup` built successfully and uploaded to CP210x `COM5` with flash verification.

**Raw observation:**
- 65.31 seconds; 65 usable samples; first `581`; last `486`; min `447`; max `621`; mean `534.585`; median `536`.
- All 65 samples were nonzero; no ADC saturation near 4095.
- DHT22 was valid for 65/65 reads. IR1 and IR2 were readable HIGH for all captured lines; button was readable HIGH for all captured lines. No reset loop, brownout, watchdog, or crash was observed; one startup reset line was present at the beginning of the serial buffer after upload.

**Diagnosis:**
- `NEW_MQ2_ANALOG_PATH_PASS` — the replacement module restored a clearly nonzero analog path, strongly supporting the prior `MQ2_MODULE_AO_OUTPUT_FAULT_SUSPECTED` diagnosis for the old module.
- No smoke/fire/gas stimulus was used. No thresholds or production files were changed. Ambient warm-up/baseline characterization remains a separate next step.

## 2026-10-03 — New MQ-2 pre-burn-in engineering baseline

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Observation boundary:**
- Replacement MQ-2 remained on the verified VCC/GND/AO wiring and 20k/10k divider in clean ventilated room air. No smoke, aerosol, gas, perfume, alcohol, flame, or other intentional stimulus was used.
- A temporary non-production 10 Hz raw-report interval was used to meet the engineering baseline sample target, then restored to the original 1 Hz source and re-uploaded to COM5. GPIO assignments, thresholds, and production firmware behavior were not changed.

**Ten-minute warm-up:**
- Duration `660.07 s` total capture (first 600 s used for warm-up), `5,999` warm-up samples; first/last raw values were not retained by the aggregate recorder, but the series ranged `126–366`, mean `243.286`, median `236`, standard deviation `40.569`, overall CV `16.675%`.
- Per-minute averages: `316.229, 295.233, 275.718, 254.260, 239.083, 229.113, 219.133, 207.448, 202.663, 194.103`.

**Final 60-second clean-air window:**
- `601` samples; min `131`; max `242`; mean `186.101`; median `186`; standard deviation `11.049`; CV `5.937%`.
- Final 30-second window: `300` samples; min `131`; max `237`; mean `183.150`; median `183`; standard deviation `9.466`; CV `5.169%`.

**Classification:**
- `PRE_BURN_IN_BASELINE_STILL_DRIFTING` — minute averages continued downward and final 30-second CV exceeded 5%.
- Formal 24-hour burn-in remains outstanding. No formal calibration PASS or production threshold was claimed.
- DHT22 was valid for all `6,600` runtime lines; IR1, IR2, and button remained readable; no brownout, reset loop, watchdog, or crash was observed.

## 2026-10-03 — Corrected pre-burn-in baseline repeat with first/last values

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

The preceding aggregate run did not retain first/last values. A repeat capture was performed with the same clean-air, pre-burn-in method and is the authoritative result below.

**Ten-minute warm-up:**
- Duration `660.16 s` total capture (first 600 s used for warm-up), `6,000` samples; first `164`; last `128`; min `64`; max `208`; mean `142.113`; median `142`; standard deviation `15.321`; CV `10.781%`.
- Per-minute averages: `159.769, 158.469, 154.132, 147.802, 141.732, 139.072, 135.717, 128.523, 127.793, 128.118`.

**Final 60-second clean-air window:**
- `601` samples; first `125`; last `120`; min `54`; max `181`; mean `120.799`; median `122`; standard deviation `10.777`; CV `8.922%`.
- Final 30-second window: `300` samples; first `117`; last `120`; min `59`; max `176`; mean `121.960`; median `122`; standard deviation `10.067`; CV `8.255%`.

**Classification and health:**
- `PRE_BURN_IN_BASELINE_STILL_DRIFTING` — minute averages fell materially and final 30-second CV exceeded 5%.
- Temporary 10 Hz engineering output was restored to the original 1 Hz source and re-uploaded to COM5; no GPIO, threshold, or production behavior changed.
- DHT22 valid `6,601/6,601`; IR1, IR2, and button remained readable; no health-fault lines or uptime backsteps were observed.
- Formal 24-hour burn-in remains outstanding; no formal calibration PASS or production threshold was claimed.

## 2026-10-04 — YOLOv8n detection v1 training and evaluation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Annotation and split gates:**
- Human-QA annotation workspace completed and validated: `325` active images; `208` positive images annotated; `117` approved negatives have empty YOLO labels; invalid/missing labels `0`.
- Deterministic session-aware split `detection_split_v1`: train `229`, val `58`, test `38`; session leakage `0`; image leakage `0`.
- Mapping was session-based (`*_session_001` train, `*_session_002` val, `*_session_003` test). No production integration was changed.

**Training:**
- YOLOv8n pretrained model, `imgsz=640`, requested `epochs=50`, `patience=10`, `batch=8`, `workers=0`, `seed=42`, deterministic CPU execution.
- Early stopping completed `40` epochs; best checkpoint was epoch `30`.
- Best weights: `runs/detect/runs/detection_v1/weights/best.pt`; last weights: `runs/detect/runs/detection_v1/weights/last.pt`.
- Environment: Python `3.14.4`, Ultralytics `8.4.165`, Torch `2.14.0+cpu`, CUDA unavailable, device CPU.

**Best-checkpoint validation:**
- VAL overall: precision `0.859`, recall `0.900`, mAP50 `0.917`, mAP50-95 `0.408`.
- VAL per class (precision / recall / mAP50 / mAP50-95): fire `0.770 / 0.700 / 0.771 / 0.239`; smoke `0.870 / 1.000 / 0.986 / 0.421`; person `0.937 / 1.000 / 0.995 / 0.564`.
- TEST overall (held out session 003): precision `0.877`, recall `0.810`, mAP50 `0.839`, mAP50-95 `0.379`.
- TEST per class: fire `0.766 / 0.625 / 0.665 / 0.199`; smoke `0.956 / 0.818 / 0.865 / 0.388`; person `0.908 / 0.987 / 0.986 / 0.551`.
- Final validation/test plots and confusion matrices were generated under `runs/detect/runs/detection_v1`, `runs/detect/runs/detect/val_final`, and `runs/detect/runs/detect/test_final`.

**Real webcam benchmark:**
- Locked webcam index `1`, actual `1920×1080`, fixed crop `(340,80,1080,840)`, resized to `640×640` for inference. `100/100` valid frames, `0` failed reads, elapsed `8.856 s`.
- Average throughput including capture and inference: `11.29 FPS`; median inference latency `51.89 ms`; p95 `59.95 ms`. The measured stream exceeded the `>=5` inference/s target on this CPU run.
- Evidence: `reports/validation/vision/detection_v1_webcam_benchmark.json`.

**Bad-case candidates and limitations:**
- Automated TEST candidate report contains `9` rows (low-confidence candidates and fire/smoke missed/localization candidates); it is a human-review aid, not automatic rejection or retraining evidence: `reports/validation/vision/detection_v1_bad_cases.csv`.
- Representative annotated predictions are under `reports/validation/vision/detection_v1_predictions/`.
- Dataset remains small, class-balanced only at image level, uses controlled tabletop/miniature visual proxies, and has the documented camera source-resolution limitation. Metrics do not establish production readiness or real-world human/fire/smoke generalization.
- No second training pass, segmentation, firmware/backend changes, or production detection integration was started. No commit/push was performed.

## 2026-10-04 — YOLOv8n detection v2 fire audit (pre-capture)

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Reviewed all `61` QA-KEEP fire annotations across `fire_session_001`–`003`.
- `61` labels were unchanged; `0` objective annotation corrections were justified.
- Five fire cases require review attention because they are small, edge-adjacent, or low-confidence model cases; the boxes remain consistent with the visible fire target.
- Reviewed all `9` v1 bad-case candidates. The fire candidates include two true misses (small/edge targets), two low-confidence true positives, and one fire candidate that was not actually bad; smoke/person candidates remain unrelated to the fire label audit.
- Evidence: `reports/validation/vision/detection_v2_fire_annotation_audit.csv` and `reports/validation/vision/detection_v2_bad_case_review.csv`.
- The current camera frame contains no fire target, so no supplementary `fire_session_004` images were captured or fabricated. The audit indicates that a small hard-case fire supplement is warranted before the single v2 training pass; existing session_003 test data remains untouched.

## 2026-10-04 — YOLOv8n detection v2 final pass

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

**Fire supplement and annotation gate:**
- Captured `17` additional real images in `fire_session_004` using the locked webcam/crop. The user stopped the session after image 17; no further images were fabricated.
- Human QA: `17 KEEP`, `0 REJECT`; all `17` received one manually drawn fire box. Existing source images were preserved.
- Fire annotation audit covered all `61` pre-existing QA-KEEP fire labels: `0` objective corrections; `61` unchanged. Test-session labels were not modified.
- Evidence: `reports/validation/vision/detection_v2_fire_annotation_audit.csv`, `reports/validation/vision/detection_v2_bad_case_review.csv`, and `reports/validation/vision/detection_v2_fire_session_004_contact_sheet.jpg`.

**V2 split:**
- Session-aware split: train `246`, val `58`, test `38`; train contains fire sessions `001` and `004`, while val/session `002` and test/session `003` remain isolated.
- Image leakage `0`; session leakage `0`; split source count `342` with no split errors.
- The entire v1 held-out test image/label set is byte/hash-identical in v2; no test evidence was altered.
- Split manifest: `reports/validation/vision/detection_split_v2.json`.

**Training:**
- One clean YOLOv8n run from `yolov8n.pt`, `imgsz=640`, requested `epochs=60`, `patience=12`, `batch=8`, `workers=0`, `seed=42`, deterministic CPU execution.
- Early stopping completed `41` epochs; best checkpoint was epoch `29`.
- Best weights: `runs/detect/runs/cityresponder_detection_v2/train/weights/best.pt`; last weights: `runs/detect/runs/cityresponder_detection_v2/train/weights/last.pt`.
- Environment: Python `3.14.4`, Ultralytics `8.4.165`, Torch `2.14.0+cpu`, CPU only.

**Independent best-checkpoint evaluation:**
- VAL overall: precision `0.9645`, recall `0.9615`, mAP50 `0.9859`, mAP50-95 `0.4592`.
- TEST overall (held-out session 003): precision `0.9525`, recall `0.8488`, mAP50 `0.8970`, mAP50-95 `0.4102`.
- TEST per class (precision / recall / mAP50 / mAP50-95): fire `0.9380 / 0.7500 / 0.8360 / 0.3205`; smoke `0.9194 / 0.8182 / 0.8600 / 0.3773`; person `1.0000 / 0.9783 / 0.9950 / 0.5328`.
- Compared with v1 TEST fire (`0.766 / 0.625 / 0.665 / 0.199`), v2 deltas are `+0.172 / +0.125 / +0.171 / +0.121`.
- Smoke versus v1 (`0.956 / 0.818 / 0.865 / 0.388`) has a small precision/mAP decrease, with recall unchanged; person versus v1 (`0.908 / 0.987 / 0.986 / 0.551`) improves precision and mAP50 while mAP50-95 decreases slightly. No material regression was judged from this small held-out set.
- Metrics evidence: `reports/validation/vision/detection_v2_metrics.json`.

**Webcam benchmark:**
- Locked webcam index `1`, actual `1920×1080`, fixed crop `(340,80,1080,840)`, resized to `640×640`; `100/100` valid frames and `0` failed reads.
- Throughput including capture and inference: `17.56 FPS`; median inference latency `51.79 ms`; p95 `59.89 ms`; `>=5` inference/s target PASS.
- Evidence: `reports/validation/vision/detection_v2_webcam_benchmark.json`.

**Decision and limits:**
- Selected `DETECTION_CANDIDATE = V2` because fire TEST performance improved materially, smoke/person changes were not material regressions on the unchanged held-out test, and the webcam benchmark passed.
- Detection status: `FROZEN_PENDING_INTEGRATION`. No production detection integration was performed.
- Limitations remain: small controlled tabletop/miniature dataset, fire-only supplement of `17` images (below the 20–30 planning range because the user stopped capture), documented source-resolution limitation, CPU-only benchmark, and no claim of real-world generalization.
- Segmentation has not started. No firmware, backend, MQTT, hardware, or threshold changes were made. No commit/push was performed.

## 2026-10-04 — Segmentation pilot integrity and QA preparation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Verified `181` readable 1080×840 segmentation pilot images with `181` metadata rows. Corrupt images, orphan metadata, exact SHA-256 duplicates, dimension mismatches, metadata mismatches, and filename collisions were all `0`.
- Distribution: `road_obstacle=61`, `pothole=60`, `clear_road=60`. The extra road-obstacle image was retained; no automatic deletion was performed.
- Road-obstacle session IDs are not the intended contiguous `001/002/003` layout: session `001=1`, `002=10`, and sessions `014`–`018=10` each. Pothole and clear-road sessions are `001=40`, `002=10`, `003=10`. Session-aware splitting is therefore not yet ready.
- Recomputed adjacent perceptual similarity and created `165` near-duplicate candidates. These are review-only; exact duplicates remain `0` and no images were deleted.
- Created human-QA manifest at `datasets/cityresponder_segmentation_pilot/metadata/human_qa_manifest.csv`; all rows start `PENDING`.
- Created class/session contact sheets under `reports/validation/vision/segmentation_pilot_qa/` and integrity evidence at `reports/validation/vision/segmentation_pilot_integrity.json` plus `segmentation_pilot_duplicate_review.csv`.
- Created, but did not launch to completion, `backend/scripts/review_segmentation_pilot.py` and `backend/scripts/annotate_segmentation_pilot.py`. Polygon annotation and segmentation training have not started.
- Detection remains frozen; no firmware, backend, webcam, or production logic was changed. No split, training, commit, or push was performed.

## 2026-10-04 — Segmentation QA completion, provenance audit, and polygon preparation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Verified segmentation human QA is complete: road obstacle `61 KEEP / 0 REJECT`, pothole `59 KEEP / 1 REJECT`, clear road `60 KEEP / 0 REJECT`; total `180 KEEP`, `1 REJECT`, `0 PENDING`.
- Audited road-obstacle provenance without renaming historical sessions. Timestamp and visual variation support distinct capture blocks for sessions `002`, `014`, `015`, `016`, `017`, and `018`; session `001` remains a one-image retained provenance record.
- Provisional future grouping recommendation: `001/002/014/015` TRAIN, `016/017` VAL, `018` TEST. This is recorded as an audit recommendation only; no split was created.
- Evidence: `reports/validation/vision/road_obstacle_session_provenance_audit.csv`.
- Initialized `datasets/cityresponder_segmentation_pilot/annotations/annotation_manifest.csv`: road obstacle `61 PENDING`, pothole `59 PENDING`, clear road `60 NEGATIVE_CONFIRMED`.
- Created `60` empty YOLO-seg label files for QA-KEEP clear-road images. The manual polygon UI is running for positive images only.
- Polygon annotation and segmentation training have not started. Detection V2 remains frozen. No firmware/backend changes, split, commit, or push were performed.

## 2026-10-04 — YOLOv8n-seg v1 training and held-out validation

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Validated the completed polygon annotations before training: `209` valid polygons across `120` positive images, `60` clear-road empty labels, `0` invalid labels, and `0` missing labels. QA rejects were excluded.
- Created the session-aware split at `datasets/cityresponder_segmentation_pilot/yolo_segmentation_v1/`: train `111`, validation `39`, test `30`; road-obstacle/pothole/clear-road distributions are `31/40/40`, `20/9/10`, and `10/10/10`, respectively. Session leakage and image leakage are both `0`.
- Corrected the Windows Ultralytics dataset-root declaration in `data.yaml`; no source images or annotations changed.
- Ran one CPU `yolov8n-seg.pt` training job with `imgsz=640`, `epochs=60`, `patience=12`, `seed=42`, `batch=8`, and `workers=0`. Early stopping completed at epoch `30`; the best checkpoint was epoch `18` by the recorded segmentation fitness. Weights: `runs/segment/runs/cityresponder_segmentation_v1/train2/weights/best.pt` and `last.pt`.
- Best-checkpoint validation metrics: mask P/R/mAP50/mAP50-95 = `0.9856 / 0.9981 / 0.9950 / 0.6752`; box P/R/mAP50/mAP50-95 = `0.9856 / 0.9981 / 0.9950 / 0.7241`.
- Best-checkpoint test metrics: mask P/R/mAP50/mAP50-95 = `0.9872 / 1.0000 / 0.9950 / 0.6252`; box P/R/mAP50/mAP50-95 = `0.9872 / 1.0000 / 0.9950 / 0.6582`. Test mask mAP50-95 by class: road_obstacle `0.6827`, pothole `0.5677`.
- Held-out clear-road audit: `10/10` images with `0` false-positive instances. Evidence: `reports/validation/vision/segmentation_v1_clear_road_fp.csv`.
- Saved representative test predictions under `reports/validation/vision/segmentation_v1_predictions/rendered_final/`; bad-case report is `reports/validation/vision/segmentation_v1_bad_cases.csv` with `0` automatically identified cases.
- Webcam benchmark used camera index `1`, actual `1920x1080`, fixed crop `(340,80,1080,840)`, and `640x640` inference input: `100` valid frames, `0` failed reads, average end-to-end `9.40 FPS`, median inference `79.99 ms`, p95 `90.28 ms`. Evidence: `reports/validation/vision/segmentation_v1_webcam_benchmark.json`.
- Segmentation v1 remains a controlled tabletop pilot: no production integration, no firmware/backend changes, no automatic second training pass, and no commit/push. Detection V2 remains frozen.

## 2026-10-04 — Frozen Detection V2 and Segmentation V1 prototype integration

**Changed by:** Codex
**Branch:** `main`
**Commit:** not committed yet

- Integrated frozen Detection V2 weights at `runs/detect/runs/cityresponder_detection_v2/train/weights/best.pt` with exact classes `fire`, `smoke`, and `person`.
- Integrated frozen Segmentation V1 weights at `runs/segment/runs/cityresponder_segmentation_v1/train2/weights/best.pt` with exact classes `road_obstacle` and `pothole`.
- Added startup model-contract checks for weight existence, model task, and exact indexed class mapping; no fallback model is substituted.
- Locked the shared camera pipeline to index `1`, native `1920x1080`, RAW_CAMERA crop `(340,80,1080,840)`, Building A ROI `(460,350,340,360)`, and road ROI `(10,675,1035,145)` in RAW_BOARD_CROP coordinates.
- Added one shared-frame integration pipeline: capture once, crop once, run both frozen models, retain raw confidence/box/polygon evidence, and publish through the existing `city/vision/detection` and `city/vision/road` ingestion path. Fusion receives the resulting evidence through the existing perception snapshot; no vision code dispatches actuators.
- Replaced process-local numeric camera frame IDs with UUID-based source identifiers so evidence from separate runtime sessions cannot collide.
- Preserved the existing evidence policy: no continuous video storage and a hard maximum of five explicitly selected annotated frames per incident. The integration can render one selected audit frame in memory but does not auto-store it.
- Added runtime vision health reporting. Camera, model, inference, or malformed-output failures raise an integration error and mark vision unavailable; they are not converted into clean/safe evidence.
- Automated integration tests: `13 passed, 0 failed`. Covered model contracts/unavailable weights, locked crop, Building A and road geometry, structured outputs, empty results, camera/inference failures, evidence cap, no continuous video, and no direct actuator dispatch.
- Real MQTT smoke handoff: broker connected; one Detection V2 message and one Segmentation V1 road message were persisted with model identity and reached the existing fusion input path. The published frame contained no detection/road segmentation evidence and issued no actuator command.
- Real webcam smoke observations: normal/empty output occurred in `11/100` frames; no fire/person output was observed. The model emitted `134` pothole instances, but physical pothole ground truth was not independently confirmed, so no physical PASS is claimed for that scene.
- Combined steady-state benchmark after one untimed integrated warm-up: `100` valid frames, `0` failures, `8.05 FPS`, end-to-end median `122.69 ms`, p95 `134.01 ms`; detection mean `46.78 ms`, segmentation mean `62.22 ms`. Evidence: `reports/validation/vision/vision_integration_benchmark.json`.
- Regression checks passed: vision unit suite, fusion policy, severity policy, severity orchestration, dispatch policy, requirements/privacy/evidence validation, backend compilation, frontend typecheck, and frontend build.
- Existing unrelated response E2E validation remains failed in unchanged `backend/app/respond/service.py`: a function-local `DEFAULT_ACTUATOR_NODE_ID` import shadows the module import and causes `UnboundLocalError` on the no-safe-route branch. It was reported and not modified.
- Known limitations remain explicit: controlled tabletop datasets, no established real-world generalization, and native board crop `1080x840` below the `1536x1017` source target. MQ-2 formal calibration was not started. No commit/push was performed.

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
- logic compilation. The file was rewritten to serve as a finalized, developer-ready master specification by removing outdated discussions and integrating the Hidden Conflicts Review solutions.

**Source / decision reference:**
-  "Hidden Conflicts Review".

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
- logic compilation. Variables had to be defined for backend implementation, and the missing data behavior needed strict rules to prevent manual dispatch errors.
 
**Source / decision reference:** 
-  "Hidden Conflicts Review".
 
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

## 2026-10-03 16:51 — Finalize Dispatch Matrix and Failsafe Rules

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- TBD-DISPATCH-01 to TBD-DISPATCH-03 (Dispatch Module)

**Files changed:**
- `dispatch.md`

**Previous behavior / value:**
- The wording for Low/Medium dispatch was ambiguous ("vehicles are only dispatched in the background").
- The hardware failsafe triggered physical alarms for `NO_SAFE_ROUTE` regardless of the severity level.
- The 500ms hardware ACK timeout lacked a strict definition for retry attempts before triggering the failsafe.

**New behavior / value:**
- **Low/Medium Action Clarification:** Explicitly stated that "Responder units are assigned/displayed in the dashboard only; no physical sandbox action is triggered."
- **Severity-Based Failsafe:** Failsafe actions are now split. High/Critical triggers physical failsafe (ALL_RED, Gate CLOSE, Buzzer ON). Low/Medium triggers a dashboard warning only.
- **ACK Timeout Definition:** Defined that each hardware command has a 500 ms ACK timeout with exactly one retry allowed. If the retry fails, the failsafe triggers.
- **Resource & Escalation:** Finalized resource mapping per severity and confirmed the 1-frame `P = 1` Critical override rule.

**Why this changed:**
- UI consistency and hardware logic refinement. To prevent physical sandbox disruptions (alarms/traffic paralysis) during low-severity or unrouted incidents, and to finalize strict hardware communication constraints.

**Source / decision reference:**
- "Hidden Conflicts Review".

**Validation performed:**
- Logic review for hardware action matrices and `NO_SAFE_ROUTE` edge cases.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend developers must separate the `NO_SAFE_ROUTE` and hardware failure logic based on the incident's severity (dashboard warning vs. physical actions).
- Hardware team must implement the 500ms + 1 retry logic for actuator ACKs.

**Follow-up required:**
- Verify the overall false dispatch rate remains ≤ 10% during testing for the single-frame `P = 1` rule.

## 2026-10-03 17:08 — Finalize Routing Module Parameters and Calibration Logic

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- TBD-ROUTE-01 to TBD-ROUTE-08 (Routing Module)[cite: 11]

**Files changed:**
- `routing.md`

**Previous behavior / value:**
- Ambiguity existed regarding how segmentation masks converted into routing occupancy (`O` and `L`), and the meaning of `C_routing` was undefined[cite: 11].
- IR hardware rules (polarity, debounce, physical prop restrictions) were vague[cite: 11].
- The conflict resolution logic between the Camera and IR sensor lacked a grace period, specific state thresholds, and clear recovery mechanisms (auto/manual override expiry)[cite: 11].
- ETA calculations were included despite the prototype lacking a moving vehicle or speed model[cite: 11].

**New behavior / value:**
- **Variables Defined:** `O` uses a 3-frame median (1.5s)[cite: 11]. `L` is defined as obstacle length / road length (max 1.0)[cite: 11]. `C_routing` is assumed as pothole mask area (kept strictly separate from the obstacle mask)[cite: 11].
- **IR Hardware Strict Rules:** Debounce requires 5 consecutive blocked/clear samples[cite: 11]. Physical test props MUST be tall enough to be seen by the IR beam and fall inside the `O_ir` camera zone (no flat items like tape)[cite: 11].
- **Conflict Resolution (`SENSOR_CONFLICT`):** Defined Camera states (BLOCKED, CLEAR, MIDDLE)[cite: 11]. Added a 1.5s grace time when sensors disagree[cite: 11]. "MIDDLE + IR blocked" is explicitly handled as "passable, extra cost only" to utilize the cost formula[cite: 11].
- **Edge Recovery:** Implemented a 5-second hold-off for automatic recovery to prevent route flipping, and set a 60-second expiration for manual Operator "verified clear" overrides[cite: 11].
- **ETA Removed:** ETA metrics are completely removed from the UI/system and replaced with raw route length (cm) and route cost[cite: 11].

**Why this changed:**
- team decision / logic compilation. The routing cost formula and edge removal logic require absolute strictness to prevent `NO_SAFE_ROUTE` false positives and rapid traffic light flipping on the sandbox hardware.

**Source / decision reference:**
- "Hidden Conflicts Review".

**Validation performed:**
- Logic review of hardware polling rates, debounce logic, and edge mapping matrices (S0 to A1)[cite: 11].

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend developers must implement the 5s auto-recovery hold-off, 60s manual override expiry, and the 1.5s sensor conflict grace period[cite: 11].
- UI developers must remove ETA from all dashboards and replace it with route length (cm) and cost[cite: 11].
- Hardware team must measure and hardcode real-world coordinates for the mapping table (Distance, Road ROI, IR Zone)[cite: 11].

**Follow-up required:**
- Physically measure actual segmentation delays, IR polarities (HIGH/LOW), and the exact `O_ir` bounding zones on the sandbox[cite: 11].

## 2026-10-03 17:21 — Finalize Incident Feedback Lifecycle and State Model

**Changed by:** Hong Jia Bao
**Branch:** main
**Commit:** not committed yet

**Requirement / area:**
- TBD-INC-01 to TBD-INC-02 (Incident Feedback Lifecycle)

**Files changed:**
- `incident_feedback.md`

**Previous behavior / value:**
- Lack of clear distinction on how Operator `REJECT` and `CANCEL` actions affect subsequent model calibration labels and false dispatch statistics.
- No explicit database-level handling rules for race conditions when automatic confirmation and manual confirmation occur simultaneously.
- Missing recurring reminder mechanism for unattended `ALERT`s.
- `FAILSAFE` state actions were not strictly bound to severity levels (Low/Medium vs. High/Critical).

**New behavior / value:**
- Clarified the exact impact of `CONFIRM`/`REJECT`/`CANCEL` on calibration labels (1/0/not used) and risk scores.
- Introduced the "Lock rule" as a single database transaction: the first condition met (auto or manual) wins, and late confirms are ignored. Operator-chosen severity acts as an auto-upgradeable "floor".
- Defined that physical `FAILSAFE` responses (All-Red lights, Gate CLOSE, Buzzer ON) only trigger for High or Critical severities.
- Added the `ALERT_UNATTENDED` mechanism: alerts do not auto-close; after 30 seconds of inaction, the dashboard flashes a repeating reminder and logs it.

**Why this changed:**
- Team decision / logic compilation. To allow backend developers to build a strict incident state machine, completely resolve concurrent confirmation conflicts, and ensure perfectly clean dataset labels for future AI recalibration.

**Source / decision reference:**
- Proposal (Figure 7.2).

**Validation performed:**
- Logic review for state machine transition paths, specifically the race condition lock from ALERT to CONFIRMED.

**Requirement status after change:**
- PASS

**Impact on teammates:**
- Backend developers must implement the transition from `ALERT` to `CONFIRMED` as a strict single database transaction.
- Backend must implement the 30-second polling mechanism for `ALERT_UNATTENDED` reminders.

**Follow-up required:**
- Check the backend codebase's existing enums to ensure the state list exactly matches this document (ALERT, CONFIRMED, RESPONDING, ACTIVE, CONCLUDED, VERIFIED).
