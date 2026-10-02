# Fire Fusion (S / T / V / H) - TBD Resolutions

## TBD-FUSION-01: S, sensor normalization
**What's missing:** how MQ-2 and DHT22 readings become a number from 0 to 1, and what happens when the data is old or missing.
**My idea:** scale each sensor between a "normal" value and an "alarm" value, then clamp to 0 to 1. So `s_smoke = (reading - baseline) / (alarm - baseline)`, and the same for temperature. Then `S = max(s_smoke, s_heat)`. The proposal says MQ-2 is stale after 2.0 s and DHT22 after 3.0 s, so I would use those. If both are stale, S is unavailable and C is not calculated.
**Need from team:** the baseline and alarm values for both sensors [measure] (we have the testing aerosol and heat pad). Is it ok to use only one sensor if the other one is stale?
**Team answer:**
Use the measured normal and alarm values for MQ-2 and DHT22:
* **DHT22 (Temperature):** normal = 30°C, alarm = 50°C (scaled for tabletop heat pad testing).
* **MQ-2 (Smoke):** normal = 500, alarm = 2000 (0-4095 analog scale).

Each sensor is normalized to 0–1 and clamped to this range. `S = max(s_smoke, s_heat)` using the available sensor values. If one sensor is stale, the other available sensor can still be used. If both sensors are stale, S is unavailable and C is not calculated.

---

## TBD-FUSION-02: T, temporal consistency
**What's missing:** the exact formula for T.
**My idea:** look at the last 3 one-second windows and count how many had some evidence. `T = count / 3`, so it can only be 0, 1/3, 2/3, or 1.
**Worry:** we already have a "3 consecutive windows" rule, so this might count persistence twice. Is that ok? (B) Under Option B, T would just be the temperature score.
**Need from team:** the level that counts as "evidence present" [measure].
**Team answer:**
Use the last 3 one-second windows to calculate temporal consistency:
`T = number of windows with valid evidence / 3`

A window is counted as having evidence when the normalized sensor score `S >= 0.20`, vision score `V >= 0.40`, or the manual button is pressed. The 3-window persistence rule for automatic confirmation remains separate. T is used as a confidence component and does not replace the requirement for 3 consecutive windows.

---

## TBD-FUSION-03: V, vision normalization
**What's missing:** how fire, smoke and person detections become V.
**My idea:** `V` = the highest fire or smoke confidence from YOLO inside the building ROI. If there are many boxes, take the max and don't add them up (otherwise overlapping boxes inflate it). I left person out of V because a person is not proof of fire. Person is used in severity instead. If the camera frame is older than 1.0 s, V is unavailable.
**Need from team:** the minimum YOLO confidence to accept a detection. Should smoke count less than fire?
**Team answer:**
Use the highest YOLO confidence for fire or smoke detected inside the building ROI:
`V = max(Fire confidence, Smoke confidence)`

Person detection is not included in V; it is used for severity assessment instead. Multiple overlapping detections are not added together.
* The minimum accepted YOLO confidence is **0.50**.
* Fire and smoke will use the same confidence threshold for the first implementation. No additional smoke weighting is added to keep the fusion logic simple.

If the camera frame is older than 1.0 s, V is unavailable.

---

## TBD-FUSION-04: H, historical baseline
**What's missing:** where the history comes from, the time range, the formula, and what to do at the start when there is no history.
**My idea:** use the operator-verified incidents in SQLite, with the same 180-day window as Area Risk. `H = area risk score / 100`. For cold start I was thinking `H = 0` but clearly shown as "no_history" in the log, because if H is blocked then nothing can run during the demo. I know the proposal code says not to fill missing values with zero, so I want the team to confirm this exception.
**Other idea:** H could instead mean how unusual the current sensor reading is compared to its own recent average. I don't know which one the team wants. (B) Under Option B, H would be the button/human input.
**Team answer:**
Use operator-verified incidents stored in SQLite as the history source, using the same 180-day period as the Area Risk calculation.
`H = Area Risk Score / 100`

For cold start (no history), explicitly set `H = 0` in the calculation formula. This ensures the system relies strictly on real-time evidence (S, T, V) to reach the threshold, acting as a safe default. Do not use sensor anomaly detection for H in the first implementation.

---

## TBD-FUSION-05: Supporting channels
**What's missing:** what counts as a "supporting channel" and how much support is enough.
**My idea:** count independent sources only: smoke sensor, heat sensor, camera, and manual button. A source supports if it is available and its score is above a minimum. I don't count T and H, because they come from other data and one sensor would be counted twice.
**Need from team:** the minimum score for "supporting" [measure]. Do smoke and heat count as two separate channels?
**Team answer:**
Count only independent evidence sources as supporting channels:
* MQ-2 → Smoke
* DHT22 → Temperature
* Camera → YOLO Fire/Smoke
* Manual Button → Human confirmation/evidence

MQ-2 and DHT22 are treated as two separate independent channels. T and H are not counted as supporting channels because they are derived from existing evidence/history and should not count the same evidence twice.

A channel must be available and meet the minimum supporting score of **0.30** to count. Automatic fire confirmation still requires at least 2 independent supporting channels.

---

## TBD-FUSION-06: Manual button
**What's missing:** what the button actually does.
**My idea:** the button creates an alert on the dashboard right away (the proposal says under 1 s) and counts as one supporting channel. It does not change the C formula and does not skip the 3-window rule or the operator confirmation.
**Need from team:** is that right? Can a button press alone lead to dispatch if the operator confirms?
**Team answer:**
A manual button press immediately creates an alert on the dashboard and counts as one supporting channel (score = 1.0).

The button does not directly change the C formula. It does not skip the 3-window persistence requirement for automatic confirmation. However, if an authenticated Operator manually confirms the incident following a button press, this action bypasses the "at least 2 physical sensors" requirement and directly triggers resource dispatch.