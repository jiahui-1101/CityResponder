import { apiRequest } from "./client";

export type RouteIndexItem = { route_id: string; latest_version: number; status: string; source_node_id: string; destination_node_id: string; node_path: string[]; edge_path: string[]; total_edge_cost: number | null; total_distance_cm: number | null; no_safe_route: boolean; route_changed: boolean; created_at: string; reasons: string[]; warnings: string[] };
export type RouteEvent = { id: number; event_type: string; entity_type: string; entity_id: string; reason_code: string | null; human_readable_reason: string | null; payload: Record<string, unknown>; created_at: string };
export type ActuatorStatus = { commands: Array<{ command_id: string; node_id: string; command_type: string; payload: Record<string, unknown>; sent_at: string; ack_status: string | null; ack_at: string | null }>; node_status: { node_id: string; last_command_at: string | null; last_ack_at: string | null; last_ack_status: string | null; available: boolean } };

export const routeRequests = {
  list: () => apiRequest<RouteIndexItem[]>("/api/routes?limit=100"),
  history: (routeId: string) => apiRequest<RouteEvent[]>(`/api/routes/${encodeURIComponent(routeId)}/history`),
  actuators: () => apiRequest<ActuatorStatus>("/api/actuators/status"),
  events: () => apiRequest<RouteEvent[]>("/api/events?limit=30"),
};
