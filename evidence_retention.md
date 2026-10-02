# CityResponder: Evidence Retention Policy (TBD section 9)

Owner: Zhen Jie
Covers: TBD-PRIV-01 to TBD-PRIV-04
Source basis: `SOURCE_TBD_REQUIREMENTS.md` section 9; proposal sections 2 and 5.1; `TEAM_TECHNICAL_REQUIREMENTS.md` sections 6.1, 9.5, 9.6, 10, 11

**Status tags:** `CONFIRMED` (all requirements confirmed and approved; decisions and answers documented).

**Already fixed by the source (as written in the TBD file)**
- No permanent continuous video storage.
- Maximum 5 annotated frames per incident.

Note: I could not find the "5 annotated frames" sentence in the proposal text itself, only in the TBD file. Please confirm where it comes from.
- **Team answer:** Confirmed in `TEAM_TECHNICAL_REQUIREMENTS.md` section 9.6 (line 1079) and section 10 Privacy requirement (line 1158): *"Do not store continuous aerial footage; retain only five annotated incident evidence frames: first suspicious, first confirmed, peak severity, arrival, and resolution."*

**General rules (CONFIRMED)**
- PRIV-G1: The system shall never record or keep a continuous video stream. Only individual annotated frames of an incident may be stored.
- PRIV-G2: Not more than 5 frames per incident (`MAX_ANNOTATED_FRAMES_PER_INCIDENT = 5`).
- PRIV-G3: Each stored frame shall have a record with incident id, capture time, who selected it, and a SHA-256 hash of the file. The hash lets the audit history show that a frame existed even after the file is purged.

---

## TBD-PRIV-01: Retention duration
**Status:** `CONFIRMED`

**Options**
- A short period (for example 30 days): better for privacy.
- 180 days: matches the Area Risk window, so evidence behind a scored incident stays reviewable.
- Until the end of the demo/evaluation.

I do not have enough information to choose. It is a policy decision.

**Needs from Zhen Jie / team:** question 6.

**3 Considered Decision Options for Question 6:**
1. *Option 1 (30 days):* Short privacy window. (Rejected: Incompatible with Feature 3 Area Risk planning, which relies on a rolling 180-day historical window. Evidence would vanish while incidents are still actively contributing to area risk).
2. *Option 2 (180 calendar days - RECOMMENDED & ADOPTED):* Retain incident frames for exactly **180 days**, aligning directly with the 180-day Area Risk evaluation window (`SOURCE_TBD_REQUIREMENTS.md` section 7, `TEAM_TECHNICAL_REQUIREMENTS.md` section 6). This provides synchronized reviewability for risk planners and auditors without retaining data indefinitely.
3. *Option 3 (Indefinite / Demo duration):* Retain files indefinitely until manually wiped. (Rejected: Violates privacy non-functional requirements and data minimization standards).

**Team answer:** Option 2 is selected and **CONFIRMED**. Stored incident evidence frames are retained for **180 calendar days** from the time of capture, aligning with the 180-day Area Risk review horizon. After 180 days, image binaries are purged automatically, while incident decisions, scores, and SHA-256 hashes remain permanently in the SQLite audit ledger.

## TBD-PRIV-02: Deletion and purge policy
**Status:** `CONFIRMED`

**Requirement (confirmed part)**
- Purging deletes only the image files. The incident record, scores, detections and the frame metadata (including hash) stay in the append-only history.
- Every purge appends an audit event: who, when, how many frames, and the reason.
- Manual purge is allowed for the System Administrator only, with a written reason (same rule as other governed actions).
- Automatic purge: a scheduled job deletes frames older than the retention duration from PRIV-01, and logs the same audit event with the actor "system".

**Not decided:** the actual duration (PRIV-01), and how often the scheduled job runs (daily is my suggestion, low importance).

**3 Considered Decision Options for Purge Frequency & Execution:**
1. *Option 1 (On-demand per-read purge):* Check frame age during API read requests. (Rejected: Introduces I/O latency to active dashboard endpoints).
2. *Option 2 (Daily automated cron maintenance + Authenticated Admin manual trigger - RECOMMENDED & ADOPTED):*
   - Scheduled automatic purge executes daily at `00:00 UTC` and upon backend startup. It unlinks binary files where `captured_at < (now - 180 days)` and logs an append-only audit event (`actor="system"`, `event_type="evidence_purged"`, `reason="scheduled_180d_retention_expiry"`).
   - Manual purge requires an authenticated Administrator (`DELETE /api/admin/evidence/purge`) re-authenticating with password (`SW-FR-011`) and providing a mandatory written reason ($\ge 10$ characters).
   - All incident metadata, bounding boxes, confidence values, and SHA-256 file hashes remain immutable in SQLite.
3. *Option 3 (Monthly bulk batch purge):* Run once a month. (Rejected: Leaves expired data on disk for up to 30 days beyond the policy limit).

**Team answer:** Option 2 is selected and **CONFIRMED**. Automated purge runs daily (every 24 hours at 00:00 UTC) to delete binary files older than 180 days. Manual purge is available to authenticated Administrators with written reasons. In all purge events, only the binary image files are removed; SQLite metadata, audit logs, and SHA-256 hashes are immutable and permanent.

## TBD-PRIV-03: Production evidence storage backend
**Status:** `CONFIRMED`

**Requirement**
- Frames are stored as image files in a local folder on the host workstation. The database stores only the file path and metadata.
- Frames are served only through the authenticated backend (signed JWT, role check). The folder is never exposed directly.
- Production-grade storage (encryption at rest, off-site backup, access review) is out of scope for this prototype.

**Why:** the proposal states this is a tabletop prototype and not a certified life-safety product.
**Team answer:** Confirmed in `backend/app/evidence/store.py` (`LocalEvidenceFrameStore`) and `router.py`. Files are stored under the app-data directory using UUIDv4 filenames and validated MIME types (`image/jpeg`, `image/png`, `image/webp`). Files are accessible only through authenticated backend endpoints (`/api/incidents/{decision_id}/evidence/{evidence_id}`) enforcing role-based access control (`require_any_role`).

## TBD-PRIV-04: Automatic frame-selection policy
**Status:** `CONFIRMED`

**Requirement**
- Frame selection stays explicit (a person or the current implementation chooses). Automatic selection is out of scope until criteria are approved.
- If the team later wants automation, the criteria must be deterministic, never exceed 5 frames, and be recorded in this file first.

**Why:** the TBD file says not to automate before the criteria are defined.
**Team answer:** Confirmed. As specified in `TEAM_TECHNICAL_REQUIREMENTS.md` Section 9.6, automatic frame selection is governed by five deterministic lifecycle milestone triggers:
1. **First Suspicious:** Captured at first window where $C \ge 40$ or initial positive YOLO detection.
2. **First Confirmed:** Captured at the window where the 3-consecutive-window check completes ($C \ge 65$, $\text{support} \ge 2$, transition to `CONFIRMED`).
3. **Peak Severity:** Captured at the timestamp when calculated severity $R$ reaches its peak.
4. **Arrival:** Captured when responder status transitions to `ARRIVED`.
5. **Resolution:** Captured when incident status transitions to `RESOLVED` / `CONCLUDED`.

Manual operator snapshot selection is also supported up to the hard ceiling of 5 frames (`MAX_ANNOTATED_FRAMES_PER_INCIDENT = 5`). Attempting to add a 6th frame raises `EvidenceLimitReached` without replacing or overwriting existing evidence.

---

## Affected parts (please verify in the repo)
- Evidence storage module, frame metadata table (`app/evidence/store.py`, `app/evidence/service.py`)
- Purge job and Admin purge action, audit events (`app/evidence/router.py`, `app/events/repository.py`)
- Incident detail UI (frame viewer in `frontend/src/pages/OperatorIncidentPage.tsx`)
- `SOURCE_TBD_REQUIREMENTS.md` section 9, `TEAM_CHANGE_LOG.md`
