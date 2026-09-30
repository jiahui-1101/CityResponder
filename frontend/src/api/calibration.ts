import { apiRequest } from "./client";

export type CalibrationWeights = { s: number; t: number; v: number; h: number };
export type CalibrationCandidate = { candidate_id: string; based_on_version: number | null; baseline_weights: CalibrationWeights; raw_proposed_weights: Record<string, number> | null; projected_candidate_weights: CalibrationWeights | null; batch_gradient_setting: number; training_count: number; validation_count: number; dataset_identity: string; provider_name: string | null; provider_version: string | null; status: string; reasons: string[]; warnings: string[]; created_at: string; audit_references: Array<Record<string, unknown>> };
export type CalibrationValidation = { candidate_id: string; status: string; passed: boolean | null; metrics: Record<string, unknown>; policy_name: string | null; policy_version: string | null; reasons: string[]; warnings: string[]; evaluated_at: string; audit_references: Array<Record<string, unknown>> };
export type CalibrationCandidateView = { candidate: CalibrationCandidate; validation: CalibrationValidation | null };
export type CalibrationVersion = { version_id: string; version_number: number; weights: CalibrationWeights; source_candidate_id: string | null; status: string; approved_by: number | null; approved_at: string | null; activated_at: string | null; supersedes_version: number | null; rollback_from_version: number | null; reasons: string[]; audit_references: Array<Record<string, unknown>>; created_at: string };
export type CalibrationGovernance = { active_version: CalibrationVersion | null; versions: CalibrationVersion[]; reasons: string[] };

export const calibrationRequests = {
  governance: () => apiRequest<CalibrationGovernance>("/api/admin/calibration"),
  versions: () => apiRequest<CalibrationVersion[]>("/api/admin/calibration/versions"),
  candidates: () => apiRequest<CalibrationCandidateView[]>("/api/admin/calibration/candidates"),
  candidate: (id: string) => apiRequest<CalibrationCandidate>(`/api/admin/calibration/candidates/${encodeURIComponent(id)}`),
  approve: (id: string) => apiRequest<CalibrationVersion>(`/api/admin/calibration/candidates/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  activate: (id: string) => apiRequest<CalibrationVersion>(`/api/admin/calibration/versions/${encodeURIComponent(id)}/activate`, { method: "POST" }),
  rollback: (id: string) => apiRequest<CalibrationVersion>(`/api/admin/calibration/versions/${encodeURIComponent(id)}/rollback`, { method: "POST" }),
};
