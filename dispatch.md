## Dispatch Matrix

### DISPATCH-01: Responder/Resource Mapping by Severity
`TEAM_TECHNICAL_REQUIREMENTS.md` is the implementation contract. Its current
severity bands and actions supersede the uncoordinated dashboard-only decision.

* **Low (R = 0–24):** Keep E1 at station and notify the Operator.
* **Moderate / MEDIUM (R = 25–49):** Dispatch E1.
* **High (R = 50–74):** Dispatch E1 as urgent.
* **Critical (R = 75–100 or P = 1):** Dispatch E1 at highest priority.

### TBD-DISPATCH-02: Person-Evidence Escalation Beyond the Critical Override
*   **Trigger condition (P = 1):** When YOLO detects a person inside the hazard polygon zone with a confidence ≥ 0.50, `P` is set to 1, and the incident severity is directly forced to Critical.   
*   **1-frame confirmation rule:** The team decided that only 1 frame of person detection is required to trigger the escalation, without waiting for 2-3 frames. Because smoke can quickly obscure a person, life safety must be prioritized.   
*   **Notes and testing:** The 0.50 confidence is the standard detection threshold and not an additional safety limit. This single-frame rule must be verified during testing to ensure the overall false dispatch rate remains within the target of ≤ 10%.   

### DISPATCH-03: Exact Traffic, Gate, Buzzer, and Building-Action Matrix
* **Low:** Keep the defined normal traffic cycle (four-second green and
  one-second yellow), do not open the gate, perform no emergency buzzer action,
  and show the amber affected-zone indicator for five seconds.
* **Moderate / MEDIUM:** Activate `GREEN_CORRIDOR` on the selected safe route,
  pulse the buzzer 500 ms ON / 500 ms OFF, keep the gate closed/default, and
  keep the amber affected-zone indicator active.
* **High / Critical:** Preserve the master-contract urgent response: activate
  the selected-route `GREEN_CORRIDOR`, open the configured safe entrance, and
  activate the continuous building warning outputs.
* The authoritative hardware GPIO map currently has no affected-zone LED pin.
  The amber action remains a required, explicitly unmapped output; no GPIO may
  be invented to make the implementation appear complete.
* `GREEN_CORRIDOR` is route-aware. Its command parameters must identify either
  `PRIMARY` or `STANDBY`. A corridor switch must apply ALL_RED for at least one
  second before the selected route becomes green. PRIMARY means PRIMARY green /
  STANDBY red; STANDBY means PRIMARY red / STANDBY green.
*   **Auto and manual race condition handling:**
    *   Pressing the manual button only generates an `ALERT`, and dispatching begins only after the Operator confirms it.
    *   The severity for a manual dispatch does not default to Critical; the system prioritizes using the calculated `R` score. If `R` cannot be calculated, the severity chosen by the Operator serves as the "floor".
    *   If the system subsequently recovers and calculates a higher `R`, it will automatically upgrade and dispatch additional rescue units (already dispatched units will not be recalled automatically).
    *   If the automated system's conditions are met before the Operator manually confirms, the system will execute the dispatch directly using the `R` score and ignore the Operator's late confirmation action (lock rule).
*   **Failsafe (Safe default) and system release:**
    *   **Triggering failsafe:** Each hardware command has a 500 ms ACK timeout. One retry is allowed. If the retry also fails, the system triggers the failsafe. For High/Critical `NO_SAFE_ROUTE` or hardware failure, trigger physical failsafe (sandbox traffic lights turn ALL_RED, gate CLOSE, and buzzer ON). For Low/Medium, show a dashboard warning only.
    *   **System release:** When an alert is rejected, canceled, or the incident is closed, the traffic corridor is released, the gate is CLOSED, and the buzzer is turned OFF.
    *   **Anti-flicker limit:** Every route change generates a new route version, and older traffic commands automatically expire. When a road removed due to a conflict recovers, it must wait for a 5-second hold-off period before it can be used again to prevent traffic commands from flipping frequently.
