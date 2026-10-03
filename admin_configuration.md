# CityResponder: Admin / Operational Configuration Policy (TBD section 10)

Owner: Zhen Jie
Covers: TBD-ADMIN-01
Source basis: Proposal section 5.1 (`/admin` page), section 7 (Admin account: "User RBAC, system health, and freshness calibration"), `SOURCE_TBD_REQUIREMENTS.md` section 10

**Status tag:** `APPROVED` = decided and approved by Zhen Jie as owner of this section. No separate team sign-off was requested. The proposal does not fully define these items, so they are design decisions; if the proposal authors had a specific meaning, theirs should replace it. Each decision is recorded in `TEAM_CHANGE_LOG.md`.

**What the source already says**
- The System Administrator approves calibration versions and can roll them back.
- The Admin account is described as covering user RBAC, system health and "freshness calibration".
- The proposal does not describe a universal settings editor.

---

## TBD-ADMIN-01: Which settings may the Admin edit?
**Status:** `APPROVED`

**Requirement**

| Setting | Admin edits it in the UI? | Reason |
|---|---|---|
| Calibration: preview, approve, rollback | Yes | Defined by the source |
| User accounts and roles (RBAC) | Yes | Admin account description in the proposal |
| Sensor freshness timeouts | Yes, only inside the allowed range below | Decided by Zhen Jie: more flexible; proposal says Admin handles "freshness calibration" |
| System health | View only | Monitoring, not a setting |
| Fusion thresholds (`C >= 40`, 3 windows, 2 supporting channels) | No | Safety-critical, source-defined |
| Fusion weights | Only through calibration | Source-defined governance |
| Severity thresholds and weights | No | Safety-critical |
| Routing weights (0.70 / 0.20 / 0.10), actuator ACK timeout | No | Source-defined constants |
| Risk thresholds, N_min, repeated-fire count | No | Not source-defined yet, change only through change-control |
| Evidence retention duration (180 days) | No | Policy value, change-control only |
| Sensor alarm thresholds (smoke, temperature) | No | Physical calibration values, change-control only |
| MQTT settings | No | A wrong value can break sensors and actuators |
| Model paths | No | A wrong path can disable detection |

**General rules**
- ADMIN-R1: Anything the Admin cannot edit in the UI is changed only in config/code through the team's change-control (new entry in `TEAM_CHANGE_LOG.md`).
- ADMIN-R2: Every Admin change is an appended audit event with the Admin's identity, the old and new value, and a written reason.
- ADMIN-R3: The server enforces the Admin role and the allowed ranges. Hiding a button in the UI is not enough.

### Allowed range for freshness timeouts (`APPROVED`)

| Source | Default (source) | Allowed range | Reason |
|---|---|---|---|
| MQ-2 | 2.0 s | 1.5 s to 3.0 s | The lower limit avoids marking a normal reading as stale if the sensor node publishes about once per second. The upper limit (1.5x default) stops old smoke data from being used. |
| DHT22 | 3.0 s | 2.5 s to 4.0 s | The DHT22 can only give a new reading about every 2 seconds (as I remember from its datasheet, please verify), so a limit below that would flag good data as stale. The upper limit is the default plus 1 second. |
| Camera | 1.0 s | 0.5 s to 1.0 s | The proposal requires camera data fresher than 1.0 s, so the Admin may only make it stricter, never looser. Detection runs at 5 FPS or more (a frame at least every 200 ms), so 0.5 s still leaves margin. |

Rules for freshness changes:
- The server rejects values outside the range.
- A change applies from the next evaluation window and is shown on the system health view next to the default.
- "Reset to default" is available.
- **Check before use:** the lower limits assume the sensor node publishes at least once per second and the DHT22 is read about every 2 s. Please confirm the real publish interval in the SN1 firmware. A timeout must always be at least 1.5 times the real publish interval.

**Why these ranges:** they are engineering judgment, not from the source. They protect against two risks: false "stale" flags (too tight) and old data being trusted (too loose).

---

## Affected parts (please verify in the repo)
- `/admin` page, backend admin endpoints, role checks and range validation
- Config files for thresholds, MQTT and model paths (read-only at runtime)
- Audit events for admin actions
- `SOURCE_TBD_REQUIREMENTS.md` section 10, `TEAM_CHANGE_LOG.md`
