# CityResponder — Hardware & External Validation Requirements

**Status:** Remaining work requiring real camera, model, IoT, actuator, or manual physical evidence.

## Change-control rule

Any change to this file, a requirement status, threshold, test method, hardware mapping, or acceptance result must also be recorded in `TEAM_CHANGE_LOG.md`. Never mark an item PASS using mock ACKs, synthetic camera output, fake dashboard data, or controlled software fixtures.

## Current boundary

The software implementation is frozen with zero software FAIL in the final deep audit. The requirements below are external acceptance work and must remain `NOT_RUN_EXTERNAL` or `BLOCKED_EXTERNAL` until real evidence exists.

## Camera and computer vision

- **HW-VIS-01 Real overhead camera:** connect the intended top-down camera and verify the production pipeline reports its real state. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-02 Full model coverage:** verify 100% of the intended tabletop smart-city model area is visible. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-03 Building A ROI:** verify real view ROI is at least `280 × 180 px`. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-04 Road width:** verify relevant real road regions are at least `120 px` wide. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-05 Real detection model:** validate custom/production `fire`, `smoke`, and `person` classes and person-in-hazard evidence. Status: `BLOCKED_EXTERNAL` until real weights are supplied.
- **HW-VIS-06 Real segmentation model:** validate `road_obstacle` and `pothole` masks and real occupancy input. Status: `BLOCKED_EXTERNAL`.
- **HW-VIS-07 Object throughput:** real YOLO detection target `>= 5 inference/s`. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-08 Segmentation throughput:** real YOLO segmentation target `>= 2 inference/s`. Status: `NOT_RUN_EXTERNAL`.
- **HW-VIS-09 Dimension accuracy:** calibrated physical dimension MAE `<= 1 cm`. Status: `NOT_RUN_EXTERNAL`.

Record model identifiers, warm-up/sample policy, measured timing, camera/device ID, calibration, frame references, and evidence paths under `reports/validation/step19/`.

## 40-scenario fire verification

- **HW-FIRE-01:** execute at least 40 controlled real fire/non-fire scenarios with ground truth, evidence channels, automatic result, operator outcome, reason codes, and false-dispatch outcome. Status: `NOT_RUN_EXTERNAL`.
- **HW-FIRE-02:** verification correctness `>= 85%`. Status: `NOT_RUN_EXTERNAL`.
- **HW-FIRE-03:** false-dispatch rate for non-fire scenarios `<= 10%`. Status: `NOT_RUN_EXTERNAL`.
- **HW-FIRE-04:** verify real three-window confirmation (`C >= 40`, 3 consecutive 1-second windows, at least 2 supporting channels). Status: `NOT_RUN_EXTERNAL`; production support policy remains in `SOURCE_TBD_REQUIREMENTS.md`.
- **HW-FIRE-05:** real person-in-hazard test produces `P = 1` and an explainable Critical override. Status: `NOT_RUN_EXTERNAL`.

## Real SN1, IR, and AC1 hardware

- **HW-IOT-01 SN1:** connect real MQ-2, DHT22, and manual button; verify MQTT schema, timestamps, freshness, disconnect behavior, and truthful UI state. Status: `NOT_RUN_EXTERNAL`.
- **HW-IOT-02 IR sensors:** connect `IR_A` and `IR_B`; verify physical road mapping, timing correlation, polarity, and conflict behavior. Status: `NOT_RUN_EXTERNAL`; policy remains TBD.
- **HW-IOT-03 AC1:** connect traffic-light corridor, servo gate, and buzzer; verify exact command ID/node ACK correlation and visible outputs. Status: `NOT_RUN_EXTERNAL`.

## 20-cycle physical acceptance

- **HW-E2E-01:** complete 20 real Understand → Respond cycles with command, ACK, retry, safe-default, and visible-output evidence. Status: `NOT_RUN_EXTERNAL`.
- **HW-E2E-02:** physical ACK success `>= 95%` over 20 real cycles. Status: `NOT_RUN_EXTERNAL`.
- **HW-E2E-03:** demonstrate hardware 500 ms timeout, exactly one retry, and safe default. Status: `NOT_RUN_EXTERNAL`.
- **HW-E2E-04:** physically confirm `ALL_RED`, gate `CLOSE`, and buzzer `ON` safe defaults. Status: `NOT_RUN_EXTERNAL`.

## Full real closed loop

**HW-CLOSE-01:** demonstrate real sensor/camera input → verification → severity → routing → AC1 action → physical ACK → dashboard/history → operator verification → eligible learning/risk history. Status: `NOT_RUN_EXTERNAL`.

Do not overwrite controlled software reports with physical results. Every hardware result and every resulting code/configuration change must be recorded in `TEAM_CHANGE_LOG.md`.

## Hardware-complete checklist

- [ ] Real camera coverage and ROI/road dimensions verified.
- [ ] Real detection/segmentation semantics and throughput verified.
- [ ] Physical dimension MAE verified.
- [ ] 40 fire scenarios, correctness, and false-dispatch targets verified.
- [ ] SN1/IR/AC1 integrated.
- [ ] 20 physical cycles and `>=95%` physical ACK success verified.
- [ ] Physical timeout/retry/safe-default outputs verified.
- [ ] Full real Understand → Respond → Learn demonstration recorded.
