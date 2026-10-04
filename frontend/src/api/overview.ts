import { apiRequest } from "./client";

export type ComponentStatus = { status: string; last_seen: string | null; detail: string | null; connected_clients?: number | null };
export type SystemHealth = { backend: ComponentStatus; database: ComponentStatus; mqtt: ComponentStatus; websocket: ComponentStatus; sensor_activity: ComponentStatus; actuator_ack_activity: ComponentStatus; vision: ComponentStatus };
export type SensorState = { sensor_type: "MQ2" | "DHT22" | "BUTTON" | "IR_A" | "IR_B"; value: unknown; timestamp: string | null; node_id: string | null; unit: string | null; available: boolean };
export type FreshnessItem = { source_type: string; source_id: string | null; available: boolean; stale: boolean | null; age_seconds: number | null; timestamp: string | null };
export type PerceptionFreshness = { mq2: FreshnessItem; dht22: FreshnessItem; button: FreshnessItem; ir_a: FreshnessItem; ir_b: FreshnessItem; detection: FreshnessItem; road_evidence: FreshnessItem[] };
export type VisionSnapshot = { generated_at: string; sensors: SensorState[]; detection: Record<string, unknown> | null; person_in_hazard: boolean | null; road_evidence: Array<Record<string, unknown>>; freshness: PerceptionFreshness; road_sync: Array<{ road_roi_name: string; time_matched: boolean | null; conflict: boolean | null; conflict_reason: string }>; warnings: string[]; unavailable_inputs: string[] };
export type ActuatorStatus = { commands: Array<{ command_id: string; node_id: string; command_type: string; payload: Record<string, unknown>; sent_at: string; ack_status: string | null; ack_at: string | null }>; node_status: { node_id: string; last_command_at: string | null; last_ack_at: string | null; last_ack_status: string | null; available: boolean } };
export type EventRecord = { id: number; event_type: string; entity_type: string; entity_id: string; reason_code: string | null; human_readable_reason: string | null; payload: Record<string, unknown>; created_at: string };

export const overviewRequests = {
  health: () => apiRequest<SystemHealth>("/api/system/health"),
  sensors: () => apiRequest<SensorState[]>("/api/sensors/latest"),
  actuators: () => apiRequest<ActuatorStatus>("/api/actuators/status"),
  freshness: () => apiRequest<PerceptionFreshness>("/api/perception/freshness"),
  snapshot: () => apiRequest<VisionSnapshot>("/api/perception/snapshot"),
  events: () => apiRequest<EventRecord[]>("/api/events?limit=8"),
};
