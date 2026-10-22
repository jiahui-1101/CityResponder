# Proposal → Implementation Traceability

Sources inspected: `PROPOSAL_SUBMISSION_REQUIREMENTS.md`, `TEAM_TECHNICAL_REQUIREMENTS.md`, current backend routes/services, current frontend routes/pages, hardware reference, validation evidence, and team change log.

Status meanings: **PASS** = implemented and evidenced; **PARTIAL** = meaningful implementation exists with a stated gap; **GAP** = promised demo path is absent; **PENDING_HW** = software exists but final physical evidence is incomplete.

## Feature 1 — Understand

| Proposal claim | Backend implementation | Frontend representation | Physical representation/evidence | Status |
|---|---|---|---|---|
| MQ-2 smoke/gas | Raw SN1 MQTT ingestion and freshness | Raw/provisional telemetry and health | Replacement module produces nonzero ADC; formal burn-in/calibration not passed | PARTIAL |
| DHT22 | SN1 telemetry ingestion/freshness | Sensor status/value | Real readings previously observed | PASS |
| Manual button | SN1 telemetry ingestion | Sensor status/value | INPUT_PULLUP HIGH→LOW→HIGH verified | PASS |
| Overhead camera | Single shared integrated pipeline | Real annotated Operator/Firefighter view | Fixed 1920×1080 camera and locked crop | PARTIAL: freshness/cold start |
| Fire/smoke/person detection | Frozen Detection V2 integration | Boxes, labels, confidence when present | Real model output; negative-scene false persons recorded | PARTIAL |
| Road obstacle/pothole segmentation | Frozen Segmentation V1 integration | Polygons, labels, confidence when present | Real model output; negative-scene false obstacle evidence recorded | PARTIAL |
| Evidence/confidence fusion | S/T/V/H services and three-window decision | Incident/evidence projections | Controlled validators PASS | PASS with policy boundaries |
| Support count | Fusion supporting-channel policy | Evidence panel data | Validator PASS | PASS |
| Three-window persistence | Confirmation sequence/window | Incident evidence | Validator PASS | PASS |
| Severity/person override/reasons | Severity calculator, critical override, reason data | Incident projection/badges | Validator PASS | PASS |
| Operator Confirm | Transactional first-writer action with severity floor | Incident action UI | Concurrency tests PASS | PASS |
| Operator Reject/Cancel | Valid release sequence, immutable audit | Incident action UI | Targeted tests PASS | PASS |

## Feature 2 — Respond

| Proposal claim | Backend implementation | Frontend representation | Physical representation/evidence | Status |
|---|---|---|---|---|
| Severity dispatch matrix | Authoritative LOW/MEDIUM/HIGH/CRITICAL policy | Projected incident/action data | Dispatch validator PASS | PASS |
| A* route/blocked road/cost | Edge safety, costs, active graph, A* | Route details and history | Controlled route tests PASS | PASS |
| PRIMARY/STANDBY and route_version | Route-aware corridor contract and stale rejection | Route/corridor/version state | PRIMARY observed; STANDBY final physical verification pending | PENDING_HW |
| ALL_RED transition/reroute | Sequenced safety transition before corridor | Route/actuator timeline | ALL_RED physically observed | PARTIAL |
| Traffic corridor | MQTT action mapping | Actual ACK projection | Corrected group mapping; final route-aware flash pending | PENDING_HW |
| Buzzer | ON/OFF and MEDIUM pulse parameters | Actuator projection | ON/OFF physically verified; final Moderate pulse not reverified | PARTIAL |
| Gate | OPEN/CLOSE actions and safe-default CLOSE | Actuator projection | Current servo is continuous-rotation; replacement not installed | PENDING_HW |
| MQTT/ACK/timeout/retry | Command service, exact ACK correlation, 500 ms timeout, idempotent retry | ACK state from backend | 20/20 cycles ACK; 3 latency samples >500 ms | PARTIAL |
| Safe default/NO_SAFE_ROUTE | ALL_RED + gate CLOSE + buzzer ON; auto dispatch inhibited | No-safe-route state | Traffic/buzzer observed; gate incomplete | PENDING_HW |
| Operator Start Response/Manual Stop/Restore | No complete promised lifecycle API | No controls | Not demonstrated | GAP / FRONTEND_GAP |
| Firefighter En Route/Arrived/Completion | Required endpoint absent | Required controls absent | Not demonstrated | GAP / FRONTEND_GAP |

## Feature 3 — Learn

| Proposal claim | Backend implementation | Frontend representation | Evidence | Status |
|---|---|---|---|---|
| Incident history/audit | Immutable event store and projections | History/incident pages | Immutable-store validator PASS | PASS |
| Verified outcome/probable cause | Required responder feedback and operator verification APIs absent | Forms absent | Not demonstrated | GAP / FRONTEND_GAP |
| Area-risk ranking/factors | F/R/E/A/M calculator, 180-day window | Ranking, factor detail, history | Contract validator PASS | PARTIAL: semantics/mapping unresolved |
| Inspection queue | Endpoint absent | UI absent | Not demonstrated | GAP / FRONTEND_GAP |
| CSV export | Endpoint absent | UI absent | Not demonstrated | GAP / FRONTEND_GAP |
| Calibration preview/bounds | Candidate/version schemas and bounded weights | Candidate/governance UI | Governance validator PASS | PASS for preview |
| Admin approval/activation/rollback | Protected endpoints and immutable version events | Approve/activate/rollback controls | Validator PASS | PARTIAL: no reject/re-auth |
| Calibration audit | Immutable events | History/Admin data | Available | PASS |

## Roles

| Role | Current route | Implemented | Critical gap | Status |
|---|---|---|---|---|
| Emergency Operator | `/` and `/incidents` | Live overview, sensors, vision, incidents, evidence, routes, Confirm/Reject/Cancel | Start/Stop/Restore and final outcome verification/closure | PARTIAL |
| Firefighter | `/response` | Mobile-oriented incident, route, actuator, live vision | En Route, Arrived, Completion Requested, preliminary outcome/cause/inspection | GAP |
| City Risk Planner | `/risk` and `/history` | Ranking, factors, history | Inspection queue, CSV export, geographic map | PARTIAL |
| System Administrator | `/admin` | Health, users, calibration candidates/versions, approve/activate/rollback | Camera calibration UI, candidate reject, password re-entry/config editor | PARTIAL |

## Conclusion

Critical missing demo paths remain for the Firefighter lifecycle and cross-role incident closure, plus Planner inspection/export. Because those are explicit proposal claims, traceability has critical gaps and the deployment gate cannot pass.
