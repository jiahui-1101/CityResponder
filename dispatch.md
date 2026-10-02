### DISPATCH-01: Severity to resources
Use the R bands: Low 0–29, Medium 30–49, High 50–69, Critical 70–80 (or P = 1).
**Team Decision (by type):** 
- **LOW:** 1 Fire unit
- **MEDIUM:** 2 Fire units
- **HIGH:** 2 Fire units + 1 Ambulance
- **CRITICAL:** 2 Fire units + 1 Ambulance + 1 Rescue unit

### DISPATCH-02: Person escalation
**Team Decision:** 
Trigger chain: `P = 1 (YOLO conf ≥ 0.50, inside hazard polygon, 1 frame) -> CRITICAL -> 2 Fire + 1 Amb + 1 Rescue`. We prioritize life safety using a 1-frame trigger, relying on the 0.50 confidence threshold to mitigate false positives.

### DISPATCH-03: Traffic and building actions
Auto path: act after confirmation (C ≥ 40, 3 windows, ≥ 2 channels); operator can reject or cancel at any time.
Manual path: button press dispatches directly.
**Team Decision:** 
- **(a) Manual Override:** If a calculated R score already exists, dispatch according to that R score. If triggered purely by a manual button press (no R score exists), default to **MEDIUM** severity. This prevents wasting critical medical and rescue resources (maintaining the ≤10% false-dispatch KPI) for minor unclassified fires.
- **(b) Hardware & Traffic Thresholds:** 
  - **Buzzer (Building Alarm):** `ON` for **ALL** confirmed severities (LOW, MEDIUM, HIGH, CRITICAL) to ensure building occupants can evacuate immediately (addressing the Kuching apartment case safety requirement).
  - **Gate & Traffic:** Gate `OPEN` and `GREEN_CORRIDOR` active for **MEDIUM, HIGH, and CRITICAL** only. LOW severity relies on normal traffic flow to minimize city disruption.