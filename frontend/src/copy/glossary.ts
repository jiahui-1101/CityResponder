/**
 * Single Source of Truth for user-facing copy, plain-language display labels,
 * and neutral technical explanations (hints).
 *
 * Rules:
 * - Extends `humanize.ts`; if a term exists in both, `humanize.ts` wins.
 * - Display labels only. Never change enum values, API fields, or route paths.
 * - Hint texts must remain purely descriptive (no operational advice or unsourced claims).
 */

import {
  ackText,
  ackTone,
  describeCommand,
  describeEvent,
  describeSensor,
  formatWhen,
  freshnessDetail,
  freshnessText,
  healthStatusText,
  personInHazardText,
  roadEvidenceText,
  sensorBadge,
  sentenceCase,
  FRESHNESS_LABELS,
  HEALTH_LABELS,
  SENSOR_LABELS,
} from "../utils/humanize";

// Re-export baseline humanize utilities so consumers can import from a single place
export {
  ackText,
  ackTone,
  describeCommand,
  describeEvent,
  describeSensor,
  formatWhen,
  freshnessDetail,
  freshnessText,
  healthStatusText,
  personInHazardText,
  roadEvidenceText,
  sensorBadge,
  sentenceCase,
  FRESHNESS_LABELS,
  HEALTH_LABELS,
  SENSOR_LABELS,
};

/* --------------------------------------------------------------------------
 * Route Corridor & Sensor Mappings
 * -------------------------------------------------------------------------- */

/**
 * Route labels confirmed by team:
 * IR A = Main route (Route A)
 * IR B = Alternate route (Route B)
 *
 * TODO: PRIMARY = "main route" and STANDBY = "alternate route" corridor mapping
 * remains unconfirmed with backend team. Using lowercase plain names with TODO flag.
 */
export const ROUTE_LABELS = {
  main: "Main route",
  alternate: "Alternate route",
  no_safe_route: "No safe route",
} as const;

export const ROUTE_HINTS = {
  mainRoute: "Main route (Route A in hardware specification).",
  alternateRoute: "Alternate route (Route B in hardware specification).",
  // TODO: Verify if PRIMARY/STANDBY corridors strictly equate to main/alternate routes in all deployments.
  corridorTodo: "TODO: PRIMARY / STANDBY mapping unconfirmed; currently treated as main / alternate route.",
  noSafeRoute: "All known routes are blocked.",
  travelScore: "Lower score = preferred route.",
  priorCommandsInvalidated: "Earlier traffic commands are no longer valid.",
} as const;

/* --------------------------------------------------------------------------
 * Lifecycle Status Display Labels
 * -------------------------------------------------------------------------- */

export type LifecycleStatus =
  | "DISPATCHED"
  | "RESPONDING"
  | "EN_ROUTE"
  | "ARRIVED"
  | "RESOLVED";

export const LIFECYCLE_LABELS: Record<string, string> = {
  DISPATCHED: "Dispatched",
  RESPONDING: "Responding",
  EN_ROUTE: "On the way",
  ARRIVED: "Arrived",
  RESOLVED: "Resolved",
};

export const lifecycleLabel = (status: string | null | undefined): string => {
  if (!status) return "Unavailable";
  return LIFECYCLE_LABELS[status] ?? sentenceCase(status);
};

/* --------------------------------------------------------------------------
 * Area Risk Factor Definitions (Exact frontend_implement.md specification)
 * -------------------------------------------------------------------------- */

export type RiskFactorKey = "f" | "r" | "e" | "a" | "m";

export type RiskFactorDefinition = {
  key: string;
  symbol: string;
  name: string;
  description: string;
  formula: string;
  defaultWeight: number;
};

export const RISK_FACTORS: Record<RiskFactorKey, RiskFactorDefinition> = {
  f: {
    key: "f",
    symbol: "F",
    name: "Incident frequency (F)",
    description: "Incidents in the last 180 days.",
    formula: "F = incident_count / 180 days",
    defaultWeight: 0.3,
  },
  r: {
    key: "r",
    symbol: "R",
    name: "Recency (R)",
    description: "How long since the last incident.",
    formula: "R = 1.0 - (days_since_last / 180)",
    defaultWeight: 0.25,
  },
  e: {
    key: "e",
    symbol: "E",
    name: "Electrical share (E)",
    description: "Share of incidents with electrical cause.",
    formula: "E = electrical_incidents / total_incidents",
    defaultWeight: 0.2,
  },
  a: {
    key: "a",
    symbol: "A",
    name: "Recent anomalies (A)",
    description: "Anomalies in the last 30 days.",
    formula: "A = sensor_anomalies / 30 days",
    defaultWeight: 0.15,
  },
  m: {
    key: "m",
    symbol: "M",
    name: "Maintenance status (M)",
    description: "Overdue, open, or none.",
    formula: "M = score based on open/overdue maintenance records",
    defaultWeight: 0.1,
  },
};

/* --------------------------------------------------------------------------
 * Adaptive Calibration Sensor Weights (Exact backend/TBD-FUSION specification)
 * -------------------------------------------------------------------------- */

export type CalibrationWeightKey = "s" | "t" | "v" | "h";

export type CalibrationWeightDefinition = {
  key: CalibrationWeightKey;
  symbol: string;
  name: string;
  channel: string;
  description: string;
};

export const CALIBRATION_WEIGHTS: Record<
  CalibrationWeightKey,
  CalibrationWeightDefinition
> = {
  s: {
    key: "s",
    symbol: "S",
    name: "Sensor normalization (S)",
    channel: "Smoke & Heat Sensors",
    description:
      "Normalized reading from smoke (MQ-2) and temperature (DHT-22) hardware sensors.",
  },
  t: {
    key: "t",
    symbol: "T",
    name: "Temporal consistency (T)",
    channel: "Consistency Over Time",
    description:
      "Evidence consistency across consecutive 1-second observation windows.",
  },
  v: {
    key: "v",
    symbol: "V",
    name: "Vision normalization (V)",
    channel: "Camera AI",
    description:
      "Normalized camera AI detection confidence for fire and smoke.",
  },
  h: {
    key: "h",
    symbol: "H",
    name: "Historical baseline (H)",
    channel: "Area History",
    description:
      "Historical baseline derived from Area Risk score divided by 100.",
  },
};

/* --------------------------------------------------------------------------
 * Inspection Queue Actions & Statuses
 * -------------------------------------------------------------------------- */

export const INSPECTION_STATUS_LABELS: Record<string, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  CLOSED: "Closed",
};

export const inspectionStatusLabel = (status: string): string =>
  INSPECTION_STATUS_LABELS[status] ?? sentenceCase(status);

/**
 * Inspection button verbs matching the specification:
 * - Open -> "Mark in progress"
 * - In progress -> "Close inspection"
 */
export const inspectionActionLabel = (currentStatus: string): string => {
  if (currentStatus === "OPEN") return "Mark in progress";
  if (currentStatus === "IN_PROGRESS") return "Close inspection";
  return "Closed";
};

/* --------------------------------------------------------------------------
 * Event & Audit Type Display Labels
 * -------------------------------------------------------------------------- */

export const AUDIT_EVENT_LABELS: Record<string, string> = {
  incident_decision: "Incident decision recorded",
  operator_decision: "Operator feedback recorded",
  incident_decision_ignored: "Incident decision skipped",
  operator_decision_ignored: "Operator decision skipped",
  incident_evidence_retained: "Evidence frame saved",
  sensor_reading: "Sensor reading received",
  vision_detection: "Camera detection updated",
  vision_road_evidence: "Road check updated",
  route_version: "Route updated",
  traffic_command_invalidated: "Traffic command cancelled",
  actuator_command: "Command sent to device",
  actuator_ack: "Device confirmed command",
  actuator_command_publish_failed: "Command could not be sent",
  area_risk_calculated: "Area risk recalculated",
  inspection_created: "Inspection created",
  inspection_updated: "Inspection updated",
  calibration_candidate: "Calibration candidate proposed",
  calibration_validation: "Calibration validated",
  calibration_version_approved: "Calibration version approved",
  calibration_version_activated: "Calibration version activated",
  calibration_version_rollback: "Calibration version reverted",
};

export const auditEventLabel = (type: string): string =>
  AUDIT_EVENT_LABELS[type] ?? sentenceCase(type);

/* --------------------------------------------------------------------------
 * Technical Explanation Hints (Purely descriptive, non-advisory)
 * -------------------------------------------------------------------------- */

export const TECHNICAL_HINTS = {
  immutableRecord:
    "Permanent record stored in the system log that cannot be altered or deleted.",
  fieldController:
    "The street hardware controller (device ID: AC1) that controls traffic lights, sirens, and barrier gates.",
  brierScore:
    "Measures prediction accuracy. Lower score = better calibration (0.00 is perfect).",
  batchGradient:
    "Adjustment step size applied per training iteration.",
  slaThreshold:
    "Service Level Agreement: operational target threshold of 1000 ms for end-to-end event updates.",
  p95Latency:
    "Slowest 5% of updates: 95% of events finished faster than this duration.",
  domRenderDelay:
    "Time elapsed from receiving the network update until the browser repaints the screen.",
  mqttMessaging:
    "Device communication via the MQTT IoT messaging protocol.",
  shadowMode:
    "Evaluates live camera frames in the background without sending commands to physical street devices.",
  roadSegment:
    "A specific road section between two street intersections on the emergency map.",
} as const;
