import { apiRequest } from "./client";

export type AreaRiskResult = {
  area_id: string;
  status: string;
  score: number | null;
  weights: Record<string, number>;
  f: number | null;
  r: number | null;
  e: number | null;
  a: number | null;
  m: number | null;
  window_start: string;
  window_end: string;
  verified_incident_count: number;
  provider_name: string | null;
  provider_version: string | null;
  reasons: string[];
  warnings: string[];
  audit_references: Array<Record<string, unknown>>;
  calculated_at: string;
};

export const riskRequests = {
  areas: () => apiRequest<AreaRiskResult[]>("/api/risk/areas"),
  area: (areaId: string) => apiRequest<AreaRiskResult>(`/api/risk/areas/${encodeURIComponent(areaId)}`),
  history: (areaId: string) => apiRequest<AreaRiskResult[]>(`/api/risk/areas/${encodeURIComponent(areaId)}/history`),
};
