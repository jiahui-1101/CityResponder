import { apiRequest } from "./client";

export type ResponseStatus = "DISPATCHED" | "RESPONDING" | "EN_ROUTE" | "ARRIVED" | "RESOLVED" | "STOPPED" | "SAFE_DEFAULT" | "VERIFIED" | "VERIFIED_FIRE";
export type LifecycleEvent = { id: number; event_type: string; entity_type: string; entity_id: string; reason_code: string | null; human_readable_reason: string | null; payload: Record<string, unknown>; created_at: string };
export type ResponseLifecycle = { incident_id: string; status: ResponseStatus | string; status_changed_at: string | null; preliminary_outcome: "FIRE" | "FALSE_ALARM" | "UNKNOWN" | null; probable_cause: string | null; inspection_required: boolean | null; notes: string | null; verified_outcome: "VERIFIED_FIRE" | "VERIFIED_FALSE_ALARM" | null; events: LifecycleEvent[] };

export const lifecycleRequests = {
  get: (incidentId: string) => apiRequest<ResponseLifecycle>(`/api/incidents/${encodeURIComponent(incidentId)}/lifecycle`),
  responder: (incidentId: string, body: { action: "EN_ROUTE" | "ARRIVED" | "RESOLVED"; preliminary_outcome?: string; probable_cause?: string; inspection_required?: boolean; notes?: string }) => apiRequest<ResponseLifecycle>(`/api/incidents/${encodeURIComponent(incidentId)}/responder-action`, { method: "POST", body: JSON.stringify(body) }),
  operator: (incidentId: string, action: "START_RESPONSE" | "MANUAL_STOP" | "RESTORE_SAFE_DEFAULT", reason: string) => apiRequest<ResponseLifecycle>(`/api/incidents/${encodeURIComponent(incidentId)}/operator-lifecycle`, { method: "POST", body: JSON.stringify({ action, reason }) }),
  feedback: (incidentId: string, outcome: "VERIFIED_FIRE" | "VERIFIED_FALSE_ALARM", reason: string) => apiRequest<ResponseLifecycle>(`/api/incidents/${encodeURIComponent(incidentId)}/operator-feedback`, { method: "POST", body: JSON.stringify({ outcome, reason }) }),
};
