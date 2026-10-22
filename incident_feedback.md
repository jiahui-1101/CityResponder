## Incident Feedback Lifecycle

### TBD-INC-01: Verified Feedback Downstream Meaning
*   **Who verifies:** Only the Operator. The Firefighter sends a preliminary outcome, and then the Operator verifies and closes the incident. Risk score calculations and model calibration use **only** operator-verified incidents.
*   **Two kinds of decisions:**
    *   **At alert time (Operator):** `CONFIRM`, `REJECT` or `CANCEL`. Executing any of these requires a written reason.
    *   **At closing time (Operator):** `VERIFIED_FIRE` or `VERIFIED_FALSE_ALARM`.
*   **What each decision means:**

| Decision | Area Risk (180 days) | Calibration label | False dispatch |
|---|---|---|---|
| CONFIRM, then VERIFIED_FIRE | counts | 1 (fire) | no |
| REJECT, or VERIFIED_FALSE_ALARM | no | 0 (not a fire) | yes, if commands were already sent |
| CANCEL | no | not used | no, reported separately |

*   **Rules:**
    *   `CANCEL` requires a reason type: duplicate or drill.
    *   "Not a fire" must use `REJECT`, never `CANCEL`.
    *   A real fire that went out by itself is `CONFIRM`, then `VERIFIED_FIRE`.
    *   An incident without Operator verification is not used for risk or calibration.
    *   A `REJECT` before any hardware command was sent (for example, while still in the ALERT stage) is not considered a false dispatch.
*   **Training and validation (45 outcomes):**
    *   Fixed split, not random. The two sets do not overlap.
    *   Training: 30 (15 fire + 15 non-fire).
    *   Validation: 15 (8 fire + 7 non-fire).

### TBD-INC-02: Incident Lifecycle / State Model
*   **Start state:**

| State | Meaning |
|---|---|
| ALERT | A manual button press created an alert on the dashboard. It is not confirmed yet. |

*   **Main path:**

| State | Meaning |
|---|---|
| CONFIRMED | **Auto:** C ≥ 40 for 3 consecutive windows with ≥ 2 supporting channels.<br>**Manual:** The Operator manually confirmed an ALERT. |
| RESPONDING | Route and hardware commands sent to the sandbox, waiting for ACK. |
| ACTIVE | ACK received from hardware. |
| CONCLUDED | Firefighter sent the preliminary outcome report. |
| VERIFIED | Operator checked the outcome and closed the incident. Corridor is released, gate CLOSE, buzzer OFF. |

*   **Side states:**

| State | When | What happens |
|---|---|---|
| FAILSAFE | High or Critical severity only: `NO_SAFE_ROUTE` or `ACTUATOR_ACK_TIMEOUT` occurs. | Sandbox traffic lights turn All-Red, gate CLOSE, buzzer ON. |
| REJECTED | Operator determines it is not a fire. | Corridor released, gate CLOSE, buzzer OFF. |
| CANCELLED | Operator cancels due to duplicate or drill. | Corridor released, gate CLOSE, buzzer OFF. |

*   **Low and Medium Severities:** Hardware actions follow the authoritative dispatch matrix: Low preserves the normal traffic cycle and requests the five-second amber affected-zone indication; Medium activates the selected-route green corridor, 500 ms ON/OFF buzzer pattern, and amber affected-zone indication while keeping the gate closed/default. These commands use the normal ACK path. The existing `NO_SAFE_ROUTE`/timeout failsafe policy is unchanged by this dispatch alignment: Low/Medium retain dashboard-warning handling rather than the High/Critical physical safe-default sequence.
*   **Before CONFIRMED:** An automatic detection that has not passed the strict confirmation gate is not considered an incident. The system simply reverts to monitoring.
*   **ALERT that nobody handles:**
    *   There is no automatic timeout and no automatic close for an ALERT. It stays active until the Operator acts, or until the automatic conditions are met and it becomes `CONFIRMED`. This ensures a fallback if the fire is real.
    *   After 30 seconds without action, the dashboard flashes the ALERT as "unattended" and repeats this every 30 seconds. The reminder is saved in the log as `ALERT_UNATTENDED`. It does not change the state and does not create a calibration label.
*   **Lock rule (Auto and manual race condition handling):**
    *   The transition from ALERT to CONFIRMED is a single database transaction. Only the first valid action wins.
    *   If the automatic conditions are met first, the system automatically confirms the incident. The Operator's Confirm button turns grey, and the backend ignores any late Confirm clicks (logged as: "confirm ignored, already confirmed"). The severity follows the calculated `R` score. The Operator can still REJECT or CANCEL.
    *   If the Operator confirms first, the severity is the band of `R`. If `R` cannot be calculated, the Operator must choose the severity.
    *   An Operator-chosen severity serves as the **minimum (floor)**. If `R` becomes available later and requires a higher severity band, the higher severity is automatically used and the change is logged. `P = 1` always escalates to Critical. Severity is never lowered automatically.
*   **Other rules:**
    *   `REJECTED` and `CANCELLED` can only be triggered by the Operator. They are final states and cannot be reopened.
    *   From `FAILSAFE`, the Operator can click retry after the physical problem is fixed. The incident goes back to `RESPONDING` with a new route version.
    *   The Operator can verify an incident without a Firefighter outcome. The incident can transition straight from `ACTIVE` to `VERIFIED`. The log record will show "no firefighter report".
    *   Every state change saves the timestamp, the initiator (system or user), and a reason code. A system confirmation has no written reason, only the system code.
    *   Records are strictly immutable (never edited). A correction always generates a new record.
*   **Reason codes saved in the log (Note: these are not states):**
    *   `SENSOR_STALE` (also used for a failed reading), `TIME_MISMATCH`, `SENSOR_CONFLICT`. Each must be saved with its source ID: `MQ2`, `DHT22`, `CAM`, `IR-A`, `IR-B`. Road routing codes must also save the specific road edge ID.
    *   `NO_SAFE_ROUTE`, `ACTUATOR_ACK_TIMEOUT`, `ALERT_UNATTENDED`.
*   **Final Check:** If the backend code already implements its own list of states, ensure the codebase matches this document strictly.
