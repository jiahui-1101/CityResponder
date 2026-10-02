# CityResponder: Admin / Operational Configuration Policy (TBD section 10)
**Owner:** Zhen Jie
**Covers:** TBD-ADMIN-01
**Source basis:** Proposal section 5.1 (/admin page), section 7 (Admin account: "User RBAC, system health, and freshness calibration"), SOURCE_TBD_REQUIREMENTS.md section 10, TEAM_TECHNICAL_REQUIREMENTS.md sections 1.3, 6.3, 7.3, 8.4, 9.5
**Status tags:** CONFIRMED

## What the source already says
* The System Administrator approves calibration versions and can roll them back.
* The Admin account covers user RBAC, system health, camera/ROI calibration, and bounded adaptive calibration.
* Configuration changes must be versioned, immutable, audited with account ID and justification, and require administrative re-authentication for sensitive operations.

## TBD-ADMIN-01: Which settings may the Admin edit?
**Status:** CONFIRMED

**Requirement (confirmed classification)**

| Setting Category | Admin edits in UI? | Enforcement / Mechanism | Reason |
| :--- | :---: | :--- | :--- |
| **Adaptive Calibration (Preview / Approve / Rollback)** | **Yes** | Re-enter Admin password; simplex bounded weights ($w_i \in [0.10, 0.50]$, $\sum w = 1.00$) | Mandated in F3-FR-012, SW-FR-011 |
| **User Accounts & Roles (RBAC)** | **Yes** | User management API; Argon2 password hash; server-side role check | Explicitly designated in Admin core responsibilities |
| **Camera & Board ROI Calibration** | **Yes** | `/api/admin/camera/calibrate` UI workflow; stores ArUco homography and Building A polygon | Section 8.4, 9.5 Tab 3; needed after hardware placement |
| **Freshness Timeouts & Sensor Health Thresholds** | **Config (Controlled)** | Editable via versioned Admin Config tab (`PUT /api/admin/config`) with mandatory written reason | Solves "freshness calibration" ambiguity |
| **System Health & Telemetry Diagnostics** | **View Only** | Read-only live telemetry via `/ws/live` and `/api/admin/health` | Monitoring metrics are non-settable properties |
| **Fusion Confirmation Gates & Evidence Windows** | **No** | Requires offline code review and `TEAM_CHANGE_LOG.md` entry | Safety-critical baseline ($C \ge 65$, 2 channels, 3 consecutive windows) |
| **Graph Topologies & Actuator Pin Mappings** | **No** | Static configuration file (`config/hardware.json`) | Misconfiguration causes electrical/boot-strap conflicts |
| **MQTT Broker & Database Connection Strings** | **No** | Managed strictly via `.env` file | Credential leakage and process restart risks |

**Rules**
* **ADMIN-R1:** All UI-configurable settings submitted via `PUT /api/admin/config` or `/api/calibration/*` create an immutable versioned snapshot in the SQLite `calibration_versions` / audit log table.
* **ADMIN-R2:** Every Admin action records an audit event (`audit_events`) capturing `user_id`, `timestamp`, `action`, `target_type`, `old_value`, `new_value`, and `reason` (minimum 10 characters).
* **ADMIN-R3:** The server enforces RBAC via signed HttpOnly session cookies. Disallowed endpoints immediately reject requests with HTTP 403 Forbidden.
* **ADMIN-R4:** Activating or rolling back calibration weights requires administrator password re-authentication.

---

### Team Decision & Solution for "Freshness Calibration"

**Needs from Zhen Jie / Clarification Problem:**
The phrase *"Admin covers freshness calibration"* in proposal section 7 is ambiguous between runtime timeout editing vs. diagnostic monitoring.

**3 Considered Decision Options:**
1. **Option 1 (Diagnostic View-Only):** Admin can only monitor freshness indicators (fresh vs. stale). All timeout constants (MQ-2: 2.0 s, DHT22: 3.0 s, Camera: 1.0 s) remain hardcoded constants.
2. **Option 2 (Bounded Parameter Configuration - RECOMMENDED & ADOPTED):** Admin has access to the `/admin` Configuration Tab to fine-tune sensor staleness timeouts and camera ArUco calibration within strictly bounded safety envelopes. Each change increments `config_version` and requires an audit reason.
3. **Option 3 (Unrestricted Runtime Editor):** Admin can freely edit arbitrary thresholds, formulas, and weights directly in the UI without bounds or schema validation.

**Team answer**: **Option 2 is selected and CONFIRMED.** 
As specified in `TEAM_TECHNICAL_REQUIREMENTS.md` Section 9.5 (System Admin View Tab 2 & Tab 3) and Section 7.3 (`PUT /api/admin/config`, `POST /api/admin/camera/calibrate`), "freshness calibration" comprises two concrete functions:
1. **Camera Homography & ROI Freshness Calibration:** Executed via the Admin UI ArUco marker wizard (`POST /api/admin/camera/calibrate`), calibrating the downward 90° overhead camera and saving perspective transformation to `config/camera_board.json` and `config/camera_roi.json`.
2. **Sensor Freshness Timeouts Tuning:** Configurable in the Admin Configuration Tab (`PUT /api/admin/config`) within strictly validated bounds:
   - `MQ-2 Stale Timeout`: Baseline **2.0 s** (Permitted range: `1.0 s` – `5.0 s`)
   - `DHT22 Stale Timeout`: Baseline **3.0 s** (Permitted range: `2.0 s` – `6.0 s`)
   - `Camera Metadata Timeout`: Baseline **1.0 s** (Permitted range: `0.5 s` – `2.0 s`)
   - `Actuator ACK Timeout`: Baseline **500 ms** (Fixed with 1 retry before safe default)

Any parameter change outside these boundaries is rejected by Pydantic schema validation with HTTP 422.

---

## Affected parts (verified in repo)
* Frontend: `/admin` page (Tabs: System Health, Configuration, Camera & AI, Adaptive Calibration, Audit Timeline)
* Backend: `app/api/endpoints/admin.py`, `app/api/endpoints/calibration.py`, `app/core/security.py`
* Database: `audit_events`, `calibration_versions`, `users`, `sessions`
* Configuration files: `config/camera_board.json`, `config/camera_roi.json`, `config/thresholds.json`

## Dependencies on other sections
* `TBD-FUSION-01` / `TBD-FUSION-02`: Fixed baseline fusion thresholds and stale data handling
* `TBD-RISK-07`: Static operational risk bands and weights
* `SW-FR-010` & `SW-FR-011`: Immutable versioning and re-authentication gates