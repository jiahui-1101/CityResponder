# CityResponder: Area Risk Requirements (TBD section 7)
Owner: Zhen Jie
Covers: TBD-RISK-01 to TBD-RISK-09
Source basis: Proposal sections 4.4 and 5.1 (Learn phase, /risk page), SOURCE_TBD_REQUIREMENTS.md section 7, TEAM_TECHNICAL_REQUIREMENTS.md section 6

## Status tags
* **CONFIRMED**: decided with high confidence from TEAM_TECHNICAL_REQUIREMENTS.md baseline and proposal logic.
* **PARTIAL**: the definition is confirmed but a number or detail is still missing. (None remaining)
* **PENDING**: cannot be decided from the documents. Waiting for clarification. (None remaining)

## What the proposal and technical requirements fix
* Score = 100 * (0.30F + 0.25R + 0.20E + 0.15A + 0.10M)
* Uses confirmed/operator-verified incidents only, in a 180-day rolling window.
* It is a transparent, explainable weighted score, "not a black-box prediction".
* Repeated fires may display the cautious wording "possible electrical-risk hotspot; inspection recommended", never a definitive diagnosis.
* Full mathematical breakdown and component definitions:
  - F = Frequency of confirmed incidents in last 180 days: min(confirmed_incidents_in_last_180_days / 5, 1.0)
  - R = Recency exponential decay: exp(-days_since_latest_confirmed_incident / 60)
  - E = Verified electrical incident ratio: verified_electrical_incidents / confirmed_incidents_in_last_180_days
  - A = Repeated sensor anomalies (near-misses): min(repeated_sensor_anomaly_events_in_last_30_days / 5, 1.0)
  - M = Maintenance overdue/inspection status: 1.0 if overdue > 30 days, 0.5 if open <= 30 days, 0.0 if none due

## General rules for this section (CONFIRMED)
* RISK-G1: Every component F, R, E, A, M shall be a number in [0.0, 1.0].
* RISK-G2: Only incidents that the operator verified and marked as CONFIRMED count toward F, R, and E. REJECTED, FALSE_ALARM, and CANCELLED do not count toward fire incidents.
* RISK-G3: The 180-day window is rolling: an incident counts if its start timestamp (`created_at`) is within 180 days before the moment the score is calculated.
* RISK-G4: If a component cannot be calculated due to missing system data or uninitialized state, the score shall be `not_calculated` with a visible diagnostic reason. No silent zero.
* RISK-G5: The UI shall show the score as a transparent breakdown (individual F, R, E, A, M values and their weights) so the City Risk Planner can audit why an area is ranked at a given risk level.

---

## TBD-RISK-01: F definition and normalization
**Status**: CONFIRMED

**Requirement**
* `F` represents the frequency of confirmed incidents in the designated area within the 180-day rolling window.
* Formula: `F = min(confirmed_incidents_in_last_180_days / 5.0, 1.0)`.
* `F_cap` is fixed at `5.0`. An area experiencing 5 or more confirmed fires within 180 days achieves the maximum frequency risk score of `1.0`.

**Team answer**: `F_cap` is strictly fixed to **5** as established in Section 6.2 of `TEAM_TECHNICAL_REQUIREMENTS.md`. This captures repeatability within the 45-row historical dataset (15 cases per area) without letting a single extreme cluster permanently skew the 180-day window.

---

## TBD-RISK-02: R definition and normalization
**Status**: CONFIRMED

**Requirement**
* `R` represents **Recency** of the most recent confirmed incident in the area.
* Formula: `R = exp(-days_since_latest_confirmed_incident / 60.0)`.
* An incident occurring today produces `R = exp(0) = 1.00`. An incident 60 days ago produces `R = exp(-1) ≈ 0.368`. An incident at 180 days produces `R = exp(-3) ≈ 0.050`. If an area has no confirmed incidents in the 180-day window, `R = 0.0`.

**Team answer**: `R` stands for **Recency** using exponential decay with a **60-day half-life constant (`lambda = 1/60`)**, as defined in Section 6.2 of `TEAM_TECHNICAL_REQUIREMENTS.md`. This smooth continuous decay avoids artificial cliffs caused by step functions.

---

## TBD-RISK-03: E definition and normalization
**Status**: CONFIRMED

**Requirement**
* `E` represents the **Verified Electrical Ratio** among confirmed incidents in the 180-day window.
* Formula: `E = verified_electrical_incidents / confirmed_incidents_in_last_180_days`.
* If `confirmed_incidents_in_last_180_days == 0`, `E = 0.0`.
* The cause is sourced exclusively from the post-incident outcome feedback form submitted by the authorized operator/firefighter (feedback table `probable_cause == 'ELECTRICAL'`).

**Team answer**: `E` stands for **Verified Electrical Ratio**, matching Section 6.2 and 7.1 of `TEAM_TECHNICAL_REQUIREMENTS.md`. Feedback submitted at incident resolution stores `probable_cause`, allowing verified electrical incidents to be isolated and normalized directly against total confirmed incidents.

---

## TBD-RISK-04: A definition and normalization
**Status**: CONFIRMED

**Requirement**
* `A` represents **Repeated Sensor Anomalies** (near-misses / sub-threshold spikes) detected in the area within the last 30 days.
* Formula: `A = min(repeated_sensor_anomaly_events_in_last_30_days / 5.0, 1.0)`.
* An anomaly event is defined as a persistent environmental reading of Smoke `S >= 0.55` and Temperature `T >= 0.50` lasting at least 3 consecutive seconds without resulting in an operator-confirmed fire dispatch.
* 5 anomaly episodes within 30 days saturate `A` to `1.0`.

**Team answer**: `A` stands for **Repeated Sensor Anomaly Events**, fixed by Section 6.2 of `TEAM_TECHNICAL_REQUIREMENTS.md`. This captures early hardware/infrastructure warning signs (near-miss thermal/gas spikes) independently of full fire dispatches.

---

## TBD-RISK-05: M definition and normalization
**Status**: CONFIRMED

**Requirement**
* `M` represents **Maintenance Status** of the area/building derived from the municipal inspection queue.
* Piecewise schedule:
  - `M = 1.0`: Inspection overdue by more than 30 days.
  - `M = 0.5`: Inspection open / scheduled / pending for at most 30 days.
  - `M = 0.0`: Up to date; no inspection due.

**Team answer**: `M` stands for **Maintenance Status**, strictly mapped to the discrete regulatory schedule defined in Section 6.2 of `TEAM_TECHNICAL_REQUIREMENTS.md`.

---

## TBD-RISK-06: Area identity and mapping
**Status**: CONFIRMED

**Requirement**
* The city model has exactly three fixed areas:
  1. `Area A` / `B-A`: Live Fire Zone Building A (`x=92–116, y=70–88`), occupied commercial (`Z=0.80`).
  2. `Area B` / `B-B`: Building B (`x=48–72, y=40–58`), commercial/residential baseline.
  3. `Area C` / `B-C`: Building C (`x=4–28, y=72–86`), historical risk comparison zone.
* Incidents are assigned via detection coordinate inside the calibrated camera ROI polygon.
* For non-camera alerts (e.g., manual push button PB1 or pure sensor anomalies), the incident record is statically mapped to the physical zone containing the sensor/button hardware (Button PB1 at `(90,75)` maps to `Area A`).

**Team answer**: The model implements three areas: **Area A**, **Area B**, and **Area C** as defined in Section 8.2 and 8.3 of `TEAM_TECHNICAL_REQUIREMENTS.md`. Every incident record stores `area_id`. Non-camera alerts default to the device-to-zone hardware mapping registered in `devices.area_id` in SQLite.

---

## TBD-RISK-07: Risk bands and thresholds
**Status**: CONFIRMED

**Requirement**
* Numeric score range: `0` to `100`.
* The four fixed operational risk priority bands are:
  - `0–29`: **Low** (Dashboard action: Continue monitoring)
  - `30–59`: **Moderate** (Dashboard action: Review trend)
  - `60–79`: **High** (Dashboard action: Recommend inspection)
  - `80–100`: **Critical** (Dashboard action: Prioritise inspection and operator review)
* Cautious wording rule: The label `"possible electrical-risk hotspot; inspection recommended"` shall appear ONLY when `Risk >= 60` (High or Critical) AND `E >= 0.40` (at least 40% of confirmed incidents verified electrical). The UI shall never state "wiring fault confirmed".

**Team answer**: Confirmed. Bands are explicitly defined as **Low (0–29), Moderate (30–59), High (60–79), and Critical (80–100)** in Section 6.2 of `TEAM_TECHNICAL_REQUIREMENTS.md`. Cautious wording criteria are strictly bounded to prevent unverified diagnoses.

---

## TBD-RISK-08: Cold start behavior
**Status**: CONFIRMED

**Requirement**
* If an area has 0 confirmed incidents within the 180-day window:
  - Frequency `F = 0.0`.
  - Recency `R = 0.0`.
  - Electrical ratio `E = 0.0`.
  - Anomaly `A` and Maintenance `M` are calculated from live telemetry and inspection logs respectively.
* If all incident history is absent and no inspections are logged, the score evaluates based on existing anomaly/maintenance values; if sensor streams are offline/uninitialized, the score displays `"No verified history (last 180 days)"` with state `not_calculated` per RISK-G4.
* `N_min = 1`: A single confirmed incident is sufficient to calculate a non-zero historical score. No synthetic padding is permitted.

**Team answer**: Confirmed. `N_min` is set to **1** confirmed incident. Cold-start areas with zero incidents evaluate with `F=0`, `R=0`, `E=0` while retaining `A` and `M` context, or show `"No verified history (last 180 days)"` if uninitialized, as mandated by Sections 6.2 and 6.4.

---

## TBD-RISK-09: What-if and predictive semantics
**Status**: CONFIRMED

**Requirement**
* In accordance with Section 0.2, 6.0, 6.2, and 6.4 of `TEAM_TECHNICAL_REQUIREMENTS.md`, the prototype implements an **Explainable Weighted Priority Index**, not an unconstrained predictive ML model.
* The `/planner` page shall be entitled **"Area Risk Index"** and display transparent, auditable factor weights.
* All demonstration incidents not originating from real-world sensors shall be explicitly labelled `"synthetic demonstration data"`.
* Logistic regression is formally specified as the next-stage predictive model after a threshold of at least 500 municipal verified incident records is collected (F3-FR-016).

**Team answer**: Confirmed. The UI and documentation strictly use the title **"Area Risk Index"** with explainable rule-based scoring and cautious predictive labeling.

---

## Affected parts (verified in repo)
* Backend: `app/services/risk.py`, `app/api/endpoints/risk.py`, schema `area_risk`
* Frontend: `/planner` (City Risk Planner View) area ranking table, score breakdown cards, and CSV export
* Database: SQLite tables `area_risk`, `inspections`, `feedback`, and `incidents`
* Tests: Unit tests for exact 45-row seed dataset calculation, band boundary checks, and cold-start fallback

## Dependencies on other sections
* `TBD-INC-01`: Incident state machine (`CONFIRMED` state transitions drive `F`, `R`, and `E`)
* `TBD-ROUTE-07`: Area ID consistency (`Area A`, `Area B`, `Area C`) between routing graphs and physical model
* `TBD-FUSION-04`: Feature 1 and Feature 3 weight separation (Detection weights sum to 1.00; Risk weights sum to 1.00 as independent parameter sets)