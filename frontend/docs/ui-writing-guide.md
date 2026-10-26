# CityResponder UI Writing & Plain-Language Guide

A single-source guide for frontend engineers and teammates working on CityResponder interfaces.

---

## 1. Core Writing Rules

1. **Target Reading Level:** Plain English, everyday vocabulary, and short sentences ($\le 15$ words). Aim for an 8th-grade reading level.
2. **Describe Function, Not Implementation:** Say what an item is or does, not how the backend or database computed it (e.g., "Saved route", not "Persisted route projection"). Put technical specifications into an `InfoHint`.
3. **Sentence Case Everywhere:** Use sentence case for headings, section titles, table headers, buttons, and status badges (e.g., "No safe route", not "NO_SAFE_ROUTE"). Small uppercase is reserved exclusively for small eyebrow tags (`.eyebrow`).
4. **Button Wording:** Always use **Verb + Object** (e.g., "Create user", "Export CSV", "Mark in progress", "Close inspection").
5. **Exact Numbers & Units:** Keep units exact with a space before the unit (e.g., `"1000 ms"`, `"180 days"`, `"12.4 s"`). Never round down or truncate safety numbers or sensor thresholds.
6. **Error Messages:** State what happened + what to do next (e.g., "Could not load incidents. Check your network connection and try again.").
7. **Empty States:** State why the view is empty + what action to take.

---

## 2. Audience-Specific Guidance

* **Emergency Operator & Dispatch:**
  * Shortest possible wording for high-stress glanceability.
  * Explicit state labels accompanying any color indicators.
  * Action buttons must use unambiguous verbs ("Confirm", "Reject", "Cancel").
* **Firefighter & Field Responder:**
  * Maximum clarity on mobile/tablet screens.
  * Zero database jargon. Big, legible route statuses ("Main route", "Alternate route", "No safe route").
  * Strict linear lifecycle: "On the way" → "Arrived" → "Resolved".
* **City Risk Planner:**
  * Professional municipal planning terminology.
  * Risk formulas (F, R, E, A, M) explained with `InfoHint`.
  * Concrete next actions ("Start inspection", "Export CSV").
* **System Administrator:**
  * Technical precision is permitted (e.g., Brier score, P95 latency, sensor weights), but every technical term must include a descriptive `InfoHint`.
  * Destructive or governance actions must have an explicit confirmation modal.

---

## 3. Approved Terminology Dictionary

| Internal / Jargon Term | Approved Display Label | Usage Rule & Context |
| :--- | :--- | :--- |
| `Incident` | **Incident** | Use everywhere. Never call an incident an "alert" or "event". |
| `Alert` | **Alert / Warning** | Reserved exclusively for notification banners and immediate system warnings. |
| `Event` | **Event / Activity** | Reserved exclusively for chronological audit log records. |
| `Backend API` / `Backend` | **Server** | Admin pages may display an InfoHint explaining "Backend API". |
| `MQTT broker` / `MQTT` | **Device messaging** | Explain MQTT in an InfoHint for admin/audit views. |
| `healthy` | **Working normally** | Baseline status for operational subsystems. |
| `Actuator` / `AC1` | **Field controller** | Raw node ID "AC1" is placed in tooltips or InfoHints only. |
| `ACK` / `REJECTED` / `null` | **Confirmed** / **Rejected by device** / **No confirmation yet** | Overview baseline for device command status. |
| `NO_SAFE_ROUTE` | **No safe route** | Purely descriptive: "All known routes are blocked." |
| `proxy cost` | **Estimated travel score** | Purely descriptive hint: "Lower score = preferred route." |
| `prior commands invalidated` | **Earlier traffic commands are no longer valid** | Never use "cancelled". |
| `IR_A` / `IR_B` | **Main route: Blocked / Not blocked** / **Alternate route: Blocked / Not blocked** | Confirmed mapping (Route A = Main route, Route B = Alternate route). |
| `PRIMARY` / `STANDBY` | **main route / alternate route** | *TODO: Corridor mapping unconfirmed; flagged with TODO.* |
| `F, R, E, A, M` | **F: Incident frequency**, **R: Recency**, **E: Electrical share**, **A: Recent anomalies**, **M: Maintenance status** | Exact names from specification; formulas documented in hints. |
| `S, T, V, H` | **S: Sensor normalization**, **T: Temporal consistency**, **V: Vision normalization**, **H: Historical baseline** | Exact sensor fusion channels from backend spec. |

---

## 4. Safety-Related Copy Rules (Do Not Weaken)

1. **Person in Hazard Zone:** Critical safety overrides must remain explicit ("Critical override applied · person in hazard zone").
2. **Unconfirmed Commands:** Commands that have not received an ACK must never be presented as completed; show "No confirmation yet".
3. **Reroute Alerts:** Reroute notices must be clearly stated as condition changes ("Route conditions changed").
4. **Electrical Risk Hotspot:** Use cautious, exact phrasing ("Possible electrical-risk hotspot; inspection recommended").
5. **Demonstration Data Disclosure:** Synthetic demo notices must remain explicit ("Isolated simulation database · MQTT unavailable · no physical actuation").
6. **No Operational Advice in Hints:** Hints must describe system state only. Never tell responders what tactical action to take.

---

## 5. Component Usage: `InfoHint` & `LabelWithHint`

Import the components from `@/components/InfoHint`:

```tsx
import { InfoHint, LabelWithHint } from "../components/InfoHint";
import { TECHNICAL_HINTS, ROUTE_HINTS } from "../copy/glossary";

// Standard label with info hint
<LabelWithHint
  label="Estimated travel score"
  hint={ROUTE_HINTS.travelScore}
/>

// Standalone icon hint next to a custom heading or metric
<div className="metric-header">
  <span>95th percentile (P95)</span>
  <InfoHint
    label="P95 latency"
    text={TECHNICAL_HINTS.p95Latency}
  />
</div>
```

### Hint Budget Rule
* **Operator & Firefighter pages:** Keep hints to a minimum. Fix jargon primarily by simplifying the label itself. Use hints only when a technical term is truly unavoidable.
* **Admin & Planner pages:** Higher hint budget permitted for engineering parameters, algorithms, and formulas.
* **Rule of First Occurrence:** Show an `InfoHint` only on the **first occurrence** of a term on a page to avoid visual clutter.

---

## 6. Contrast & Accessibility Requirements

* Normal text must achieve at least **4.5:1** contrast against its background.
* Large text ($\ge 18\text{px}$ or $14\text{px}$ bold) must achieve at least **3:1**.
* Page eyebrows on cream (`#f8f8f5`) must use `--color-orange-800` (`#a24c08`, **5.52:1** ratio).
* `InfoHint` popover achieves **15.6:1** contrast (`#1f1d1b` background with `#f8f8f5` text).
* Every interactive button must have a focus outline (`:focus-visible`).
* All tooltips must close on Escape and click/tap outside, and must not overflow at 375px viewport width.
