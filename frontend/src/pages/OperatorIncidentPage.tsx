import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Clock3, FileText, ShieldCheck, X } from "lucide-react";
import { incidentRequests, type IncidentEvidenceFrame } from "../api/incidents";
import { useIncidentDetail } from "../hooks/useIncidents";
import { useAuth } from "../auth/AuthContext";
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import { OperatorDecisionPanel, type OperatorDecisionAction } from "../components/OperatorDecisionPanel";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { useEscapeDismiss } from "../hooks/useEscapeDismiss";
import { useIncidentLifecycle } from "../hooks/useIncidentLifecycle";
import { lifecycleRequests } from "../api/lifecycle";

const formatTime = (value: string) => new Date(value).toLocaleString();
const outcomeTone = (value: string): "success" | "warning" | "danger" | "neutral" => value === "CONFIRM" || value === "confirmed" ? "success" : value === "REJECT" || value === "CANCEL" || value === "not_confirmed" ? "warning" : value === "unresolved" ? "danger" : "neutral";
const incidentActionMap = { confirm: "CONFIRM", reject: "REJECT", cancel: "CANCEL" } as const;
const lifecycleActionMap = { start_response: "START_RESPONSE", manual_stop: "MANUAL_STOP", restore_safe_default: "RESTORE_SAFE_DEFAULT" } as const;

export function OperatorIncidentPage() {
  const { decisionId = "" } = useParams();
  const { projection, history, loading, error, refresh } = useIncidentDetail(decisionId);
  const [evidence, setEvidence] = useState<IncidentEvidenceFrame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({});
  const [selectedEvidence, setSelectedEvidence] = useState<IncidentEvidenceFrame | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const { role } = useAuth();
  const canDecide = role === "OPERATOR" || role === "ADMIN";
  const lifecycle = useIncidentLifecycle(decisionId);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [feedbackOutcome, setFeedbackOutcome] = useState<"VERIFIED_FIRE" | "VERIFIED_FALSE_ALARM">("VERIFIED_FIRE");
  useEscapeDismiss(selectedEvidence !== null, () => setSelectedEvidence(null));
  useLiveRefresh(["incident_decision", "operator_decision"], (event) => event.entityId && event.entityId !== decisionId ? undefined : refresh(), true, "incident-detail");
  useLiveRefresh(["incident_evidence_retained"], (event) => event.entityId && event.entityId !== decisionId ? undefined : loadEvidence(), true, "incident-detail");

  async function loadEvidence() { try { const next = await incidentRequests.evidence(decisionId); setEvidence(next); const loaded = await Promise.all(next.map(async (item) => { try { return [item.evidence_id, URL.createObjectURL(await incidentRequests.evidenceImage(decisionId, item.evidence_id))] as const; } catch { return null; } })); const nextUrls = Object.fromEntries(loaded.filter((item): item is readonly [string, string] => item !== null)); setImageUrls((current) => { Object.values(current).forEach((url) => URL.revokeObjectURL(url)); return nextUrls; }); setEvidenceError(null); } catch (caught) { setEvidenceError(caught instanceof Error ? caught.message : "Unable to load retained evidence"); } }
  useEffect(() => { void loadEvidence(); }, [decisionId]);

  async function performOperatorAction(action: OperatorDecisionAction, reason: string) {
    if (action in incidentActionMap) {
      await incidentRequests.operatorDecision(decisionId, incidentActionMap[action as keyof typeof incidentActionMap], reason);
      await refresh();
      return;
    }
    await lifecycleRequests.operator(decisionId, lifecycleActionMap[action as keyof typeof lifecycleActionMap], reason);
    await Promise.all([lifecycle.refresh(), refresh()]);
  }
  async function verifyOutcome() {
    setLifecycleBusy(true); setLifecycleError(null);
    try { await lifecycleRequests.feedback(decisionId, feedbackOutcome, "Operator verified responder outcome"); await lifecycle.refresh(); }
    catch (caught) { setLifecycleError(caught instanceof Error ? caught.message : "Unable to verify outcome"); }
    finally { setLifecycleBusy(false); }
  }

  if (loading) return <LoadingState label="Loading incident record" />;
  if (error && !projection) return <ErrorState title={error.includes("404") ? "Incident not found" : "Unable to load incident"} body={error} />;
  if (!projection) return <EmptyState title="Incident unavailable" body="No immutable projection was returned for this decision." />;
  const automatic = projection.automatic_decision;
  return <div className="incident-detail-page"><Link className="back-link" to="/incidents"><ArrowLeft size={15} />Back to incidents</Link><div className="page-header"><div><p className="eyebrow">Incident command view</p><h2>{projection.incident_id}</h2><p>Automatic evidence remains separate from operator outcomes.</p></div><StatusBadge tone={outcomeTone(projection.projected_outcome)}>{projection.projected_outcome}</StatusBadge></div>
    <section className="incident-summary-grid"><Card className="incident-summary-card"><SectionHeader title="Decision summary" /><div className="summary-facts"><Fact label="Automatic confirmation" value={automatic.incident_confirmed === null ? "Unresolved" : automatic.incident_confirmed ? "Confirmed" : "Not confirmed"} /><Fact label="Fusion confidence" value={automatic.fusion_confidence.confidence_score === null ? `Unavailable · ${automatic.fusion_confidence.status}` : `${automatic.fusion_confidence.confidence_score.toFixed(2)} / 100`} /><Fact label="Projected outcome" value={projection.projected_outcome} /><Fact label="Final severity" value={projection.final_severity ?? "Unavailable"} /><Fact label="Critical override" value={automatic.critical_override_applied ? "Applied · person in hazard zone" : "Not applied"} /><Fact label="Decision status" value={automatic.decision_status} /><Fact label="Evaluated" value={formatTime(projection.evaluated_at)} /></div></Card><Card className="incident-summary-card"><SectionHeader title="Evidence and reasons" /><ReasonList values={[...automatic.fusion_confidence.reasons, ...automatic.reasons, ...automatic.warnings, ...projection.warnings]} /></Card></section>
    <section className="overview-section">
      {canDecide ? <OperatorDecisionPanel status={projection.latest_operator_action?.resulting_operator_outcome ?? automatic.decision_status} lifecycle={lifecycle.lifecycle?.status ?? ""} incidentId={projection.incident_id} onAction={performOperatorAction} /> : <Card className="decision-card"><p className="read-only-note">Current lifecycle: <strong>{lifecycle.lifecycle?.status ?? "DISPATCHED"}</strong></p><p className="read-only-note">Your role can review this incident but cannot submit manual decisions.</p></Card>}
      {lifecycle.lifecycle?.status === "RESOLVED" && canDecide ? <Card className="decision-card operator-feedback-card"><div className="decision-actions"><select value={feedbackOutcome} onChange={(event) => setFeedbackOutcome(event.target.value as typeof feedbackOutcome)}><option value="VERIFIED_FIRE">Verified fire</option><option value="VERIFIED_FALSE_ALARM">Verified false alarm</option></select><button className="button button-primary" type="button" disabled={lifecycleBusy} onClick={() => void verifyOutcome()}>Verify and close</button></div>{lifecycleError ? <div className="section-error" role="alert"><AlertCircle size={15} />{lifecycleError}</div> : null}</Card> : null}
    </section>
    <section className="overview-section"><SectionHeader title="Immutable history" description="Chronological Event-store records" /><Card className="history-card">{history.length ? <div className="history-list">{history.map((event) => <div className="history-item" key={event.id}><div className="history-icon"><Clock3 size={15} /></div><div><strong>{event.event_type}</strong><span>{formatTime(event.created_at)} · {event.entity_type} / {event.entity_id}</span><p>{event.human_readable_reason ?? event.reason_code ?? "No reason recorded"}</p></div>{event.payload.action ? <Badge tone="neutral">{String(event.payload.action)}</Badge> : null}</div>)}</div> : <EmptyState title="No history returned" body="The incident has no readable immutable event history." />}</Card></section>
    <EvidenceSection evidence={evidence} imageUrls={imageUrls} error={evidenceError} onSelect={setSelectedEvidence} />
    {selectedEvidence ? <EvidenceModal imageUrl={imageUrls[selectedEvidence.evidence_id]} evidence={selectedEvidence} onClose={() => setSelectedEvidence(null)} /> : null}
  </div>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
function ReasonList({ values }: { values: string[] }) { const unique = [...new Set(values.filter(Boolean))]; return unique.length ? <ul className="reason-list">{unique.map((value) => <li key={value}><FileText size={14} />{value}</li>)}</ul> : <p className="muted-copy">No reasons or warnings were returned.</p>; }
function EvidenceSection({ evidence, imageUrls, error, onSelect }: { evidence: IncidentEvidenceFrame[]; imageUrls: Record<string, string>; error: string | null; onSelect: (item: IncidentEvidenceFrame) => void }) { return <section className="overview-section"><SectionHeader title="Annotated evidence" description={`${evidence.length} / 5 retained frame(s) · continuous camera video is not permanently stored`} />{error ? <div className="section-error" role="alert"><AlertCircle size={15} />{error}</div> : evidence.length === 0 ? <Card><EmptyState title="No retained annotated evidence frames" body="Only explicitly selected annotated incident evidence is retained; no retention duration is defined." /></Card> : <Card className="evidence-card"><div className="evidence-privacy-note"><ShieldCheck size={15} />Selected evidence only · maximum five frames per incident</div><div className="evidence-grid">{evidence.map((item) => <button className="evidence-thumb" type="button" key={item.evidence_id} onClick={() => onSelect(item)}><img src={imageUrls[item.evidence_id]} alt={`Annotated evidence frame ${item.frame_index}`} /><span>Frame {item.frame_index} · {formatTime(item.captured_at)}</span></button>)}</div></Card>}</section>; }
function EvidenceModal({ imageUrl, evidence, onClose }: { imageUrl?: string; evidence: IncidentEvidenceFrame; onClose: () => void }) { return <div className="modal-backdrop" role="presentation" onClick={onClose}><div className="evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-modal-title" onClick={(event) => event.stopPropagation()}><div className="modal-heading"><div><p className="eyebrow">Retained evidence</p><h3 id="evidence-modal-title">Frame {evidence.frame_index}</h3></div><button autoFocus className="icon-button" type="button" aria-label="Close evidence" onClick={onClose}><X size={17} /></button></div>{imageUrl ? <img className="evidence-large" src={imageUrl} alt={`Annotated evidence frame ${evidence.frame_index}`} /> : <p className="muted-copy">Evidence image unavailable.</p>}<div className="evidence-modal-meta"><Fact label="Captured" value={formatTime(evidence.captured_at)} /><Fact label="Stored" value={formatTime(evidence.stored_at)} /><Fact label="Source" value={evidence.source_camera_id ?? "Unavailable"} /><Fact label="Content type" value={evidence.content_type} /></div>{evidence.reason_codes.length ? <ReasonList values={evidence.reason_codes} /> : null}<details className="audit-raw"><summary>Annotation metadata</summary><pre>{JSON.stringify(evidence.annotation_metadata, null, 2)}</pre></details></div></div>; }
