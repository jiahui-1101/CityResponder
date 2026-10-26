# CityResponder Phase 4.1E — remaining AC1 hardware validation

**Date:** 2026-10-26 (Asia/Singapore)
**Scope:** normal cycling, traffic off, buzzer on/off, safe final state. Gate/servo remains deferred.

## Verified starting state

The Phase 4.1D audit records secure Mosquitto, backend and AC1 connections, real correlated `RECEIVED` and `ACK/execution_reported` messages, and operator-observed primary green, standby green, and all-red static traffic states. The final operator-observed traffic state was all red. Those passed states are not repeated in this phase unless needed as a safety stop.

## Firmware contract and safety inspection

- `TRAFFIC/NORMAL_CYCLE` is supported. It starts with PRIMARY green for a nominal 4,000 ms, then PRIMARY yellow for 1,000 ms, STANDBY green for 4,000 ms, and STANDBY yellow for 1,000 ms, repeating until another traffic command changes the mode. The loop checks `millis()` and calls `delay(5)`, so actual durations must be observed rather than assumed exact. The firmware has no programmed all-red dwell between routes. Each completed phase sets at most one green high; a source-level simulation of 30 sequential LED writes across a complete cycle and return to phase zero found zero intermediate states with both greens high. The same simulation found both red pins high briefly between three sequential writes when transitioning from PRIMARY yellow to STANDBY green; it does not establish a sustained both-red phase. This does not replace physical observation.
- `TRAFFIC/ALL_RED` is the documented safe static stop: both red pins high, yellow and green pins low, cycle mode stopped. It was physically verified in Phase 4.1D.
- `TRAFFIC/OFF` is supported and calls `allLedsOff()`: all six traffic pins low and cycle mode stopped. Both routes go dark. It is not a safe final state; any bounded tabletop test must promptly restore `ALL_RED`.
- `BUZZER/ON` is supported and drives active-low GPIO19 low indefinitely until another buzzer action. `BUZZER/OFF` drives GPIO19 high and cancels pulse mode. The actual module trigger polarity still needs operator confirmation. `BUZZER/PULSE_500_MS` toggles every 500 ms indefinitely; despite its name, it is not a bounded single pulse and is excluded from this phase's brief buzzer test. A later ON/OFF test needs an explicit short timer and operator-controlled power cutoff if the OFF command cannot be delivered.
- Gate commands attach and drive the servo on GPIO18. Replacement servo behavior and independent position feedback remain unverified; no gate command is authorized in this phase.

## First proposed physical test: bounded normal cycle

Pending separate operator authorization: send one non-retained QoS 1 `PHYSICAL_ACTION` command for `TRAFFIC/NORMAL_CYCLE` through the backend, with no application retry. Have the operator observe and time the four phases, including absence of simultaneous greens. Because cycling does not stop itself, the same authorization must include one `TRAFFIC/ALL_RED` safety-stop command at a fixed maximum of 15 seconds after broker confirmation, even if observation or the cycle ACK is delayed. Verify broker confirmation and both real AC1 ACK stages for each command, then obtain the operator's physical observation of the cycle and final all-red state. If delivery of the stop command is uncertain or outputs behave unexpectedly, do not retry blindly; the operator should disconnect AC1 output power and report the state.

The operator authorized this bounded test. One `NORMAL_CYCLE` command (`ca7b069f-f991-40d5-8fe3-1d342db93eff`) was broker-confirmed, followed by one `ALL_RED` stop (`76e195e7-9aae-42b8-b9b1-b295c77fd80b`) attempted 12,500 ms after the cycle attempt began and also broker-confirmed. Each received real, matching `RECEIVED/received` and `ACK/execution_reported` messages from `city/acks/AC1`, with no rejection or simulation flag. Command-to-terminal-ACK latencies were 475 ms and 278 ms. No application retry occurred. The operator reported generally normal red/yellow/green transitions and no simultaneous green lights, but did not time the phases. They separately confirmed the final `ALL_RED` state: both reds on and all yellow/green off. They noticed both reds at points within the repeating cycle but could not tell whether this was a brief flicker or a sustained interval. A source-level check found a brief both-red intermediate state at the PRIMARY-yellow to STANDBY-green transition, but no sustained programmed both-red phase. The duration of the observed both-red state remains unresolved. The event history contains only the authorized `NORMAL_CYCLE` and `ALL_RED` commands during this test. Firmware serial logs do not emit individual phase transitions or timestamps, and the Mosquitto log is empty, so actual 4/1/4/1-second timing cannot be verified from logs. The ACKs alone do not verify physical phase timing.

## Bounded traffic OFF test

The operator separately authorized a tabletop-only OFF test with a timed all-red restore and power cutoff available. The backend sent `TRAFFIC/OFF` once, command ID `d530072e-96e6-4e00-b98e-ad2a863afa79`, followed 3,001 ms after the OFF attempt began by one `TRAFFIC/ALL_RED` restore, ID `3b7a0e85-dbe2-4617-8a35-3b82c87888dd`. Both publications were broker-confirmed and each received real matching `RECEIVED/received` and `ACK/execution_reported` messages from `city/acks/AC1`, without rejection or simulation flag. Command-to-terminal-ACK latencies were 445 ms and 420 ms. The operator observed all six traffic lights dark during OFF, then the exact all-red state (both reds on; yellow/green off) after restore, with no gate or buzzer change. No retry or unrelated command was sent. OFF behavior and safe restoration are physically verified for this isolated tabletop test; OFF is not a safe final state.

## Brief buzzer ON/OFF test

The operator separately authorized one brief ON/OFF pair with the sound safe for this tabletop and output-power cutoff available. The backend sent `BUZZER/ON` once, command ID `e54e639d-2d1d-4193-b120-86bb45c884dd`, then `BUZZER/OFF` once 1,500 ms after the ON attempt began, ID `d20505ab-6d8b-4056-b445-98453138be39`. Both publications were broker-confirmed. Each received real matching `RECEIVED/received` and `ACK/execution_reported` messages from `city/acks/AC1`, without rejection or simulation flag. Command-to-terminal-ACK latencies were 347 ms and 283 ms. The operator heard the buzzer during ON and silence after OFF, with no traffic-light or gate change. `PULSE_500_MS` was not used. No retry or other command was sent.

## Final safe state and limits

After all authorized tests, the operator directly confirmed both red LEDs on, all yellow/green LEDs off, the buzzer silent, and the gate unchanged. A final read-only check found Mosquitto Running, AC1 connected from `<PRIVATE_LAN_IP>`, backend connected on loopback, and backend `/health` healthy. The event history showed only the six authorized Phase 4.1E traffic/buzzer commands and stops listed above. No production incident, automatic dispatch, SN1 command, YOLO evidence publish, firmware flash, gate command, MQTT application retry, commit, push, merge, or Cloudflare change was performed in this phase.

The cycle's real ACKs, generally normal visual transitions, and absence of simultaneous greens passed. Actual phase durations and whether the observed both-red interval was only the brief source-level GPIO transition remain unverified. Source code has no per-phase serial log entries, so logs cannot resolve either point. Full AC1 demo readiness is withheld while these timing observations and gate/servo behavior remain unverified; the validated static lights, bounded OFF, and brief buzzer ON/OFF can be reported separately.

## Status

```text
REAL_ACK=PASS_ALL_SIX_PHASE41E_COMMANDS
NORMAL_TRAFFIC_CYCLING=PARTIAL_REAL_ACK_GENERAL_VISUAL_PASS_TIMING_AND_RED_DURATION_UNVERIFIED
TRAFFIC_OFF=PASS_BOUNDED_DARK_THEN_ALL_RED
BUZZER_ON=PASS_REAL_ACK_AND_AUDIBLE_OUTPUT
BUZZER_OFF=PASS_REAL_ACK_AND_OPERATOR_CONFIRMED_SILENCE
SAFE_FINAL_STATE=PASS_OPERATOR_CONFIRMED_ALL_RED_BUZZER_SILENT_GATE_UNCHANGED
GATE_SERVO=DEFERRED
PHYSICAL_OBSERVATION=PASS_OFF_ALL_RED_BUZZER_ON_OFF_PARTIAL_CYCLE_TIMING
AC1_DEMO_READY=NO_FULL_DEMO_GATE_AND_CYCLE_TIMING_UNVERIFIED
```
