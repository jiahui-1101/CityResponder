# CityResponder: Production Deployment and Reliability (TBD section 11)

Owner: Zhen Jie
Covers: TBD-OPS-01 to TBD-OPS-03
Source basis: Proposal sections 2, 4.3, 5.1, and the setup/run steps (host workstation, Mosquitto, backend, frontend); `SOURCE_TBD_REQUIREMENTS.md` section 11

**Status tag:** `CHOSEN` = the proposal does not fully define this item, so it is a design choice made by Zhen Jie (with Claude's help). Every item needs team sign-off and a `TEAM_CHANGE_LOG.md` entry before the real TBD file is updated. If the proposal authors had a specific meaning, theirs wins.

---

## TBD-OPS-01: Production topology and load expectations
**Status:** `CHOSEN`

**Requirement (confirmed part)**

Deployment environment (from the proposal's setup steps):
- One host workstation, Windows 10/11 or Linux, Python 3.11+, Node.js 20+.
- Eclipse Mosquitto broker on `localhost:1883`.
- FastAPI backend (Uvicorn) on `127.0.0.1:8010`, React dashboard on port `5173`.
- Two ESP32 nodes: SN1 (sensors) and AC1 (actuators), one overhead camera (720p, 1280x720 at 30 FPS).
- SQLite as the only database.

Event rates (already stated in the proposal):
- IR sampling every 200 ms.
- Object detection at 5 FPS or more, segmentation at 2 FPS or more.
- Fusion in 1-second windows.
- Freshness limits: MQ-2 2.0 s, DHT22 3.0 s, camera 1.0 s.

Users:
- Design target: up to 4 dashboard sessions at the same time (one per role: Operator, Firefighter, City Risk Planner, Administrator), each on an authenticated WebSocket.

**Not decided:** expected graph size (depends on TBD-ROUTE-07, section 5, other owner). It should be filled in once the real node and edge list is final.

**Why 4 users:** the proposal does not give a number. 4 follows from the 4 roles and is only a design target. I am about 80% sure it is reasonable, so please tell me if the demo needs more sessions (for example judges watching).

## TBD-OPS-02: Production scalability acceptance criteria
**Status:** `CHOSEN`

**Requirement**
- No scale target beyond the tabletop demo is defined, so scaling beyond one host and one model is out of scope.
- Acceptance uses only the measurable targets that the proposal already gives:
  - Routes calculated within 1 second.
  - Dashboard updates within 1 second.
  - Actuator ACK success of 95% over 20 cycles.
  - At least 85% verification correctness across at least 40 scenarios.
  - False-dispatch rate of 10% or lower.
  - Manual button alert visible on the dashboard in under 1 second.
  - Camera data fresher than 1.0 s for use in decisions.

**Why:** inventing new load numbers would be a fake value, which the TBD file forbids.

## TBD-OPS-03: Production availability and recovery policy
**Status:** `CHOSEN` (heartbeat value is an engineering choice, see below)

**Requirement**
- No uptime percentage target (prototype, not a certified life-safety product).
- Data lives in SQLite and survives a backend restart. After a restart the backend reloads unfinished incidents and the audit history stays intact.
- **Actuators go to the fail-safe state when the backend is lost** (decided by Zhen Jie): signals ALL_RED, barriers CLOSE, hazard lights ON. This is the same fail-safe the proposal already uses when an ACK fails.
- How AC1 detects that the backend is lost:
  1. The backend connects to Mosquitto with a Last Will message, so the broker announces "backend offline" immediately if the backend drops.
  2. As a backup, AC1 enters the fail-safe state if it receives no backend heartbeat for 3 seconds (heartbeat sent every 1 second, matching the 1-second fusion window). The 3 s value is my engineering choice and must be tested on the real hardware.
- Recovery: AC1 leaves the fail-safe state only when it receives a valid new command with a version number higher than any earlier one (the proposal's version number rejects stale commands). The backend does not re-send old commands on restart. Reloaded unfinished incidents are shown to the operator as needing review, and the operator re-confirms or overrides manually.
- Backup is manual: copy the SQLite database file and the evidence folder before a demo or evaluation.

---

## Affected parts (please verify in the repo)
- Setup/run documentation, backend startup (reload of unfinished incidents)
- Actuator firmware/execution logic (behavior when the backend is lost)
- Acceptance test plan (the 20-cycle ACK test and 40-scenario test)
- `SOURCE_TBD_REQUIREMENTS.md` section 11, `TEAM_CHANGE_LOG.md`

## Dependencies
- TBD-ROUTE-07 (graph size)
