import { apiBinaryRequest, apiRequest } from "./client";

export type OperatorAction = "CONFIRM" | "REJECT" | "CANCEL";
export type SeverityFloor = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type OperatorDecision = { action_id: string; incident_decision_id: string; operator_id: number; operator_role: string; action: OperatorAction; written_reason: string; previous_automatic_decision_status: string; resulting_operator_outcome: string; action_timestamp: string; reasons: string[]; warnings: string[] };
export type FusionConfidence = { status: string; confidence_score: number | null; s_score: number | null; t_score: number | null; v_score: number | null; h_score: number | null; weights: Record<string, number>; weighted_contributions: Record<string, number | null>; reasons: string[]; calculated_at: string };
export type AutomaticDecision = { decision_id: string; evaluated_at: string; confirmation_status: string; incident_confirmed: boolean | null; fusion_confidence: FusionConfidence; severity_score: number | null; base_severity: string | null; final_severity: string | null; critical_override_applied: boolean; decision_status: string; reasons: string[]; warnings: string[]; audit_references: Array<Record<string, unknown>> };
export type EventRecord = { id: number; event_type: string; entity_type: string; entity_id: string; reason_code: string | null; human_readable_reason: string | null; payload: Record<string, unknown>; created_at: string };
export type IncidentIndexItem = { decision_id: string; created_at: string; evaluated_at: string; automatic_decision_status: string; incident_confirmed: boolean | null; final_severity: string | null; severity_score: number | null; latest_operator_action: OperatorDecision | null; projected_outcome: string; reasons: string[]; warnings: string[] };
export type IncidentProjection = { incident_id: string; automatic_decision: AutomaticDecision; operator_actions: OperatorDecision[]; latest_operator_action: OperatorDecision | null; projected_outcome: string; final_severity: string | null; created_at: string; evaluated_at: string; audit_timeline: EventRecord[]; warnings: string[] };
export type IncidentEvidenceFrame = { evidence_id: string; incident_decision_id: string; captured_at: string; stored_at: string; frame_index: number; content_type: string; storage_reference: string; annotation_metadata: Record<string, unknown>; source_camera_id: string | null; reason_codes: string[]; audit_references: Array<Record<string, unknown>> };

export const incidentRequests = {
  list: () => apiRequest<IncidentIndexItem[]>("/api/incidents?limit=100"),
  projection: (decisionId: string) => apiRequest<IncidentProjection>(`/api/incidents/${encodeURIComponent(decisionId)}`),
  history: (decisionId: string) => apiRequest<EventRecord[]>(`/api/incidents/${encodeURIComponent(decisionId)}/history`),
  operatorDecision: (decisionId: string, action: OperatorAction, reason: string, severityFloor?: SeverityFloor) => apiRequest<OperatorDecision>(`/api/incidents/${encodeURIComponent(decisionId)}/operator-decision`, { method: "POST", body: JSON.stringify({ action, reason, ...(severityFloor ? { severity_floor: severityFloor } : {}) }) }),
  evidence: (decisionId: string) => apiRequest<IncidentEvidenceFrame[]>(`/api/incidents/${encodeURIComponent(decisionId)}/evidence`),
  evidenceImage: (decisionId: string, evidenceId: string) => apiBinaryRequest(`/api/incidents/${encodeURIComponent(decisionId)}/evidence/${encodeURIComponent(evidenceId)}`),
};
