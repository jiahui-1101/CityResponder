# CityResponder — Team Change Log

**Purpose:** Shared record of requirement, policy, implementation, validation, hardware, UI/UX, and configuration changes.

## Mandatory rule

Whenever a teammate changes a requirement, source threshold, production policy, hardware mapping, sensor interpretation, routing topology, dispatch matrix, calibration policy, area-risk policy, API contract, UI/UX behavior, RBAC behavior, validation result, hardware result, camera/model configuration, production configuration, or evidence-retention behavior, add an entry here in the same work session.

Do not rely only on Git commit messages. Refer to `HARDWARE_EXTERNAL_REQUIREMENTS.md` for external work and `SOURCE_TBD_REQUIREMENTS.md` for undefined policy.

## Status vocabulary

Use: `PASS`, `FAIL`, `PARTIAL`, `NOT_RUN_EXTERNAL`, `BLOCKED_EXTERNAL`, `TBD_SOURCE`.

## Standard change entry

```md
## YYYY-MM-DD HH:MM — Short change title

**Changed by:** Name
**Branch:** branch-name
**Commit:** hash / not committed yet

**Requirement / area:**
- Requirement ID or module

**Files changed:**
- path

**Previous behavior / value:**
- ...

**New behavior / value:**
- ...

**Why this changed:**
- source clarification / team decision / bug fix / validation / UI consistency / other

**Source / decision reference:**
- proposal section, team decision, hardware evidence, or report

**Validation performed:**
- command/test/scenario and result

**Requirement status after change:**
- PASS / FAIL / PARTIAL / NOT_RUN_EXTERNAL / BLOCKED_EXTERNAL / TBD_SOURCE

**Impact on teammates:**
- update, rerun, or avoid

**Follow-up required:**
- next action or None
```

## Policy decision entry

Every team-approved TBD resolution must record the exact rule/formula/threshold, approver, affected backend/frontend/hardware/validation modules, tests to rerun, and the documentation/code updates.

## Hardware validation entry

Record tester, hardware and firmware versions, backend commit, environment, requirement ID/target, measured result, status, evidence path, notes, software/config changes, and follow-up.

## Current software baseline

- Branch: `main`
- Latest software commit: `df7a2f2`
- Deep audit baseline before this tracking-document commit: `a3950ef`
- Requirements reviewed: 328
- PASS: 251
- FAIL: 0
- PARTIAL: 0
- NOT_RUN_EXTERNAL: 19
- TBD_SOURCE: 58
- Backend compile/import/OpenAPI: PASS
- Frontend typecheck/build: PASS
- API contract audit: 29/29 matched
- Controlled routing benchmark: 150/150 under 1 second
- Controlled dashboard latency: 10/10 under 1 second
- Production UI fake/mock audit: PASS

Future changes must not invalidate this baseline without updating validation evidence and this log.

## 2026-10-01 — Shared requirement tracking files added

**Changed by:** Team / ChatGPT-assisted documentation
**Branch:** `main`
**Commit:** documentation commit for these files

**Requirement / area:**
- Cross-team requirement, external-validation, and source-TBD tracking

**Files changed:**
- `HARDWARE_EXTERNAL_REQUIREMENTS.md`
- `SOURCE_TBD_REQUIREMENTS.md`
- `TEAM_CHANGE_LOG.md`

**Previous behavior / value:**
- Remaining external and source-undefined work was distributed across audit summaries and validation reports.

**New behavior / value:**
- External hardware/camera acceptance and source-undefined policy decisions are separated into shared root documents with mandatory change control.

**Why this changed:**
- Keep teammates synchronized and prevent silent requirement, policy, mapping, or status changes.

**Source / decision reference:**
- Final deep audit and current project requirements.

**Validation performed:**
- Cross-checked against the final deep-audit coverage and existing validation reports.

**Requirement status after change:**
- Documentation/tracking added; software behavior unchanged.

**Impact on teammates:**
- Record every future requirement, policy, hardware, UI/API, and validation change here.

**Follow-up required:**
- Keep the log entry in the same commit as these tracking files and update it for every subsequent change.

## Change entries

<!-- Add newest entries above older entries. -->
