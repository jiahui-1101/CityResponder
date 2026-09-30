# Step 18 response timing

Controlled software routing benchmark using deterministic graph fixtures and mock ACKs.

## Routing
- INITIAL_SAFE_ROUTE: n=50, median=0.055 ms, p95=0.108 ms, max=0.123 ms, within 1s=50, exceeds 1s=0
- REROUTE: n=50, median=0.081 ms, p95=0.103 ms, max=0.128 ms, within 1s=50, exceeds 1s=0
- NO_SAFE_ROUTE: n=50, median=0.035 ms, p95=0.051 ms, max=0.084 ms, within 1s=50, exceeds 1s=0

## Response breakdown
- normal_ack_path: status=PASS, routing=0.30509999487549067 ms, execution=1010.9227999928407 ms, total=1033.461 ms
- ack_timeout_path: status=PASS, routing=0.3000000142492354 ms, execution=1033.3375000045635 ms, total=1046.891 ms
- no_safe_route_path: status=PASS, routing=0.2747999969869852 ms, execution=5.598700023256242 ms, total=19.539 ms

The 1000 ms ALL_RED transition is intentional and excluded from routing latency. Mock ACK timings are not real ESP32 performance. Production topology remains TBD_SOURCE.
