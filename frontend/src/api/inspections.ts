import { apiBinaryRequest, apiRequest } from "./client";

export type Inspection = { inspection_id: string; area_id: string; incident_id: string | null; reason: string; status: string; notes: string | null; created_at?: string; updated_at?: string; };
export const inspectionRequests = {
  list: () => apiRequest<Inspection[]>("/api/inspections"),
  create: (body: Omit<Inspection, "inspection_id" | "created_at" | "updated_at">) => apiRequest<Inspection>("/api/inspections", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: { status?: string; notes?: string }) => apiRequest<Inspection>(`/api/inspections/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  exportCsv: () => apiBinaryRequest("/api/inspections/export.csv"),
};
