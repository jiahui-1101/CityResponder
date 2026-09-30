# Step 18 response timing

Controlled software routing benchmark using deterministic graph fixtures and mock ACKs.

## Routing
- INITIAL_SAFE_ROUTE: n=50, median=0.062 ms, p95=0.110 ms, max=0.135 ms, within 1s=50, exceeds 1s=0
- REROUTE: n=50, median=0.057 ms, p95=0.101 ms, max=0.117 ms, within 1s=50, exceeds 1s=0
- NO_SAFE_ROUTE: n=50, median=0.022 ms, p95=0.044 ms, max=0.047 ms, within 1s=50, exceeds 1s=0

## Response breakdown
- normal_ack_path: status=PASS, routing=0.43020001612603664 ms, execution=1027.090700052213 ms, total=1050.088 ms
- ack_timeout_path: status=PASS, routing=0.3968999953940511 ms, execution=1022.702099988237 ms, total=1040.476 ms
- no_safe_route_path: status=PASS, routing=0.2899999963119626 ms, execution=4.841400019358844 ms, total=19.368 ms

The 1000 ms ALL_RED transition is intentional and excluded from routing latency. Mock ACK timings are not real ESP32 performance. Production topology remains TBD_SOURCE.
