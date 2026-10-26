import type { ActuatorStatus, EventRecord, FreshnessItem, SensorState } from "../api/overview";

/**
 * Plain-language wording for raw backend values.
 * Rule: never show an internal name (MQ2, PHYSICAL_ACTION, true/false) to the user.
 * Wording only: no values are invented, and a missing value stays visibly missing.
 */

type Tone = "success" | "warning" | "danger" | "neutral";
type Command = ActuatorStatus["commands"][number];

/** Last-resort fallback so SOME_RAW_NAME is shown as "Some raw name" instead of an internal code. */
export const sentenceCase = (value: string) => {
  const text = value.replaceAll("_", " ").toLowerCase().trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
};

const upper = (value: unknown) => (typeof value === "string" ? value.trim().toUpperCase() : "");
const record = (value: unknown): Record<string, unknown> => (value && typeof value === "object" ? (value as Record<string, unknown>) : {});

const asBoolean = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (["true", "1", "yes", "on", "pressed", "blocked"].includes(text)) return true;
    if (["false", "0", "no", "off", "released", "clear", "not blocked"].includes(text)) return false;
  }
  return null;
};

/** Today shows the time only; other days show a short date and time. */
export function formatWhen(value: string | null | undefined, fallback = "Not available") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  if (date.toDateString() === new Date().toDateString()) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
  }
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

/* ---------------------------------- Sensors --------------------------------- */

export const SENSOR_LABELS: Record<SensorState["sensor_type"], string> = {
  MQ2: "Smoke sensor",
  DHT22: "Temperature sensor",
  BUTTON: "Emergency button",
  IR_A: "Road sensor · Route A",
  IR_B: "Road sensor · Route B",
};

export type SensorDisplay = { label: string; value: string; unit?: string; alert: boolean; missing: boolean };

export function describeSensor(sensor: SensorState): SensorDisplay {
  const label = SENSOR_LABELS[sensor.sensor_type] ?? sentenceCase(sensor.sensor_type);
  if (!sensor.available || sensor.value === null || sensor.value === undefined) {
    return { label, value: "No data", alert: false, missing: true };
  }
  const flag = asBoolean(sensor.value);
  switch (sensor.sensor_type) {
    case "BUTTON":
      if (flag !== null) return { label, value: flag ? "Pressed" : "Not pressed", alert: flag, missing: false };
      break;
    case "IR_A":
    case "IR_B":
      if (flag !== null) return { label, value: flag ? "Blocked" : "Not blocked", alert: flag, missing: false };
      break;
    case "DHT22": {
      const degrees = Number(sensor.value);
      if (Number.isFinite(degrees)) {
        const unit = !sensor.unit || /^(c|°c|celsius)$/i.test(sensor.unit) ? "°C" : sensor.unit;
        return { label, value: degrees.toFixed(1), unit, alert: false, missing: false };
      }
      break;
    }
    case "MQ2": {
      const level = Number(sensor.value);
      // The smoke sensor is not calibrated yet, so the number is labelled as a raw reading.
      if (Number.isFinite(level)) return { label, value: String(Math.round(level)), unit: "raw reading", alert: false, missing: false };
      break;
    }
  }
  return { label, value: String(sensor.value), unit: sensor.unit ?? undefined, alert: false, missing: false };
}

export function sensorBadge(missing: boolean, freshness?: FreshnessItem): { text: string; tone: "success" | "warning" | "neutral" } {
  if (freshness?.stale === true) return { text: "Outdated", tone: "warning" };
  if (missing) return { text: "No reading yet", tone: "neutral" };
  return { text: "Receiving data", tone: "success" };
}

/* ---------------------------- Freshness / data age --------------------------- */

export const FRESHNESS_LABELS = {
  mq2: "Smoke sensor",
  dht22: "Temperature sensor",
  detection: "Camera detection",
  person: "Person in danger zone",
  road: "Road conditions",
} as const;

export const freshnessText = (item: FreshnessItem) => (item.stale === true ? "Outdated" : item.available ? "Up to date" : "No data");

export function freshnessDetail(item: FreshnessItem) {
  if (!item.available && !item.timestamp) return "No data received yet";
  const parts: string[] = [];
  if (item.age_seconds !== null) parts.push(`Data is ${item.age_seconds.toFixed(1)} s old`);
  if (item.timestamp) parts.push(`last update ${formatWhen(item.timestamp)}`);
  return parts.join(" · ") || "Timing not available";
}

export const personInHazardText = (value: boolean | null) => (value === null ? "No data" : value ? "Person detected" : "No one detected");

export const roadEvidenceText = (count: number) => (count === 0 ? "No road data" : count === 1 ? "1 road area checked" : `${count} road areas checked`);

/* ------------------------------- System health ------------------------------- */

export const HEALTH_LABELS = {
  backend: "Server",
  database: "Database",
  mqtt: "Device messaging",
  websocket: "Live updates",
  vision: "Camera AI",
  sensor_activity: "Sensor data",
  actuator_ack_activity: "Device confirmations",
} as const;

const HEALTH_STATUS: Record<string, string> = {
  healthy: "Working normally",
  connected: "Connected",
  available: "Available",
  unavailable: "Not available",
  unknown: "Not checked yet",
  warming: "Starting up",
};

export const healthStatusText = (status: string) => HEALTH_STATUS[status] ?? sentenceCase(status);

/* ------------------------------ Field devices -------------------------------- */

const routeName = (corridor: unknown) => {
  const value = upper(corridor);
  if (value === "PRIMARY" || value === "MAIN") return "main route";
  if (value === "STANDBY" || value === "ALTERNATE") return "alternate route";
  return null;
};

/**
 * Every command arrives as command_type "PHYSICAL_ACTION"; the real meaning lives in the payload.
 * Example: { action_category: "TRAFFIC", action_type: "GREEN_CORRIDOR", parameters: { corridor: "PRIMARY" } }
 *       -> "Traffic light: green for main route"
 */
export function describeCommand(command: Pick<Command, "command_type" | "payload">): string {
  const payload = record(command.payload);
  const parameters = record(payload.parameters);
  const category = upper(payload.action_category);
  const action = upper(payload.action_type);
  const output = upper(parameters.output);

  if (output.includes("AMBER")) {
    const ms = Number(parameters.duration_ms);
    return Number.isFinite(ms) && ms > 0 ? `Traffic lights: amber zone on for ${Math.round(ms / 1000)} s` : "Traffic lights: amber zone on";
  }
  if (category === "TRAFFIC") {
    if (action === "GREEN_CORRIDOR") {
      const route = routeName(parameters.corridor);
      return route ? `Traffic light: green for ${route}` : "Traffic light: green corridor";
    }
    if (action === "ALL_RED") return "Traffic lights: all red (stop)";
    if (action === "NORMAL_CYCLE") return "Traffic lights: back to normal cycle";
    if (action === "OFF") return "Traffic lights: off";
  }
  if (category === "GATE") {
    if (action === "OPEN") return "Servo gate: open";
    if (action === "CLOSE") return "Servo gate: closed";
  }
  if (category === "BUZZER") {
    if (action === "ON") return "Siren: on";
    if (action === "OFF") return "Siren: off";
    if (action === "PULSE_500_MS") return "Siren: short beeps";
  }
  if (category === "GATE") return `Servo gate: ${sentenceCase(action).toLowerCase()}`;
  if (category === "TRAFFIC") return `Traffic lights: ${sentenceCase(action).toLowerCase()}`;
  if (category && action) return `${sentenceCase(category)}: ${sentenceCase(action).toLowerCase()}`;
  return sentenceCase(command.command_type);
}

export const ackText = (status: string | null | undefined) => {
  if (!status) return "No confirmation yet";
  const value = upper(status);
  if (value === "ACK") return "Confirmed";
  if (value === "REJECTED") return "Rejected by device";
  return sentenceCase(status);
};

export const ackTone = (status: string | null | undefined): Tone => {
  if (!status) return "neutral";
  const value = upper(status);
  if (value === "ACK") return "success";
  if (value === "REJECTED") return "danger";
  return "warning";
};

/* ------------------------------- Recent activity ----------------------------- */

const EVENT_TITLES: Record<string, string> = {
  sensor_reading: "Sensor reading received",
  vision_detection: "Camera detection updated",
  vision_road_evidence: "Road check updated",
  actuator_command: "Command sent to a field device",
  actuator_ack: "Field device confirmed a command",
  actuator_command_publish_failed: "Command could not be sent",
  incident_decision: "Incident decision recorded",
  operator_decision: "Operator decision recorded",
  incident_decision_ignored: "Incident decision skipped (already handled)",
  operator_decision_ignored: "Operator decision skipped (already handled)",
  route_version: "Route updated",
  traffic_command_invalidated: "Traffic command cancelled",
  incident_evidence_retained: "Evidence frame saved",
  inspection_created: "Inspection requested",
  inspection_updated: "Inspection updated",
  area_risk_calculated: "Area risk recalculated",
  calibration_candidate: "New calibration proposed",
  calibration_validation: "Calibration checked",
};

export function describeEvent(event: EventRecord) {
  const reason = event.human_readable_reason ?? (event.reason_code ? sentenceCase(event.reason_code) : null);
  return {
    title: EVENT_TITLES[event.event_type] ?? sentenceCase(event.event_type),
    detail: reason,
    // Raw identifiers are kept for audit, as a hover tooltip only.
    audit: `${event.entity_type} · ${event.entity_id}`,
  };
}