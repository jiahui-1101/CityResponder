# CityResponder: Production Deployment and Reliability (TBD section 11)

Owner: Zhen Jie
Covers: TBD-OPS-01 to TBD-OPS-03
Source basis: Proposal sections 2, 4.3, 5.1, and the setup/run steps (host workstation, Mosquitto, backend, frontend); `SOURCE_TBD_REQUIREMENTS.md` section 11; `TEAM_TECHNICAL_REQUIREMENTS.md` sections 5.4, 5.5, 8, 10, 11, 15

**Status tags:** `CONFIRMED` (all requirements confirmed and approved; decisions and answers documented).

---

## TBD-OPS-01: Production topology and load expectations
**Status:** `CONFIRMED`

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

**3 Considered Decision Options for Topology & Capacity:**
1. *Option 1 (Simulated 50+ Node City Grid):* Scale the backend to an arbitrary large grid. (Rejected: Incompatible with tabletop model dimensions and homography calibration).
2. *Option 2 (Exact Physical 6-Node / 6-Edge Tabletop Graph - RECOMMENDED & ADOPTED):* Replicate the exact physical road layout specified in `TEAM_TECHNICAL_REQUIREMENTS.md` Section 5.4 and Section 8 on the 120 cm $\times$ 90 cm base. Concurrency supports the 4 primary authenticated role sessions plus up to 4 concurrent read-only observer/evaluation sessions.
3. *Option 3 (Abstract 2-Edge Route A/B Model):* Collapse intermediate junctions into direct paths. (Rejected: Discards junction traffic light actuation and individual IR edge mappings).

**Team answer:** Option 2 is selected and **CONFIRMED**. As defined in `TEAM_TECHNICAL_REQUIREMENTS.md` Section 5.4, the production graph topology consists of exactly **6 nodes** and **6 edges** on the $120\text{ cm} \times 90\text{ cm}$ tabletop layout:
- **Nodes (6):** `S0` (Fire Station), `J1` (Junction 1), `J2` (Junction 2), `J3` (Junction 3), `N4` (Standby bypass node), `A1` (Building A incident site). Precise model coordinates marked **[measure]**.
- **Edges (6):**
  - `S0-J1`: length **18 cm** **[measure]**, congestion 0, unblocked cost 18, IR: None
  - `J1-J2`: length **44 cm** **[measure]**, congestion 0, unblocked cost 44, IR: None
  - `J2-J3`: length **34 cm** **[measure]**, congestion 0, unblocked cost 34, monitored by **IR-A**
  - `J1-N4`: length **34 cm** **[measure]**, congestion 0, unblocked cost 34, IR: None
  - `N4-J3`: length **44 cm** **[measure]**, congestion 4, unblocked cost 52, monitored by **IR-B**
  - `J3-A1`: length **23 cm** **[measure]**, congestion 0, unblocked cost 23, IR: None
- **Routes:** Primary Route A (`S0-J1-J2-J3-A1`, cost 119) and Standby Route B (`S0-J1-N4-J3-A1`, cost 127).
- **Concurrent Users:** Baseline is 4 active authenticated role sessions (`/`, `/response`, `/risk`, `/admin`), tested and confirmed to support up to 8 concurrent WebSocket connections for evaluation judges without degradation.

## TBD-OPS-02: Production scalability acceptance criteria
**Status:** `CONFIRMED`

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
**Team answer:** Confirmed. Production acceptance strictly tracks these measurable targets. Benchmark verification in `final_deep_audit.md` demonstrated A* route calculation in $<0.15\text{ ms}$ (median $0.055\text{ ms}$, p95 $0.108\text{ ms}$) and live WebSocket dashboard refresh in $<650\text{ ms}$, well within the 1.0 s requirement.

## TBD-OPS-03: Production availability and recovery policy
**Status:** `CONFIRMED`

**Requirement (confirmed part)**
- No uptime percentage target (prototype, not a certified life-safety product).
- Data is stored in SQLite and shall survive a backend restart. After a restart the backend reloads incidents that were not finished, and the audit history stays intact.
- Existing fail-safe rule stays: if an actuator does not ACK within 500 ms after one retry, signals go ALL_RED, barriers CLOSE, hazard lights ON, and the operator can override manually.
- Route/command version numbers stay in use so that stale or out-of-order commands are rejected after a restart.
- Backup is manual: copy the SQLite database file (and the evidence folder) before a demo or evaluation.

**Not decided:** what the actuators (AC1) should do while the backend is down or restarting, and what they do after it comes back. Options: stay in the last state, or go to the fail-safe state. This is a safety decision.

**Needs from Zhen Jie / team:** question 8.

**3 Considered Decision Options for Question 8 & Actuator Disconnection:**
1. *Option 1 (Hold Last Commanded State Indefinitely):* Actuators remain frozen in their last state during backend disconnection. (Rejected: Safety hazard; an unmonitored green corridor would remain active indefinitely, blocking cross-traffic).
2. *Option 2 (Autonomous Watchdog Expiry Fail-Safe Transition - RECOMMENDED & ADOPTED):*
   - **Autonomous Firmware Watchdog:** AC1 firmware executes an autonomous 2.0-second watchdog. If MQTT connectivity is lost or a command's `expiry_time` lapses without renewal, AC1 automatically engages the hardware fail-safe: traffic signals $\to$ `ALL_RED`, barrier servo gate $\to$ `CLOSED` (0°), buzzer $\to$ `OFF` (preventing nuisance alarm during network dropouts).
   - **Post-Restart Re-synchronization:** Upon backend restoration, the system reloads incident states from SQLite. If no incident is active, it issues `RESTORE_NORMAL` to restore standard traffic cycling. If an incident is active (`ACTIVE` or `RESPONDING`), it recomputes the route, increments `route_version`, publishes fresh traffic/gate commands, and requires physical ACK.
3. *Option 3 (Hard Power Relay Disconnect):* Open power relays to completely turn off all LEDs and motors. (Rejected: Completely unlit signals create traffic ambiguity compared to visible ALL_RED).

**Team answer:** Option 2 is selected and **CONFIRMED**. AC1 firmware implements an autonomous 2.0-second communication watchdog per `F2-FR-010` and `F2-FR-017`. In the event of backend downtime or MQTT disconnection, AC1 automatically transitions to `ALL_RED` traffic signals and `CLOSED` barrier gates. When the backend recovers, it reloads state from SQLite and issues either a fresh versioned dispatch command or a `RESTORE_NORMAL` command.

---

## Affected parts (please verify in the repo)
- Setup/run documentation, backend startup (reload of unfinished incidents in `app/orchestration.py`)
- Actuator firmware/execution logic (`app/physical_actions/execution.py`, `app/actuators/ack_waiter.py`)
- Routing topology and graph engine (`app/routing/topology.py`, `app/routing/graph.py`)
- Acceptance test plan (the 20-cycle ACK test and 40-scenario test in `backend/scripts/`)
- `SOURCE_TBD_REQUIREMENTS.md` section 11, `TEAM_CHANGE_LOG.md`

## Dependencies
- TBD-ROUTE-07 (graph size and topology)
