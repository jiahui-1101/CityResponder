# Deployment Readiness

## Gate result

`GO_FOR_DEPLOYMENT = NO`

No deployment, commit, pull/rebase, or push was performed in this pass.

## Smallest remaining blockers

1. Physically validate the route-aware AC1 STANDBY-green transition and stale route-version rejection on the current hardware.
2. Install and validate the replacement positional servo; complete gate and full failsafe evidence (still intentionally outside this pass).
3. Complete interactive browser QA with a working browser-control surface; the local computer-use helper was unavailable in this pass.
4. Rerun the full 40-scenario controlled validation only when the remaining physical/evidence boundaries are ready.
5. Prove strict backend-origin-to-DOM camera freshness if that acceptance metric remains mandatory; the measured 900-event value is a WS-receipt→DOM proxy.
6. Complete an extended integrated soak and recheck memory/camera/MQTT/WebSocket stability.

## Deployment topology

The appropriate demo topology is local/hybrid. The FastAPI backend, SQLite database, Mosquitto broker, shared vision process, and React frontend must run on the local Windows host/network that can access the USB camera and ESP32 nodes. A cloud deployment must not be substituted for that host because it cannot access local USB/MQTT hardware without additional infrastructure.

## Known evidence boundaries

- MQ-2 formal 24-hour burn-in/calibration: not passed.
- Vision generalization: limited to the captured tabletop data; false positives exist in negative-scene validation.
- Servo/gate and complete failsafe: deferred pending replacement hardware.
- Interactive browser QA: blocked by local browser-control helper failure in this run.

Final status: **NOT_READY**. Software lifecycle and planner inspection/export remediation is present, but physical STANDBY-green evidence and interactive browser proof remain open.
