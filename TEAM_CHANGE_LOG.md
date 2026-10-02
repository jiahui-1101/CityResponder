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

Future changes must not invalidate this baseline without updating validation evidence and this log.

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

## Change entries

<!-- Add newest entries above older entries. -->
