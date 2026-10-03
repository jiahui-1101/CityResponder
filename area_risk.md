# CityResponder: Area Risk Requirements (TBD section 7)

Owner: Zhen Jie
Covers: TBD-RISK-01 to TBD-RISK-09
Source basis: Proposal sections 4.4 and 5.1 (Learn phase, `/risk` page), `SOURCE_TBD_REQUIREMENTS.md` section 7

**Status tag:** `CHOSEN` = the proposal does not fully define this item, so it is a design choice made by Zhen Jie (with Claude's help). Every item needs team sign-off and a `TEAM_CHANGE_LOG.md` entry before the real TBD file is updated. If the proposal authors had a specific meaning, theirs wins.

**What the proposal already fixes**
- Score = `100 * (0.30F + 0.25R + 0.20E + 0.15A + 0.10M)`
- Operator-verified incidents only, rolling 180-day window.
- It is a transparent weighted score, "not a black-box prediction".
- Repeated fires may show "possible electrical-risk hotspot; inspection recommended", never a diagnosis.
- The proposal does **not** say what F, R, E, A, M stand for. RISK-01 to 05 below are my choices, built only from data the system already records and from topics in proposal section 3.2.

**General rules (CHOSEN)**
- RISK-G1: Every component F, R, E, A, M is a number in [0, 1].
- RISK-G2: Only incidents the operator verified as real (CONFIRM) count. REJECT and CANCEL do not count (must stay consistent with TBD-INC-01, section 6).
- RISK-G3: Rolling window: an incident counts if its start time is within the 180 days before the calculation time.
- RISK-G4: If a component cannot be calculated, the score is `not_calculated` with a visible reason. No silent zero.
- RISK-G5: The `/risk` page shows the breakdown (F, R, E, A, M values and weights) so the Risk Planner can see why.
- RISK-G6: Notation: for area `a`, `n_a` = number of verified incidents of that area in the window.

---

## TBD-RISK-01: F (Frequency)
**Status:** `CHOSEN`

**Requirement**
- F = how often the area had verified incidents compared with other areas.
- `F = n_a / max over all areas (n_b)`. If the maximum is 0, no area has history (see RISK-08).

**Why:** relative scaling needs no invented cap. The side effect is that the busiest area always gets F = 1.0, so F is a ranking measure, not an absolute one. The "repeated fires" wording in the proposal makes frequency the natural meaning of the first and biggest component.

## TBD-RISK-02: R (Recency)
**Status:** `CHOSEN`

**Requirement**
- R = how recent the latest verified incident of the area is.
- `R = max(0, 1 - d / 180)` where `d` = days since the latest verified incident of that area. Today gives 1.0, 180 days ago gives 0.

**Why:** it uses the same 180-day window as the rest of the score, so no new number is introduced.

## TBD-RISK-03: E (Escalation)
**Status:** `CHOSEN`

**Requirement**
- E = how severe the area's verified incidents were.
- For each verified incident, `s_i = severity score R / 100`, or `1.0` if the Critical person override applied. `E = average of s_i` over the area's verified incidents.
- Incidents without a stored numeric severity are left out of the average. If none has one, E is `not_calculated`.

**Why not "electrical":** the proposal's "electrical-risk" text is only cautious wording, and the system has no field for the cause of a fire, so an electrical indicator cannot be calculated honestly.
**Dependency:** severity score definitions (TBD-SEV, section 3, other owner).

## TBD-RISK-04: A (Access)
**Status:** `CHOSEN`

**Requirement**
- A = how often reaching the area was difficult.
- `A = (verified incidents of the area whose dispatch route had a blocked or conflict-pruned edge, or needed a reroute) / n_a`.
- Data source: route and blockage events already kept in the append-only history.

**Why:** proposal section 3.2 talks about narrow access lanes being blocked, and routing blockages are recorded by the system, so no new data is needed.
**Dependency:** routing events must be logged per incident (section 5, other owner).

## TBD-RISK-05: M (Maintenance / readiness gap)
**Status:** `CHOSEN`

**Requirement**
- M = how many basic readiness checks the area fails.
- Each area has three yes/no checks in the area config, taken from proposal section 3.2: (1) fire certificate valid, (2) emergency alarm audible in the whole building, (3) escape routes and corridors not obstructed (for example by grilles).
- `M = number of failed checks / 3`.
- The City Risk Planner maintains these values. If an area has no values entered, M is `not_calculated` (RISK-G4).

**Why:** these three readiness problems are the ones the proposal gives as real-life examples, and it gives M the lowest weight (0.10), which fits a static factor.

## TBD-RISK-06: Area identity and mapping
**Status:** `CHOSEN`

**What an "area" is:** one building or structure on the 120 cm x 90 cm tabletop model. The proposal gives every structure its own region on the overhead camera image (at least 280 x 180 px), so each of those regions is one area.

**Requirement**
- Area list: one entry per structure ROI. Each has `area_id` (for example `AREA_01`) and a display name that matches the label on the physical model. One shared config list is used by routing, severity and risk.
- Automatic assignment: the incident gets the area whose ROI contains the center point of its fire detection. If the center lies in two ROIs, use the one with the larger overlap.
- No camera detection (for example only the button or smoke sensor triggered): the operator must choose the area when confirming the incident.
- The operator may correct the area when confirming. An incident without an area never counts toward Area Risk.
- The incident record shall store `area_id`. If the current database has no such field, add one.

**Still to fill in by the team:** how many structures there are, their IDs and names.

## TBD-RISK-07: Risk bands and thresholds
**Status:** `CHOSEN`

**Requirement**
- No Low / Medium / High bands until the team defines the cutoffs. The `/risk` page shows only the numeric score and ranking.
- Wording "possible electrical-risk hotspot; inspection recommended" is shown only for an area with 3 or more verified incidents in the window ("repeated" = 3 or more).
- The number 3 is a configuration value, not hard-coded.

**Why 3:** one fire is an event, two is a recurrence, three starts to look like a pattern. Showing a hotspot hint after two would be too easy to trigger by coincidence.

## TBD-RISK-08: Cold start behavior
**Status:** `CHOSEN`

**Requirement**
- `n_a = 0`: show "No verified history (last 180 days)". No score.
- `n_a = 1`: show "Insufficient history (1 of 2)", the raw count and the date. No score.
- `n_a >= 2` (minimum `N_min = 2`): the score is calculated and shown.
- `N_min = 2` is a configuration value.
- A missing component (for example M not entered) makes the score `not_calculated`, never a quiet zero.

**Why 2:** one incident says nothing about a trend. Two is the smallest number that shows a repeat, and still reachable in a demo.

## TBD-RISK-09: What-if and predictive semantics
**Status:** `CHOSEN`

**Requirement**
- No what-if or predictive simulation for now.
- The page is called "Area Risk Index" and described as historical and rule-based.

**Why:** section 4.4 says "not a black-box prediction" and no simulation inputs are defined. Section 5.1 calls it "predictive", so the proposal wording is inconsistent. Suggest telling the leader.

---

## Affected parts (please verify in the repo)
- Backend risk calculation service and tests
- `/risk` page text, breakdown and cold-start messages
- Area config list (area ID, name, three readiness checks) and `area_id` on incidents
- Config values: `N_min = 2`, repeated-fire count = 3
- `SOURCE_TBD_REQUIREMENTS.md` section 7, `TEAM_CHANGE_LOG.md`

## Dependencies on other sections
- TBD-INC-01 (meaning of CONFIRM / REJECT / CANCEL)
- TBD-SEV (severity score for E)
- TBD-ROUTE (blockage events for A, area list with ROI-07)
- TBD-FUSION-04 (if H uses Area Risk, this score feeds fusion)
