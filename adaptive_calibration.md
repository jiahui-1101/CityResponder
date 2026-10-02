# CityResponder: Adaptive Calibration Learning Policy (TBD section 8)

Owner: Zhen Jie
Covers: TBD-CAL-01 to TBD-CAL-10
Source basis: Proposal sections 2, 4.4 and 5.1; `SOURCE_TBD_REQUIREMENTS.md` section 8; `TEAM_TECHNICAL_REQUIREMENTS.md` sections 6.3, 6.4, 9.5, 11, 15

**Status tags:** `CONFIRMED` (all requirements confirmed and approved; decisions and answers documented).

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
**Status:** `CONFIRMED`

**Requirement**
- One training sample = `x = (S, T, V, H)` plus label `y`.
- `x` is taken from the evaluation window that completed the 3-consecutive-window check, which is the window that raised the alert.
- A sample is eligible only if all four channels were `available` in that window (same rule as the proposal's fusion code).
- Channel scores are stored with the incident. Because `x` does not depend on the weights, old samples can be reused for any new weight version.

**Why:** that window is the moment the system decided, so it is what the operator's verdict judges.
**Assumption:** the audit ledger stores the four channel scores for that window (the proposal says all inputs and decisions are logged). Please check in the code.
**Team answer:** Confirmed in `backend/app/fusion/confidence.py` and `backend/app/events/models.py`. The `FusionConfidenceResult` stores individual channel scores (`s_score`, `t_score`, `v_score`, `h_score`), active `weight_version_id`, and evaluation window source references upon alert confirmation. Stored feature inputs $x$ do not depend on the weights, ensuring historical outcomes remain reusable across new weight versions.

## TBD-CAL-02: Label semantics
**Status:** `CONFIRMED`

**Requirement**
- CONFIRM gives `y = 1` (verified true alarm).
- REJECT gives `y = 0` (verified false alarm).
- CANCEL is not used for calibration.

**Why:** the proposal says verified true and false alarms feed calibration. CANCEL has no clear true/false meaning.
**Dependency:** must match TBD-INC-01 (section 6, other owner).
**Team answer:** Confirmed to match `TEAM_TECHNICAL_REQUIREMENTS.md` Section 6.3 and `incident_feedback.md` (TBD-INC-01). Only Operator-verified outcomes feed calibration: `CONFIRM` / `VERIFIED_FIRE` yields $y=1$ (true incident), while `REJECT` / `VERIFIED_FALSE_ALARM` yields $y=0$ (false alarm). `CANCEL` (duplicate or drill) carries no ground-truth fire verdict and is excluded from training sets.

## TBD-CAL-03: Loss / objective function
**Status:** `CONFIRMED`

**Requirement:** mean squared error (Brier score) over the training set:
`L(w) = (1/n) * sum_i (w·x_i - y_i)^2`

**Why:** the output `w · x` is already in [0, 1] and linear in `w`, so this is the simplest loss that is easy to explain to the Admin and has a clean gradient.
**Team answer:** Confirmed. Mean squared error (Brier score) is strictly proper for binary probabilities in $[0, 1]$, linear in weights, convex, and directly interpretable for the Administrator on the preview dashboard.

## TBD-CAL-04: Gradient and update equation
**Status:** `CONFIRMED`

**Requirement**
1. Gradient: `g = (2/n) * sum_i (w·x_i - y_i) * x_i`.
2. Candidate: `w_candidate = Project(w_active - eta * g)` with `eta = 0.02`.
3. `Project` is the exact Euclidean projection onto `{ 0.10 <= w_i <= 0.50, sum w_i = 1.00 }`. Method: find a shift `lambda` so that `sum_i clip(v_i - lambda, 0.10, 0.50) = 1` (bisection works because the sum decreases as lambda increases and a solution always exists for 4 weights).
4. One update step per calibration run. The result is only a candidate that the Admin previews. It is not live.

**Not confirmed:** whether "step 0.02" in the proposal means the learning rate (as written above), or the maximum change allowed per weight. I am about 60% sure, below 80%.

**Needs from Zhen Jie:** question 4.

**3 Considered Decision Options for Question 4:**
1. *Option 1 (Sequential Online Deltas):* Sequentially update weights for each of the 30 samples using $w_i \leftarrow \text{clip}(w_i + \eta \cdot \text{error} \cdot x_i)$ with $\eta=0.02$. (Rejected: Order-dependent, non-commutative, violates batch determinism).
2. *Option 2 (Batch MSE Gradient with $\eta=0.02$ and Exact Euclidean Simplex Projection - RECOMMENDED & ADOPTED):* Treat $\eta = 0.02$ as the gradient learning rate over the batch of $n=30$ training outcomes: $g = \frac{2}{n} \sum_{i=1}^n (w_{\text{active}} \cdot x_i - y_i) x_i$. Candidate raw weights are $w_{\text{raw}} = w_{\text{active}} - \frac{\eta}{2} g = w_{\text{active}} + \frac{0.02}{n} \sum_{i=1}^n (y_i - \hat{y}_i) x_i$. Because $|y_i - \hat{y}_i| \le 1.0$ and evidence $x_{i,c} \in [0, 1]$, the maximum raw delta per weight across the batch is mathematically bounded by $\le 0.02$ (2 percentage points). This raw vector is then deterministically projected onto $\{w_i \in [0.10, 0.50], \sum w_i = 1.00\}$ via bisection water-filling (`project_to_bounded_simplex`).
3. *Option 3 (Unconstrained Gradient with Hard Coordinate Truncation):* Take an unconstrained gradient step and truncate component shifts exceeding $\pm 0.02$ prior to normalization. (Rejected: Distorts the gradient trajectory and is redundant under Option 2).

**Team answer:** Option 2 is selected and **CONFIRMED**. As defined in `TEAM_TECHNICAL_REQUIREMENTS.md` Section 6.3, "step 0.02" is the learning rate $\eta = 0.02$ applied to the batch gradient across the 30 training outcomes. Because evidence $x_i \in [0, 1]$ and error $(y_i - \hat{y}_i) \in [-1, 1]$, the raw change prior to projection cannot exceed 2 percentage points ($0.02$). Projection onto the bounded simplex is performed deterministically via `project_to_bounded_simplex` in `app/calibration/schemas.py`.

## TBD-CAL-05: Validation metric
**Status:** `CONFIRMED`

**Requirement:** Brier score on the 15 validation outcomes: `B(w) = (1/15) * sum (w·x_i - y_i)^2`. The page may also show accuracy at `C >= 40` for information only. It does not decide the gate.

**Team answer:** Confirmed. The primary validation metric is the Brier score on the 15 held-out validation samples. Secondary metrics (such as accuracy at the confirmation threshold $C \ge 65$ or baseline $C \ge 40$) are shown in the Admin preview UI for informational and diagnostic purposes only.

## TBD-CAL-06: Performance gate threshold
**Status:** `CONFIRMED`

**Requirement**
- A candidate may be approved only if `B(w_candidate) <= B(w_active)` on the same 15 validation outcomes (no regression).
- No minimum improvement margin is required.
- The Admin preview shall show both Brier values and the weight changes.

**Why:** the source gives no numeric target. "Not worse than the current version" is the minimum sensible safety rule. With only 15 samples, a strict improvement margin would be noise.
**Team answer:** Confirmed. The performance gate strictly enforces zero regression on validation: `passed = (validation_brier <= active_brier)`. Candidates that fail this gate cannot be approved by the Admin (`HTTP 409 Conflict` on `/approve`), ensuring candidate activations never degrade empirical accuracy.

## TBD-CAL-07: 30/15 dataset selection
**Status:** `CONFIRMED`

**Requirement**
- Eligible outcomes = verified (CONFIRM or REJECT) incidents that meet CAL-01.
- Take the 45 most recent eligible outcomes by verification time. The newest 15 are validation and the 30 before them are training. No sample is in both sets.
- Both sets must contain at least one CONFIRM and at least one REJECT. Otherwise calibration is blocked and the page says why.
- If fewer than 45 are eligible, calibration is unavailable and shows the current count.

**Why:** a time-ordered split is deterministic and avoids testing on older data than the model was trained on.
**Team answer:** Confirmed. The 45-sample historical split is strictly chronological (oldest 30 for training, newest 15 for validation). Calibration candidate generation rejects sets with fewer than 45 eligible samples or sets lacking binary diversity ($\ge 1$ true alarm and $\ge 1$ false alarm in each split).

## TBD-CAL-08: Initial production version
**Status:** `CONFIRMED`

**Requirement:** version `v1` = S 0.30, T 0.20, V 0.35, H 0.15 (the proposal's fusion formula). It satisfies the bounds and sums to 1.00.
**Team answer:** Confirmed. Initial production version `v1` initializes with $S=0.30, T=0.20, V=0.35, H=0.15$, matching baseline constants in `backend/app/fusion/confidence.py` and `config/thresholds.json`.

## TBD-CAL-09: Live activation policy
**Status:** `CONFIRMED`

**Requirement (confirmed part)**
- Admin approval makes the candidate the active version. Nothing else activates a version.
- The new version applies to future evaluation cycles, as the proposal says.
- Every stored `C` shall record the weight version id that produced it.

**Not decided:** what happens to an incident that is already being tracked (for example halfway through the 3-window check). Switching weights in the middle could change the decision.
**My recommendation:** an incident keeps the version it started with.

**Needs from Zhen Jie:** question 5.

**3 Considered Decision Options for Question 5 & In-Flight Behavior:**
1. *Option 1 (Immediate Retroactive Recalculation):* All open incidents and partial 3-window evaluation sequences immediately recompute confidence using the new weights. (Rejected: Alters decision history mid-flight, creates audit inconsistencies, and violates `F1-FR-016`).
2. *Option 2 (Forward-Looking Evaluation Cycle Transition with Immutable Incident Binding - RECOMMENDED & ADOPTED):*
   - **Evaluation cycles:** Newly activated weights apply immediately to the very next 1-second evaluation window tick (`t + 1`).
   - **3-window persistence check:** If an alert candidate is partway through its 3-consecutive-window check (e.g., window 2 of 3), window 3 evaluates under the newly active weights. If confidence drops below threshold under the new weights, persistence safely breaks as intended.
   - **Incident immutability:** Once an incident is confirmed / raised, its stored confidence $C$, evidence components, and severity calculation remain permanently bound to the `weight_version_id` active at creation (`F1-FR-016`). Active response states are never retroactively altered.
3. *Option 3 (Global Activation Lockout):* Prohibit Admin activation unless all sensor readings are at baseline and no incidents are active. (Rejected: Impractical and risks operational deadlocks during demonstration).

**Team answer:** Option 2 is selected and **CONFIRMED**. Live activation applies strictly forward-looking to subsequent 1-second evaluation cycles. Any incident already confirmed or undergoing emergency response permanently retains the `weight_version_id` and confidence score recorded at its confirmation window. In-flight 3-window evaluation checks evaluate subsequent windows under the newly active weights.

## TBD-CAL-10: Rollback operational policy
**Status:** `CONFIRMED`

**Requirement (confirmed part)**
- Only an authenticated Admin can roll back, with a written reason.
- Rollback restores the chosen earlier version's weights exactly and makes it the active version. No version is deleted, and the rollback is an appended event in the audit history.
- Rollback is never automatic. If the false-dispatch rate rises above the 10% target after an activation, the system may show a warning to the Admin but it does not roll back by itself.

**Not decided:** in-flight incident behavior (same question as CAL-09).

**3 Considered Decision Options for Rollback:**
1. *Option 1 (Automated Threshold-Based Rollback):* System automatically triggers rollback if false-dispatch rate exceeds 10%. (Rejected: Safety-critical fusion weights must never be altered autonomously without human-in-the-loop review).
2. *Option 2 (Admin-Authenticated Forward-Appending Rollback with Immutable History - RECOMMENDED & ADOPTED):*
   - Rollback is strictly manual, requiring an authenticated Admin re-entering their password with a mandatory written justification of at least 10 characters (`ADMIN-R2`, `SW-FR-011`).
   - Rollback appends a new event record `calibration_version_rollback` and creates a new active version entry cloning the target historical version's weights (`supersedes_version=<active>`, `rollback_from_version=<target>`).
   - Prior records and version history are never deleted or rewritten (append-only ledger).
   - In-flight incidents and historical decisions remain bound to the `weight_version_id` under which they were generated; the rolled-back weights apply strictly forward to subsequent evaluation cycles.
3. *Option 3 (Hard Database Revert):* Delete post-activation records and attempt to reset database state. (Rejected: Violates SQLite append-only immutability triggers and audit integrity).

**Team answer:** Option 2 is selected and **CONFIRMED**. Rollback is strictly an authenticated Admin action requiring password re-verification and audit justification. The rollback appends a new active version in the immutable ledger that restores the target version's weights. Rollback takes effect forward on subsequent evaluation cycles; historical and in-flight incident records remain intact.

---

## Affected parts (please verify in the repo)
- Calibration service (candidate generation, projection, validation, gate)
- Weight version table and audit events
- `/admin` calibration preview/approve/rollback UI
- Unit tests: projection keeps bounds and sum, gate blocks regression, split has no overlap
- `SOURCE_TBD_REQUIREMENTS.md` section 8, `TEAM_CHANGE_LOG.md`

## Dependencies
- TBD-INC-01 (labels), TBD-FUSION-01 to 05 (meaning of S, T, V, H channels)
