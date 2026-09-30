# CityResponder

CityResponder is a FastAPI + SQLite + MQTT backend with a React/Vite/TypeScript dashboard for sensor/vision evidence, immutable audit history, incident decisions, routing, dispatch and actuator integration.

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer and npm
- Eclipse Mosquitto running on `localhost:1883` for MQTT flows

Mosquitto is an external development dependency and is not bundled with this repository.

## Setup

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm install
Pop-Location
```

Review `.env` before starting. The development seed password and account emails are configured there; change `JWT_SECRET_KEY` and development credentials before using the system outside local development. Do not commit `.env`.

## Start the local stack

Start Mosquitto in a separate terminal:

```powershell
mosquitto -v
```

Start the backend on port `8010`:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

Start the frontend in another terminal:

```powershell
Push-Location frontend
npm run dev
```

The dashboard is served at [http://localhost:5173](http://localhost:5173). It uses `http://localhost:8010` by default; set `VITE_API_BASE_URL` when the backend is hosted elsewhere before starting Vite.

Check backend liveness at [http://localhost:8010/health](http://localhost:8010/health).

## Development accounts

On an empty database, the backend seeds one local development user for each role using the values in `.env`:

- `OPERATOR` — `DEV_OPERATOR_EMAIL`
- `FIREFIGHTER` — `DEV_FIREFIGHTER_EMAIL`
- `RISK_PLANNER` — `DEV_RISK_PLANNER_EMAIL`
- `ADMIN` — `DEV_ADMIN_EMAIL`

All seeded accounts use `DEV_SEED_PASSWORD`. These are local development defaults only.

## Optional controlled development flows

Run these from the repository root with the backend import path set by entering `backend`:

Terminal A — keep the mock actuator running:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m scripts.mock_actuator
```

Terminal B — publish and inspect one controlled flow:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m scripts.mock_sensor_publisher --once
..\.venv\Scripts\python.exe -m scripts.send_mock_command
..\.venv\Scripts\python.exe -m scripts.inspect_events --limit 20
Pop-Location
```

The mock publisher/actuator and validation scripts are controlled development fixtures. Their messages are not physical hardware evidence and are not shown as real hardware status by the production UI.

## Verification

Focused checks:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m compileall -q .
..\.venv\Scripts\python.exe -m scripts.validate_requirements --output ..\reports\validation\step16_result.json
..\.venv\Scripts\python.exe -m scripts.validate_e2e_cycle
..\.venv\Scripts\python.exe -m scripts.benchmark_response_timing
Pop-Location

Push-Location frontend
npm run typecheck
npm run build
Pop-Location
```

Validation reports are under `reports/validation/`. Real camera/model acceptance, physical ESP32/AC1 ACK reliability, and source-defined production policies remain explicitly marked `NOT_RUN_EXTERNAL` or `TBD_SOURCE` in the final audit.

## Repository safety

Runtime databases, `.env`, virtual environments, caches, model weights, generated frontend output and evidence files are ignored by Git. Keep secrets and local runtime data out of commits.
