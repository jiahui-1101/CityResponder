## Dispatch Matrix

### TBD-DISPATCH-01: Responder/Resource Mapping by Severity
*   **Low (R = 0–29):** 1 Fire unit, 0 Ambulances, 0 Rescue units.   
*   **Medium (R = 30–49):** 2 Fire units, 0 Ambulances, 0 Rescue units.   
*   **High (R = 50–69):** 2 Fire units, 1 Ambulance, 0 Rescue units.   
*   **Critical (R = 70–80 or P = 1):** 2 Fire units, 1 Ambulance, 1 Rescue unit.   

### TBD-DISPATCH-02: Person-Evidence Escalation Beyond the Critical Override
*   **Trigger condition (P = 1):** When YOLO detects a person inside the hazard polygon zone with a confidence ≥ 0.50, `P` is set to 1, and the incident severity is directly forced to Critical.   
*   **1-frame confirmation rule:** The team decided that only 1 frame of person detection is required to trigger the escalation, without waiting for 2-3 frames. Because smoke can quickly obscure a person, life safety must be prioritized.   
*   **Notes and testing:** The 0.50 confidence is the standard detection threshold and not an additional safety limit. This single-frame rule must be verified during testing to ensure the overall false dispatch rate remains within the target of ≤ 10%.   

### TBD-DISPATCH-03: Exact Traffic, Gate, Buzzer, and Other Building-Action Matrix
*   **Hardware action matrix:**
    *   **Low / Medium:** No traffic corridor is activated (no corridor), the gate stays closed, and the buzzer is OFF. Responder units are assigned/displayed in the dashboard only; no physical sandbox action is triggered.
    *   **High / Critical:** The traffic corridor is activated (GREEN_CORRIDOR), the gate is OPEN, and the buzzer is ON.
*   **Auto and manual race condition handling:**
    *   Pressing the manual button only generates an `ALERT`, and dispatching begins only after the Operator confirms it.
    *   The severity for a manual dispatch does not default to Critical; the system prioritizes using the calculated `R` score. If `R` cannot be calculated, the severity chosen by the Operator serves as the "floor".
    *   If the system subsequently recovers and calculates a higher `R`, it will automatically upgrade and dispatch additional rescue units (already dispatched units will not be recalled automatically).
    *   If the automated system's conditions are met before the Operator manually confirms, the system will execute the dispatch directly using the `R` score and ignore the Operator's late confirmation action (lock rule).
*   **Failsafe (Safe default) and system release:**
    *   **Triggering failsafe:** Each hardware command has a 500 ms ACK timeout. One retry is allowed. If the retry also fails, the system triggers the failsafe. For High/Critical `NO_SAFE_ROUTE` or hardware failure, trigger physical failsafe (sandbox traffic lights turn ALL_RED, gate CLOSE, and buzzer ON). For Low/Medium, show a dashboard warning only.
    *   **System release:** When an alert is rejected, canceled, or the incident is closed, the traffic corridor is released, the gate is CLOSED, and the buzzer is turned OFF.
    *   **Anti-flicker limit:** Every route change generates a new route version, and older traffic commands automatically expire. When a road removed due to a conflict recovers, it must wait for a 5-second hold-off period before it can be used again to prevent traffic commands from flipping frequently.