# CityResponder: Evidence Retention Policy (TBD section 9)

Owner: Zhen Jie
Covers: TBD-PRIV-01 to TBD-PRIV-04
Source basis: `SOURCE_TBD_REQUIREMENTS.md` section 9, proposal sections 2 and 5.1 (immutable audit history, prototype scope)

**Status tag:** `APPROVED` = decided and approved by Zhen Jie as owner of this section. No separate team sign-off was requested. The proposal does not fully define these items, so they are design decisions; if the proposal authors had a specific meaning, theirs should replace it. Each decision is recorded in `TEAM_CHANGE_LOG.md`.

**Already fixed by the source (as written in the TBD file)**
- No permanent continuous video storage.
- Maximum 5 annotated frames per incident.

Note: I could not find the "5 annotated frames" sentence in the proposal text itself, only in the TBD file. Please confirm where it comes from.

**General rules (APPROVED)**
- PRIV-G1: The system shall never record or keep a continuous video stream. Only individual annotated frames of an incident may be stored.
- PRIV-G2: Not more than 5 frames per incident.
- PRIV-G3: Each stored frame shall have a record with incident id, capture time, who selected it, and a SHA-256 hash of the file. The hash lets the audit history show that a frame existed even after the file is purged.

---

## TBD-PRIV-01: Retention duration
**Status:** `APPROVED`

**Requirement**
- Retained incident frames are kept for 180 days, counted from the incident's start time.
- The duration is a configuration value, changed only through change-control (see admin_configuration.md).

**Why:** decided by Zhen Jie for auditability in a real-life situation. It also matches the 180-day Area Risk window, so the evidence behind any incident that still counts in the risk score can be reviewed.

## TBD-PRIV-02: Deletion and purge policy
**Status:** `APPROVED`

**Requirement**
- Automatic purge: a scheduled job runs once per day and deletes frame files whose incident started more than 180 days ago.
- Manual purge: System Administrator only, with a written reason. It may delete frames earlier than 180 days.
- Purging deletes only the image files. The incident record, scores, detections and frame metadata (including the hash) stay in the append-only history.
- Every purge appends an audit event: who (or "system"), when, how many frames, and the reason.

## TBD-PRIV-03: Production evidence storage backend
**Status:** `APPROVED`

**Requirement**
- Frames are stored as image files in a local folder on the host workstation. The database stores only the file path and metadata.
- Frames are served only through the authenticated backend (signed JWT, role check). The folder is never exposed directly.
- Production-grade storage (encryption at rest, off-site backup, access review) is out of scope for this prototype.

**Why:** the proposal states this is a tabletop prototype and not a certified life-safety product.

## TBD-PRIV-04: Automatic frame-selection policy
**Status:** `APPROVED`

**Requirement**
- Frame selection stays explicit (a person or the current implementation chooses). Automatic selection is out of scope until deterministic criteria are defined and recorded.
- If the team later wants automation, the criteria must be deterministic, never exceed 5 frames, and be recorded in this file first.

**Why:** the TBD file says not to automate before the criteria are defined.

---

## Affected parts (please verify in the repo)
- Evidence storage module, frame metadata table
- Purge job and Admin purge action, audit events
- Incident detail UI (frame viewer)
- `SOURCE_TBD_REQUIREMENTS.md` section 9, `TEAM_CHANGE_LOG.md`
