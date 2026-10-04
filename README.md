# CityResponder

CityResponder is a tabletop urban emergency-response prototype that connects multimodal sensing, computer vision, risk-aware routing, physical traffic coordination, and role-based operations.

It follows one loop:

**Understand → Respond → Learn**

> **Evidence boundary:** the physical runtime is a local/hybrid prototype. The public showcase is a static interface and evidence tour; it does not pretend to be connected to the local camera, Mosquitto broker, or ESP32 nodes.

## Why CityResponder

Emergency response can fail when sensor evidence is fragmented, roads become blocked, or traffic infrastructure is not coordinated. CityResponder combines physical telemetry, overhead vision, operator decisions, routing, actuation, and post-incident learning in one auditable workflow.

## Key Features

- Multimodal fire verification using DHT22, raw/provisional MQ-2 telemetry, IR route sensors, a manual button, and camera evidence.
- Frozen YOLOv8n Detection V2 for `fire`, `smoke`, and `person`.
- Frozen YOLOv8n-seg Segmentation V1 for `road_obstacle` and `pothole`.
- Confidence/evidence fusion, severity assessment, and a first-frame person-in-hazard Critical override.
- Hazard-aware A* routing with PRIMARY/STANDBY route semantics and IR/camera conflict handling.
- Separate ESP32 SN1 sensor and AC1 actuator nodes communicating through Wi-Fi, the local backend, and MQTT.
- Route-aware traffic commands, correlated actuator ACKs, buzzer control, and safe-default handling.
- Operator, Firefighter, Planner, and Admin dashboard workflows.
- Event history, evidence retention, verified outcome feedback, area-risk intelligence, and governed calibration surfaces.

## System Architecture

```text
SN1 sensors + USB webcam
          │ MQTT / local camera runtime
          ▼
Mosquitto → FastAPI event/fusion/severity/routing engine → SQLite events
                                      │
                                      ├── WebSocket + REST → React dashboard
                                      └── MQTT commands → AC1 traffic/buzzer/gate
```

The production-like prototype is intentionally local/hybrid:

- **SN1:** sensor node (MQ-2 AO, DHT22, IR1, IR2, button).
- **AC1:** actuator node (two traffic-light groups, buzzer, servo signal).
- **Backend:** FastAPI on the demo workstation, with SQLite and Mosquitto locally.
- **Camera:** board-facing USB webcam on the same workstation.
- **Frontend:** React, TypeScript, Vite, and authenticated WebSocket updates.

## Understand → Respond → Learn

1. Understand: combine physical telemetry, Detection V2, Segmentation V1, and historical risk.
2. Respond: assess severity, select a safe A* route, coordinate PRIMARY/STANDBY traffic, and expose command/ACK state.
3. Learn: preserve event/evidence history, collect verified outcomes, update area-risk views, and govern calibration changes.

## AI & Vision

Detection V2 and Segmentation V1 are frozen tabletop-pilot models. Documented held-out test evidence includes:

- Detection V2 overall: precision `0.9525`, recall `0.8488`, mAP50 `0.8970`, mAP50-95 `0.4102`.
- Segmentation V1 test mask: precision `0.9872`, recall `1.0000`, mAP50 `0.9950`, mAP50-95 `0.6252`.
- Webcam benchmark: camera index `1`, actual `1920x1080`, locked crop `(340,80,1080,840)`, 640 inference input, 100 valid frames, 0 failed reads, measured end-to-end segmentation rate `9.40 FPS`.

These are controlled tabletop results, not a claim of real-world generalization. Negative-scene false detections remain part of the preserved validation evidence.

## Hardware

The authoritative wiring specification is [the hardware reference](docs/hardware/CityResponder_GPIO_Breadboard_Reference.md). Current route-aware mapping:

| Node | Function | GPIO |
|---|---|---:|
| SN1 | MQ-2 AO through final 20k upper / 10k lower divider | 34 |
| SN1 | DHT22 DATA | 4 |
| SN1 | IR1 / MAIN route | 32 |
| SN1 | IR2 / ALTERNATE route | 33 |
| SN1 | Push button, `INPUT_PULLUP` | 27 |
| AC1 | PRIMARY traffic R/Y/G | 14 / 13 / 23 |
| AC1 | STANDBY traffic R/Y/G | 25 / 26 / 27 |
| AC1 | Buzzer SIG | 19 |
| AC1 | Servo signal | 18 |

The main/PRIMARY route is preferred. A blocked primary route transitions through ALL_RED before the standby route is selected. The servo is associated with alternate-route safe-entry behavior.

## Dashboard Roles

**Operator** — live annotated camera, evidence/fusion/severity, route, command/ACK, Confirm/Reject/Cancel, Start Response, and Manual Stop.

**Firefighter** — mobile route view with live camera, CURRENT ROUTE, nodes, cost, version, blocked-edge/reroute reason, traffic corridor, and En Route/Arrived/Resolved controls.

**Planner** — area risk, factor explanations, incident history, inspection queue/actions, risk ranking, and CSV export.

**Admin** — system/device health, camera/AI health, calibration governance, approval/rollback, and audit views.

## Demo Flow

1. Operator sees healthy telemetry and the annotated camera.
2. Fire/person evidence appears and the incident is confirmed.
3. Severity and the A* PRIMARY route are shown.
4. The PRIMARY traffic corridor activates.
5. IR blockage triggers a recorded ALL_RED transition and reroute evidence.
6. The STANDBY corridor activates when the route-aware command is available.
7. Firefighter receives the updated route and progresses En Route → Arrived → Resolved.
8. Verified outcome data feeds Planner risk/history workflows.
9. Admin reviews health, calibration, and audit state.

Gate movement is not represented as complete in this flow; it remains deferred pending servo replacement and validation.

## Verified Results

- The original controlled validation record is preserved at `26/40 PASS`.
- A separate targeted remediation rerun passed `9/9` selected scenarios, giving a projected `35/40 = 87.5%`; this does not rewrite the original result.
- Backend test suite: `35 passed`.
- Physical AC1 traffic: PRIMARY, ALL_RED, and STANDBY corridors confirmed.
- MQTT command delivery and ACK correlation evidence exists; historical samples include ACKs above the 500 ms target, so perfect latency compliance is not claimed.
- Frontend refresh/loading remediation: PASS; typecheck, tests, and production build: PASS.
- WebSocket receipt → DOM proxy: `3.1 ms` average, `601 ms` maximum for the measured evidence set.
- Strict backend-origin → DOM latency: **UNMEASURED**.
- Camera cold-start warming: approximately `13.05 s`; the UI exposes the warming state.

Evidence is retained in `reports/final_validation/`, `reports/final_rehearsal/`, and `reports/validation/`.

## Public Showcase

The intended GitHub Pages URL is:

**https://jiahui-1101.github.io/CityResponder/**

This is a static showcase build. It contains clearly labelled public role views and recorded evidence, and never fabricates live sensor, camera, MQTT, or actuator data. GitHub Pages availability depends on repository visibility and Pages being enabled for the repository.

## Live Hardware Demo

- Frontend: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- Backend: [http://127.0.0.1:8020](http://127.0.0.1:8020)
- Health: [http://127.0.0.1:8020/health](http://127.0.0.1:8020/health)
- WebSocket: `ws://127.0.0.1:8020/ws/live?token=<JWT>`
- Mosquitto: local `localhost:1883`

The live demo requires the local FastAPI backend, Mosquitto, USB webcam, SN1, and AC1. Local credentials and `.env.local` overrides are intentionally not committed.

## Getting Started

Prerequisites: Python 3.11+, Node.js 20+, npm, a local Mosquitto broker, and (for the hardware demo) the configured USB webcam and ESP32 nodes.

```powershell
git clone https://github.com/jiahui-1101/CityResponder.git
Set-Location CityResponder

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Set local values in the uncommitted `.env` as needed, including `PORT=8020`, MQTT credentials, and the local model paths. Never commit `.env`, `.env.local`, passwords, or private keys.

Start the local runtime in separate terminals:

```powershell
# Terminal 1 — Mosquitto
mosquitto -c mosquitto-dev.conf

# Terminal 2 — backend
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8020
Pop-Location

# Terminal 3 — frontend
Push-Location frontend
npm ci
npm run dev
Pop-Location
```

For a production-like static showcase build, the Pages workflow sets `VITE_PUBLIC_SHOWCASE=true` and `VITE_BASE_PATH=/CityResponder/`. Local development keeps the authenticated application and local API configuration.

## Repository Structure

```text
backend/       FastAPI application, scripts, and tests
frontend/      React/Vite dashboard and public showcase build
firmware/      SN1 and AC1 ESP32 firmware
datasets/      Detection and segmentation pilot data
docs/          Hardware source-of-truth documentation
reports/       Validation, QA, model, and rehearsal evidence
*.md           Feature specifications, dispatch policy, and audit log
```

## Known Evidence Boundaries

- **MQ-2:** replacement sensor produces raw nonzero ADC values, but formal 24-hour burn-in/calibration is not completed. Production fire thresholds are not claimed as physically validated.
- **Servo/gate:** `DEFERRED_PENDING_SERVO_REPLACEMENT`; no final gate-control sign-off is claimed for the currently unsuitable continuous-rotation unit.
- **Vision:** Detection V2 and Segmentation V1 are tabletop prototype evidence; real-world generalization is not established.
- **Latency:** the WebSocket receipt → DOM proxy is measured; strict backend-origin → DOM latency is unmeasured.
- **Camera:** the locked native source and crop are documented, with a measured cold-start warming period.

## Technical Documentation & Evidence

- [Dispatch matrix](dispatch.md)
- [Routing specification](routing.md)
- [Severity specification](severity.md)
- [Fire fusion specification](fire_fusion.md)
- [Adaptive calibration policy](adaptive_calibration.md)
- [Deployment reliability](deployment_reliability.md)
- [Hardware source of truth](docs/hardware/CityResponder_GPIO_Breadboard_Reference.md)
- [Team change log](TEAM_CHANGE_LOG.md)
- [Final rehearsal reports](reports/final_rehearsal/)
- [Final validation reports](reports/final_validation/)

## Team / Project Nexus

CityResponder is developed as a Project Nexus prototype. The repository keeps implementation, hardware evidence, validation reports, and known limitations together so a reviewer can distinguish recorded results from future work.
