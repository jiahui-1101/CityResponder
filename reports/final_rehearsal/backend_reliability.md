# Backend Reliability Audit

## Runtime architecture

The defensible demo topology is local/hybrid: SN1 and AC1 communicate over Wi-Fi with a local Mosquitto broker; FastAPI consumes MQTT, persists immutable events in local SQLite, publishes live updates over an authenticated WebSocket, and serves the React/Vite UI. The USB camera is owned by one shared local vision worker. A cloud-only backend cannot directly access the local USB camera or the isolated hardware MQTT network.

## Validation results

- Python compile check: PASS.
- Backend unit discovery: 27/27 PASS.
- Targeted remediation coverage: FV-028, FV-029, FV-031, FV-032, FV-033, FV-034, FV-036, FV-037, FV-039 PASS.
- Dispatch validator: PASS.
- Fusion validator: PASS (required UTF-8 console mode on Windows; the initial failure was console encoding, not a policy assertion).
- Severity policy and orchestration validators: PASS.
- Controlled software E2E (`--no-write`): PASS for routable, no-safe-route, ACK timeout/retry, idempotent retry, and safe-default fixtures. It explicitly uses mock ACKs and is not real-hardware evidence.
- Requirements validator: role redirects 4/4 PASS; prohibited endpoint matrix 24/24 PASS; immutable store, operator decision, routing safety, actuator safety, privacy, area risk, calibration governance, and recorded live-latency checks PASS.
- Authenticated WebSocket handshake: PASS; access token is not placed in the URL and the client waits for `connection_authenticated`.

## Reliability boundaries

- Real hardware evidence records 20/20 command cycles receiving ACKs, but three latency samples exceeded the 500 ms target.
- Current final-validation source data remains 26 PASS / 14 FAIL; nine targeted remediations project 35/40 (87.5%), but the full 40-scenario suite has not been rerun and physically re-evidenced.
- Vision produced false person and road-obstacle outputs in prior negative-scene runs. Frozen models were not retrained in this pass.
- The replacement positional servo has not been installed and validated; complete gate/failsafe evidence is therefore incomplete.
- Route-aware AC1 production firmware builds successfully but still requires flash plus physical STANDBY-green and stale-route verification.
- MQ-2 remains raw/provisional; formal burn-in/calibration is not passed.

## Stability observation

A short integrated software observation completed without HTTP errors or backend exceptions. API latency remained low while cached live frames were requested. This is not an extended physical soak, and long-duration camera/MQTT/device stability remains unproven.
