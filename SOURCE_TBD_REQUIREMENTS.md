# CityResponder — Source-Undefined / Policy-TBD Requirements

**Purpose:** Preserve production decisions that the authoritative proposal does not define. Codex and teammates must not guess these values or meanings.

## Change-control rule

Any change to this file, any new policy decision, any value/threshold added, or any item moved from `TBD_SOURCE` to implementation must also be recorded in `TEAM_CHANGE_LOG.md`. A TBD may close only after the exact decision, affected files, tests, validation, and documentation are updated.

## Fire fusion — S / T / V / H

The source defines `C = 100 * (0.30S + 0.20T + 0.35V + 0.15H)`, `C >= 40`, three consecutive 1-second windows, and at least two supporting channels. It does not define:

- **TBD-FUSION-01:** MQ-2/DHT22 normalization, clamping, and stale/missing behavior for `S`.
- **TBD-FUSION-02:** exact temporal consistency formula and persistence semantics for `T`.
- **TBD-FUSION-03:** fire/smoke/person aggregation into `V`.
- **TBD-FUSION-04:** history source, horizon, anomaly formula, and cold-start behavior for `H`.
- **TBD-FUSION-05:** what makes a channel supporting, independently of its fusion weight.
- **TBD-FUSION-06:** whether the manual Button is evidence, confirmation, or override and whether it changes `C`.

## Severity — A / S / T / P / Z

The source defines `R = 100 * (0.30A + 0.20S + 0.20T + 0.20P + 0.10Z)` and `P = 1` inside the hazard zone ⇒ Critical. It does not define:

- **TBD-SEV-01:** `A` meaning, source, normalization, and missing behavior.
- **TBD-SEV-02:** whether severity `S` reuses fusion `S`.
- **TBD-SEV-03:** severity `T` meaning and normalization.
- **TBD-SEV-04:** production hazard-zone geometry and boundary rule.
- **TBD-SEV-05:** `Z` meaning, source, normalization, and missing behavior.
- **TBD-SEV-06:** Low/Medium/High/Critical numeric boundaries.

## Dispatch matrix

- **TBD-DISPATCH-01:** responder/resource mapping by severity.
- **TBD-DISPATCH-02:** person-evidence escalation beyond the Critical override.
- **TBD-DISPATCH-03:** exact traffic, gate, buzzer, and other building-action matrix.

The software has an explicit policy interface and does not invent a production matrix.

## Routing production calibration

The source formula is `edge_cost = distance_cm * (1 + 4 * (0.70O + 0.20L + 0.10C))`, with blocked/conflicted edges removed. It does not define:

- **TBD-ROUTE-01:** conversion of segmentation evidence into routing `O`.
- **TBD-ROUTE-02:** routing `L` meaning and normalization.
- **TBD-ROUTE-03:** routing `C`, distinct from fire confidence `C`.
- **TBD-ROUTE-04:** IR polarity, debounce/noise handling, and edge mapping.
- **TBD-ROUTE-05:** exact IR sample timing/support rule.
- **TBD-ROUTE-06:** all production camera/IR conflict cases and operator resolution.
- **TBD-ROUTE-07:** production node/edge topology, physical distances, ROI/IR mapping, and source/destination mapping.
- **TBD-ROUTE-08:** ETA speed, scale, units, and delay assumptions.

## Incident feedback lifecycle

- **TBD-INC-01:** how CONFIRM/REJECT/CANCEL affect risk eligibility, calibration labels, false-dispatch metrics, and training.
- **TBD-INC-02:** richer lifecycle states/transitions, if required beyond the source-backed manual actions.

## Area risk — F / R / E / A / M

The source defines `100 * (0.30F + 0.25R + 0.20E + 0.15A + 0.10M)` using operator-verified incidents within 180 days. It does not define:

- **TBD-RISK-01..05:** normalization/meaning for `F`, `R`, `E`, `A`, and `M`.
- **TBD-RISK-06:** area IDs, geometry, and incident-to-area mapping.
- **TBD-RISK-07:** risk bands/thresholds.
- **TBD-RISK-08:** cold-start behavior with insufficient verified history.
- **TBD-RISK-09:** what-if/predictive inputs and interpretation.

## Adaptive calibration

Already source-defined in the software contract: batch setting `0.02`, weights `[0.10, 0.50]`, sum `1.00`, 30 training outcomes, 15 separate validation outcomes, bounded simplex, versioning, Admin governance and rollback. Still TBD:

- **TBD-CAL-01:** training feature/label representation.
- **TBD-CAL-02:** operator-feedback label semantics.
- **TBD-CAL-03:** loss/objective function.
- **TBD-CAL-04:** full gradient/update equation beyond `0.02`.
- **TBD-CAL-05:** validation metric.
- **TBD-CAL-06:** performance-gate threshold.
- **TBD-CAL-07:** 30/15 dataset selection.
- **TBD-CAL-08:** initial production version.
- **TBD-CAL-09:** when approved weights control live fusion.
- **TBD-CAL-10:** rollback live effect and in-flight behavior.

## Evidence retention and admin policy

- **TBD-PRIV-01..04:** retention duration, purge authorization/timing, production evidence storage, and automatic frame selection.
- **TBD-ADMIN-01:** which operational settings System Administrator may edit.

## Operations

- **TBD-OPS-01:** production graph size, event rate, concurrent users, and deployment environment.
- **TBD-OPS-02:** production scale/load acceptance criteria.
- **TBD-OPS-03:** availability, restart, recovery, backup, and uptime expectations.

## Definition of source-policy complete

- [ ] Every TBD has a team-approved answer or is explicitly removed from scope.
- [ ] Software requirements, implementation, UI, tests, and validation are updated together.
- [ ] No fake value is introduced to close a TBD.
- [ ] Every resolution is recorded in `TEAM_CHANGE_LOG.md`.
