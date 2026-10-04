# Final Demo Rehearsal Results

## Outcome

Full judge-style rehearsal: **FAIL / NOT COMPLETED**.

This pass validated software and runtime paths without fabricating physical observations. It did not repeat physical sensor/actuator actions because the route-aware AC1 firmware has not been flashed for final verification and the replacement positional servo is pending.

## Evidence carried forward

- SN1 previously demonstrated Wi-Fi/MQTT, DHT22, IR1, IR2, and button operation. Replacement MQ-2 restored nonzero analog output, but its values remain provisional.
- PRIMARY corridor, ALL_RED, traffic OFF, and buzzer ON/OFF were previously physically observed.
- Hardware evidence contains 20 command cycles: 14 completed, 2 completed non-servo, 3 failed, and 1 interrupted. All 20 published cycles received ACKs; three latency samples exceeded 500 ms.
- Current frozen vision failed negative-scene cases through false person/road-obstacle outputs.
- Nine targeted software failures now pass focused regression tests, projecting 35/40 controlled scenarios (87.5%); a complete rerun has not replaced the original 26/40 evidence.

## Unfinished rehearsal steps

1. Flash route-aware AC1 production firmware.
2. Physically confirm PRIMARY green, ALL_RED transition, STANDBY green, and stale route-version rejection.
3. Install and validate a positional replacement servo unloaded, calibrate it, and repeat gate/safe-default checks.
4. Complete the missing Firefighter, Operator closure, Planner inspection/export, and Admin governance paths.
5. Repeat the 40 controlled scenarios and the full four-role judge flow.
6. Run interactive desktop/laptop/mobile browser QA and a longer integrated soak.

The physical system should remain in its previously confirmed safe/normal state; that state was not re-observed in this software-only pass.
