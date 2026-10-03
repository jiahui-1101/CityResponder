# CityResponder: Adaptive Calibration Learning Policy (TBD section 8)

Owner: Zhen Jie
Covers: TBD-CAL-01 to TBD-CAL-10
Source basis: Proposal sections 2, 4.4 and 5.1; `SOURCE_TBD_REQUIREMENTS.md` section 8

**Status tag:** `CHOSEN` = the proposal does not fully define this item, so it is a design choice made by Zhen Jie (with Claude's help). Every item needs team sign-off and a `TEAM_CHANGE_LOG.md` entry before the real TBD file is updated. If the proposal authors had a specific meaning, theirs wins.

**Already fixed by the source**
- Calibration adjusts the 4 Feature 1 fusion weights (S, T, V, H).
- Each weight stays in [0.10, 0.50] and the weights sum to exactly 1.00.
- Step setting 0.02, bounded simplex projection.
- 30 training outcomes and 15 separate validation outcomes.
- Admin previews and approves every change, every version is stored, rollback is exact.
- YOLO is not retrained.

**Key idea used in this file**
Because the weights sum to 1 and every channel score is in [0, 1], the fusion confidence `C / 100 = w · x` (where `x = (S, T, V, H)`) is already between 0 and 1. So calibration can be handled as a small regression: how close is `w · x` to the operator's verdict (1 = real fire, 0 = false alarm).

---

## TBD-CAL-01: Training representation
**Status:** `CHOSEN`

**Requirement**
- One training sample = `x = (S, T, V, H)` plus label `y`.
- `x` is taken from the evaluation window that completed the 3-consecutive-window check, which is the window that raised the alert.
- A sample is eligible only if all four channels were `available` in that window (same rule as the proposal's fusion code).
- Channel scores are stored with the incident. Because `x` does not depend on the weights, old samples can be reused for any new weight version.

**Why:** that window is the moment the system decided, so it is what the operator's verdict judges.
**Assumption:** the audit ledger stores the four channel scores for that window (the proposal says all inputs and decisions are logged). Please check in the code.

## TBD-CAL-02: Label semantics
**Status:** `CHOSEN`

**Requirement**
- CONFIRM gives `y = 1` (verified true alarm).
- REJECT gives `y = 0` (verified false alarm).
- CANCEL is not used for calibration.

**Why:** the proposal says verified true and false alarms feed calibration. CANCEL has no clear true/false meaning.
**Dependency:** must match TBD-INC-01 (section 6, other owner).

## TBD-CAL-03: Loss / objective function
**Status:** `CHOSEN`

**Requirement:** mean squared error (Brier score) over the training set:
`L(w) = (1/n) * sum_i (w·x_i - y_i)^2`

**Why:** the output `w · x` is already in [0, 1] and linear in `w`, so this is the simplest loss that is easy to explain to the Admin and has a clean gradient.

## TBD-CAL-04: Gradient and update equation
**Status:** `CHOSEN`

**Requirement**
1. Batch gradient over all 30 training samples: `g = (2/30) * sum_i (w·x_i - y_i) * x_i`.
2. Candidate: `w_candidate = Project(w_active - eta * g)` with `eta = 0.02` (learning rate).
3. `Project` is the exact Euclidean projection onto `{ 0.10 <= w_i <= 0.50, sum w_i = 1.00 }`. Method: find a shift `lambda` so that `sum_i clip(v_i - lambda, 0.10, 0.50) = 1` (bisection; a solution always exists for 4 weights).
4. One update step per calibration run. The result is a candidate for the Admin to preview, not a live version.

**Why:** decided by Zhen Jie: the TBD file calls 0.02 the "batch gradient setting", so it is the learning rate.

## TBD-CAL-05: Validation metric
**Status:** `CHOSEN`

**Requirement:** Brier score on the 15 validation outcomes: `B(w) = (1/15) * sum (w·x_i - y_i)^2`. The page may also show accuracy at `C >= 40` for information only. It does not decide the gate.

## TBD-CAL-06: Performance gate threshold
**Status:** `CHOSEN`

**Requirement**
- A candidate may be approved only if `B(w_candidate) <= B(w_active)` on the same 15 validation outcomes (no regression).
- No minimum improvement margin is required.
- The Admin preview shall show both Brier values and the weight changes.

**Why:** the source gives no numeric target. "Not worse than the current version" is the minimum sensible safety rule. With only 15 samples, a strict improvement margin would be noise.

## TBD-CAL-07: 30/15 dataset selection
**Status:** `CHOSEN`

**Requirement**
- Eligible outcomes = verified (CONFIRM or REJECT) incidents that meet CAL-01.
- Take the 45 most recent eligible outcomes by verification time. The newest 15 are validation and the 30 before them are training. No sample is in both sets.
- Both sets must contain at least one CONFIRM and at least one REJECT. Otherwise calibration is blocked and the page says why.
- If fewer than 45 are eligible, calibration is unavailable and shows the current count.

**Why:** a time-ordered split is deterministic and avoids testing on older data than the model was trained on.

## TBD-CAL-08: Initial production version
**Status:** `CHOSEN`

**Requirement:** version `v1` = S 0.30, T 0.20, V 0.35, H 0.15 (the proposal's fusion formula). It satisfies the bounds and sums to 1.00.

## TBD-CAL-09: Live activation policy
**Status:** `CHOSEN`

**Requirement**
- Admin approval makes the candidate the active version. Nothing else activates a version.
- The new version is used by incidents that start after the approval time.
- An incident that is already being tracked keeps the weight version it started with until it ends (decided by Zhen Jie).
- Every stored `C` records the weight version id that produced it.

**Why:** the proposal says the new version applies to future cycles. Keeping one version per incident stops a decision changing halfway through the 3-window check and keeps the audit trail clear.

## TBD-CAL-10: Rollback operational policy
**Status:** `CHOSEN`

**Requirement**
- Only an authenticated Admin can roll back, with a written reason.
- Rollback restores the chosen earlier version's weights exactly and makes it the active version for incidents that start afterwards. Incidents already being tracked keep their starting version (same as CAL-09).
- No version is deleted. The rollback is an appended event in the audit history.
- Rollback is never automatic. If the false-dispatch rate rises above the 10% target after an activation, the system may warn the Admin, but the Admin decides.

---

## Affected parts (please verify in the repo)
- Calibration service (candidate generation, projection, validation, gate)
- Weight version table and audit events
- `/admin` calibration preview/approve/rollback UI
- Unit tests: projection keeps bounds and sum, gate blocks regression, split has no overlap
- `SOURCE_TBD_REQUIREMENTS.md` section 8, `TEAM_CHANGE_LOG.md`

## Dependencies
- TBD-INC-01 (labels), TBD-FUSION-01 to 05 (meaning of S, T, V, H channels)
