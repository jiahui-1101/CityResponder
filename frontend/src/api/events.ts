import { apiRequest } from "./client";

export type EventRecord = { id: number; event_type: string; entity_type: string; entity_id: string; reason_code: string | null; human_readable_reason: string | null; payload: Record<string, unknown>; created_at: string };
export type EventFilters = { eventType: string; entityType: string; entityId: string; startAt: string; endAt: string };
export const emptyEventFilters = (): EventFilters => ({ eventType: "", entityType: "", entityId: "", startAt: "", endAt: "" });

export function listEvents(filters: EventFilters, skip = 0, limit = 20) {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  if (filters.eventType) params.set("event_type", filters.eventType);
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.entityId.trim()) params.set("entity_id", filters.entityId.trim());
  if (filters.startAt) params.set("start_at", new Date(filters.startAt).toISOString());
  if (filters.endAt) params.set("end_at", new Date(filters.endAt).toISOString());
  return apiRequest<EventRecord[]>(`/api/events?${params.toString()}`);
}
