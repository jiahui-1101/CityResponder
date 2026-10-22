# Frontend Data-Flow Audit

## Verified paths

- Authentication uses `/api/auth/login` and `/api/auth/me`; all four roles redirect correctly.
- Production pages use backend APIs rather than mock datasets.
- Operator overview reads system health, real sensor projections, actuator ACK projections, perception freshness/snapshot, incidents, routes, and recent immutable events.
- Incident pages use backend projections/history/evidence and submit Confirm/Reject/Cancel to the operator-decision endpoint.
- Firefighter response reads incidents, routes, actuator projections, and the real shared annotated camera frame.
- Planner reads area-risk ranking, factors, history, and incident/event data.
- Admin reads governance, candidates, versions, audit events, and user administration.
- Live events trigger debounced authoritative REST refreshes. Background refresh retains last known data and surfaces updating/error state.
- Actuator completion is derived from persisted ACK projection; the UI does not synthesize an ACK.
- The WebSocket token is no longer exposed in the URL.

## Missing or incomplete proposal paths

- **FRONTEND_GAP / BACKEND_GAP:** Start Response, Manual Stop, and Restore Normal operator lifecycle endpoints/actions.
- **FRONTEND_GAP / BACKEND_GAP:** Firefighter En Route, Arrived, Completion Requested, preliminary outcome, probable cause, notes, and inspection request.
- **FRONTEND_GAP / BACKEND_GAP:** Operator verification/return of responder outcome and final incident closure.
- **FRONTEND_GAP / BACKEND_GAP:** Planner inspection queue and CSV export.
- **FRONTEND_GAP:** Planner provides rankings/factors but not the promised geographic risk map.
- **FRONTEND_GAP / BACKEND_GAP:** Admin calibration candidate reject and password re-entry for activation/rollback.
- **FRONTEND_GAP:** Admin does not provide an interactive camera ROI calibration workflow or full device configuration editor.
- The proposal route names (`/command`, `/responder`, `/planner`) differ from implementation routes (`/`, `/response`, `/risk`); the role redirect validator verifies the implemented routes only.

## State and failure semantics

- Empty, loading, and API-error states exist across current pages.
- Background failures retain last known values rather than substituting zero/normal data.
- Camera frames remain visible when temporarily unavailable and are labelled stale when older than 1.5 seconds.
- Route version and no-safe-route information are represented from backend projections.

The missing lifecycle paths are critical to the requested judge rehearsal and block deployment readiness.
