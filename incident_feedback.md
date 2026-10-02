# 6. Incident Feedback Lifecycle

## INC-01: What CONFIRM / REJECT / CANCEL mean downstream

### Zhenjie idea 
- CONFIRM: counts in Area Risk, calibration label = 1 (real fire), not a false dispatch.
- REJECT: not in Area Risk, calibration label = 0 (false alarm), counts as a false alarm that was stopped.
- CANCEL: not in Area Risk, not used for training. If it was cancelled after dispatch because it was a false alarm, then it counts as a false dispatch. CANCEL needs a reason type (false alarm / duplicate / drill / resolved).

Question from Zhenjie: is this right? Who is the verifier: operator only, or also firefighter feedback (proposal 4.4)?

### JIABAO idea 
From the proposal: only the Operator verifies. The Firefighter sends a preliminary outcome, then the Operator verifies and closes the incident (Figure 7.2, step 13). Risk score and calibration use only operator-verified incidents (5.4).

**Two kinds of decision**
- At alert time (Operator): CONFIRM / REJECT / CANCEL, with a written reason.
- At closing time (Operator): VERIFIED_FIRE / VERIFIED_FALSE_ALARM.

| Decision | Area Risk (180 days) | Calibration label | False dispatch |
|---|---|---|---|
| CONFIRM then VERIFIED_FIRE | counts | 1 (fire) | no |
| REJECT or VERIFIED_FALSE_ALARM | no | 0 (not a fire) | yes, if commands were already sent |
| CANCEL | no | not used | no, reported separately |

- CANCEL needs a reason type: duplicate or drill.
- "Not a fire" must use REJECT, not CANCEL.
- A real fire that went out by itself is CONFIRM, then VERIFIED_FIRE.
- Incidents without Operator verification are not used for risk or calibration.

**Training and validation (45 outcomes)**
- Fixed split, not random.
- Training: 30 (15 fire + 15 non-fire).
- Validation: 15 (8 fire + 7 non-fire).
- The two sets do not overlap.

### What changed from the Zhenjie idea
- CONFIRM had two meanings (alert time and outcome). Now there are two names.
- "False alarm" was in both REJECT and CANCEL. Now "not a fire" is only REJECT.
- "Resolved" is removed from CANCEL. A real fire that went out is CONFIRM.
- Verifier: Operator only. The Firefighter gives a preliminary outcome.
- Section "4.4" does not exist in the proposal. The source is Figure 7.2, step 13.
- Added the 30 / 15 split.

---

## INC-02: Incident states

### Zhenjie idea 
What is not known: which states the code uses now.
Minimal idea: PENDING, then CONFIRMED or REJECTED. CONFIRMED can become CANCELLED.
Question: please send the real list of states from the code so the doc matches.

### JIABAO idea 
The proposal has no state list. This list is built from Figure 7.2.

**Main path**

| State | Meaning |
|---|---|
| CONFIRMED | C ≥ 40 for 3 windows with ≥ 2 channels, or manual button press |
| RESPONDING | Route and commands sent, waiting for ACK |
| ACTIVE | ACK received |
| CONCLUDED | Firefighter sent the preliminary outcome |
| VERIFIED | Operator checked the outcome and closed the incident |

**Side states**

| State | When | What happens |
|---|---|---|
| FAILSAFE | NO_SAFE_ROUTE or ACTUATOR_ACK_TIMEOUT | All-Red, gate CLOSE, buzzer ON |
| REJECTED | Operator says not a fire | Corridor released, gate CLOSE, buzzer OFF |
| CANCELLED | Operator cancels (duplicate / drill) | Corridor released, gate CLOSE, buzzer OFF |

**Rules**
- Before CONFIRMED there is no incident. The system goes back to monitoring.
- REJECTED and CANCELLED need a written reason. Only the Operator can do them.
- REJECTED and CANCELLED are final. They cannot be reopened.
- From FAILSAFE, the Operator can retry after the problem is fixed. The incident goes back to RESPONDING with a new route version.
- The Operator can verify without a Firefighter outcome. The record shows "no firefighter report".
- Every change saves the time, who did it (system or user), and a reason code.
- Records are never edited. A correction is a new record.

**To check against the code:** if the code already has states (for example PENDING), the doc and the code must match.

### What changed from the Zhenjie idea
- Added the full path: RESPONDING, ACTIVE, CONCLUDED, VERIFIED.
- Added FAILSAFE and what each side state does to the hardware.
- Added rules for retry, final states, and records that are never edited.
