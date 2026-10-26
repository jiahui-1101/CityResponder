import React from "react";
import { AlertTriangle, ArrowRight, Route as RouteIcon, Server, ShieldAlert, X } from "lucide-react";
import { useResponseView } from "../hooks/useResponseView";
import { useIncidents } from "../hooks/useIncidents";
import { useIncidentLifecycle } from "../hooks/useIncidentLifecycle";
import { lifecycleRequests } from "../api/lifecycle";
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import type { RouteEvent, RouteIndexItem } from "../api/routes";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { LiveVisionPanel } from "../components/LiveVisionPanel";
import { DemoRouteImage } from "../components/DemoRouteImage";
import { ackText, ackTone, auditEventLabel, describeCommand, formatWhen, lifecycleLabel, ROUTE_HINTS, sentenceCase } from "../copy/glossary";
import { InfoHint, LabelWithHint } from "../components/InfoHint";

const formatTime = (value: string | null | undefined) => formatWhen(value, "Not available");
const routeTone = (route: RouteIndexItem): "success" | "danger" | "warning" | "neutral" => route.no_safe_route ? "danger" : route.status === "route_found" ? "success" : "warning";

export function FirefighterResponsePage() {
  const view = useResponseView();
  const incidents = useIncidents();
  const [selectedIncidentId, setSelectedIncidentId] = React.useState<string | null>(null);
  const lifecycle = useIncidentLifecycle(selectedIncidentId);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [pendingAction, setPendingAction] = React.useState<"EN_ROUTE" | "ARRIVED" | "RESOLVED" | null>(null);
  const actionTriggerRef = React.useRef<HTMLButtonElement | null>(null);
  const confirmButtonRef = React.useRef<HTMLButtonElement | null>(null);
  const [outcome, setOutcome] = React.useState("UNKNOWN");
  const [cause, setCause] = React.useState("");
  const [inspection, setInspection] = React.useState(false);
  const [notes, setNotes] = React.useState("");
  React.useEffect(() => { if (!selectedIncidentId && incidents.items[0]) setSelectedIncidentId(incidents.items[0].decision_id); }, [incidents.items, selectedIncidentId]);
  useLiveRefresh(["route_version", "traffic_command_invalidated"], () => view.refreshRoutes(), true, "response");
  useLiveRefresh(["actuator_command", "actuator_ack"], () => view.refreshActuatorActivity(), true, "response");
  const current = view.routes.find((route) => route.route_id === view.selectedRouteId) ?? null;
  async function performAction(action: "EN_ROUTE" | "ARRIVED" | "RESOLVED") {
    if (!selectedIncidentId) return false;
    setSubmitting(true); setActionError(null);
    try { await lifecycleRequests.responder(selectedIncidentId, { action, preliminary_outcome: action === "RESOLVED" ? outcome : undefined, probable_cause: action === "RESOLVED" ? cause : undefined, inspection_required: action === "RESOLVED" ? inspection : undefined, notes: action === "RESOLVED" ? notes : undefined }); await lifecycle.refresh(); return true; }
    catch (caught) { setActionError(caught instanceof Error ? caught.message : "Unable to submit responder action"); return false; }
    finally { setSubmitting(false); }
  }
  const currentStatus = lifecycle.lifecycle?.status ?? "DISPATCHED";
  const canEnRoute = currentStatus === "DISPATCHED" || currentStatus === "RESPONDING";
  const canArrive = currentStatus === "EN_ROUTE";
  const canResolve = currentStatus === "ARRIVED";
  React.useEffect(() => {
    if (!pendingAction) return;
    const frame = window.requestAnimationFrame(() => confirmButtonRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) closeActionDialog();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [pendingAction, submitting]);
  function openActionDialog(action: "EN_ROUTE" | "ARRIVED" | "RESOLVED", trigger: HTMLButtonElement) {
    actionTriggerRef.current = trigger;
    setActionError(null);
    setPendingAction(action);
  }
  function closeActionDialog() {
    if (submitting) return;
    setPendingAction(null);
    setActionError(null);
    window.requestAnimationFrame(() => actionTriggerRef.current?.focus());
  }
  async function confirmAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingAction) return;
    if (await performAction(pendingAction)) {
      setPendingAction(null);
      window.requestAnimationFrame(() => actionTriggerRef.current?.focus());
    }
  }
  const actionDetails = pendingAction ? {
    EN_ROUTE: { title: "Start heading to the incident?", label: "Confirm en route", description: "Record that you are on your way. The response timeline will be updated." },
    ARRIVED: { title: "Confirm you have arrived?", label: "Confirm arrival", description: "Record your arrival at the incident location." },
    RESOLVED: { title: "Finish this response?", label: "Resolve incident", description: "Record the field outcome and close this response." },
  }[pendingAction] : null;
  return <div className="response-page"><div className="page-header"><div><p className="eyebrow">Firefighter workspace</p><h2>Response &amp; routing</h2><p>Live route guidance, response stage, and field device status.</p></div><div className="overview-refresh"><span>{view.lastRefreshedAt ? `Updated ${formatTime(view.lastRefreshedAt)}` : "Not refreshed yet"}</span><button className="button button-secondary" type="button" onClick={() => void view.refresh()} disabled={view.loading} aria-label={view.loading ? "Refreshing response status" : "Refresh response status"} title="Refresh response status"><RouteIcon size={15} />{view.loading ? "Refreshing" : "Refresh"}</button></div></div>{view.errors.length ? <div className="section-error" role="alert"><AlertTriangle size={15} />{view.errors.join(" · ")}</div> : null}
    <section className="overview-section"><SectionHeader title="Active incident" description="Step-by-step response progress. Complete each stage in order." action={<InfoHint label="Response progress" text="Field status moves through Dispatched, On the way, Arrived, and Resolved." />} />{incidents.error ? <div className="section-error" role="alert">{incidents.error}</div> : <div className="route-selector"><label htmlFor="incident-select">Incident</label><select id="incident-select" value={selectedIncidentId ?? ""} onChange={(event) => setSelectedIncidentId(event.target.value || null)}><option value="">Select incident</option>{incidents.items.map((item) => <option key={item.decision_id} value={item.decision_id}>{item.decision_id} · {item.final_severity ? sentenceCase(item.final_severity) : "Unresolved"}</option>)}</select></div>}</section>
    <section className="overview-section"><SectionHeader title="Live camera preview" description="Overhead camera with observation-only detection and road overlays." /><LiveVisionPanel compact /></section>
    <section className="overview-section current-route-section"><SectionHeader title="Current route" description="Static demo route image selected from the latest backend route state." />{view.loading && !view.routes.length ? <LoadingState label="Loading route state" /> : !view.routes.length ? <Card className="overview-card"><EmptyState title="No response route has been calculated yet" body="No immutable route versions are available, so no demo route image can be selected." /></Card> : <><div className="route-selector"><label htmlFor="route-select">Persisted route</label><select id="route-select" value={view.selectedRouteId ?? ""} onChange={(event) => view.selectRoute(event.target.value)}>{view.routes.map((route) => <option value={route.route_id} key={route.route_id}>{route.route_id} · v{route.latest_version}</option>)}</select></div>{current ? <><Card className="current-route-map-card"><DemoRouteImage route={current} /></Card><RouteSummary route={current} />{current.route_changed && current.previous_version !== null ? <div className="reroute-banner" role="status"><strong>REROUTED · v{current.latest_version}</strong><span>{current.previous_version ? `v${current.previous_version} → v${current.latest_version}` : "New route"} · {current.reasons[0] ?? "Route conditions changed"}</span></div> : null}</> : <Card className="overview-card"><EmptyState title="Route selection unavailable" body="A route exists, but no current projection is selected for display." /></Card>}</>}</section>
    {current ? <><section className="overview-section route-path-support"><SectionHeader title="Route path details" description="Step-by-step view of the current route." /><Card className="overview-card route-support-card"><RoutePath route={current} /></Card></section><section className="overview-section"><SectionHeader title="Traffic lights & servo gate" description="Latest device activity and confirmation." action={<InfoHint label="Field controller" text="The field controller sends commands to connected traffic lights, sirens, and the servo gate." />} /><ActuatorPanel actuator={view.actuators} /></section><section className="overview-section"><SectionHeader title="Route history" description="Earlier versions of this route." /><HistoryPanel history={view.history} currentVersion={current.latest_version} /></section></> : null}
    <section className="overview-section"><SectionHeader title="Response progress" description="Update the incident as you travel, arrive, and finish your response." /><Card className="overview-card lifecycle-card"><div className="lifecycle-status-row"><div><span>Current status</span><strong>{lifecycleLabel(currentStatus)}</strong></div><StatusBadge tone={currentStatus === "RESOLVED" ? "success" : "info"}>{lifecycleLabel(currentStatus)}</StatusBadge></div><div className="decision-actions"><button className="button button-secondary" type="button" disabled={!selectedIncidentId || !canEnRoute || submitting} onClick={(event) => openActionDialog("EN_ROUTE", event.currentTarget)}>Mark on the way</button><button className="button button-secondary" type="button" disabled={!selectedIncidentId || !canArrive || submitting} onClick={(event) => openActionDialog("ARRIVED", event.currentTarget)}>Mark arrived</button><button className="button button-primary" type="button" disabled={!selectedIncidentId || !canResolve || submitting} onClick={(event) => openActionDialog("RESOLVED", event.currentTarget)}>Resolve incident</button></div><p className="lifecycle-hint">{!selectedIncidentId ? "Select an incident to update its progress." : canEnRoute ? "When you begin travelling, mark yourself on the way." : canArrive ? "Once on site, confirm your arrival." : canResolve ? "When the situation is handled, record the outcome and finish." : "This response has been completed."}</p></Card></section>
    <section className="overview-section"><SectionHeader title="Recent response activity" description="A readable timeline of route and device updates." /><Card className="overview-card route-support-card"><EventPanel events={view.events} /></Card></section>
    {pendingAction && actionDetails ? <div className="operator-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeActionDialog(); }}><section className="operator-dialog response-action-dialog" role="dialog" aria-modal="true" aria-labelledby="response-action-title" aria-describedby="response-action-description"><div className="operator-dialog-heading"><div><h3 id="response-action-title">{actionDetails.title}</h3><p id="response-action-description">{actionDetails.description}</p></div><button className="icon-button" type="button" aria-label="Close confirmation" disabled={submitting} onClick={closeActionDialog}><X size={17} aria-hidden="true" /></button></div><form className="operator-dialog-form lifecycle-dialog-form" onSubmit={(event) => void confirmAction(event)}>{pendingAction === "RESOLVED" ? <div className="lifecycle-form"><label>What was the outcome?<select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="UNKNOWN">Not sure yet</option><option value="FIRE">Fire confirmed</option><option value="FALSE_ALARM">False alarm</option></select></label><label>What do you think caused it?<input value={cause} onChange={(event) => setCause(event.target.value)} placeholder="Optional" /></label><label className="checkbox-label"><input type="checkbox" checked={inspection} onChange={(event) => setInspection(event.target.checked)} />A follow-up inspection is needed</label><label>Notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Add any useful details for the response record." /></label></div> : null}{actionError ? <p className="operator-dialog-error" role="alert"><AlertTriangle size={14} />{actionError}</p> : null}<div className="operator-dialog-actions"><button className="button button-secondary" type="button" disabled={submitting} onClick={closeActionDialog}>Go back</button><button ref={confirmButtonRef} className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Saving…" : actionDetails.label}</button></div></form></section></div> : null}
  </div>;
}

function RouteSummary({ route }: { route: RouteIndexItem }) {
  const blockedEdge = [...route.reasons, ...route.warnings].find((value) => /edge|blocked|conflict|unavailable/i.test(value)) ?? "None reported";
  const rerouteReason = route.route_changed ? (route.reasons[0] ?? "Route conditions changed") : "No reroute recorded";
  const status = route.no_safe_route ? "No safe route" : route.status === "route_found" ? "Route found" : sentenceCase(route.status);
  return <Card className={`route-summary ${route.no_safe_route ? "route-unsafe" : ""}`}><div className="route-summary-heading"><div><span className="route-label">Current route · Version {route.latest_version}</span><h3>{route.node_path.length ? route.node_path.join(" → ") : route.route_id}</h3><p className="route-summary-subtitle">Route {route.route_id}{route.previous_version ? ` · Version ${route.previous_version} → ${route.latest_version}` : ""}</p></div><StatusBadge tone={routeTone(route)}>{status}</StatusBadge></div>{route.no_safe_route ? <div className="no-safe-banner"><ShieldAlert size={20} /><div><strong>No safe route is available</strong><span>All known routes are blocked.</span></div></div> : null}<div className="route-facts"><Fact label="Traffic corridor" value={route.no_safe_route ? "Unavailable" : "Selected route"} /><Fact label="Estimated travel score" value={route.total_edge_cost === null ? "Unavailable" : String(route.total_edge_cost)} hint={ROUTE_HINTS.travelScore} /><Fact label="Blocked road segment" value={blockedEdge} /><Fact label="Reroute reason" value={rerouteReason} /><Fact label="Last update" value={formatTime(route.created_at)} /></div></Card>;
}

function RoutePath({ route }: { route: RouteIndexItem }) {
  if (!route.node_path.length) return <EmptyState title="No route path available" body="The current route projection contains no usable node sequence." />;
  return <div className="schematic-wrap"><div className="schematic-path" aria-label="Route steps">{route.node_path.map((node, index) => <span className="path-group" key={`${node}-${index}`}><span className="path-node"><span className="path-step">Stop {index + 1}</span><strong>{node}</strong></span>{index < route.node_path.length - 1 ? <span className="path-link"><ArrowRight size={15} /><small>{route.edge_path[index] ?? "Next road segment"}</small></span> : null}</span>)}</div></div>;
}

function ActuatorPanel({ actuator }: { actuator: ReturnType<typeof useResponseView>["actuators"] }) {
  if (!actuator) return <Card className="overview-card route-support-card"><EmptyState title="Device updates aren’t available yet" body="The latest traffic light and servo gate status could not be loaded." /></Card>;
  const latest = actuator.commands[0];
  return <Card className="overview-card route-support-card"><div className="actuator-node"><Server size={20} /><div><strong>Field device activity</strong><span>{actuator.node_status.available ? "A device response has been recorded." : "No device response has been recorded yet."}</span></div><StatusBadge tone={ackTone(actuator.node_status.last_ack_status)}>{ackText(actuator.node_status.last_ack_status)}</StatusBadge></div>{latest ? <div className="actuator-detail"><Fact label="Recent action" value={describeCommand(latest)} /><Fact label="Command sent" value={formatTime(latest.sent_at)} /><Fact label="Device response" value={ackText(latest.ack_status)} /><Fact label="Response time" value={formatTime(latest.ack_at)} /></div> : <EmptyState title="No device activity yet" body="Traffic light or servo gate updates will appear here when recorded." />}</Card>;
}

function HistoryPanel({ history, currentVersion }: { history: RouteEvent[]; currentVersion: number }) {
  if (!history.length) return <Card className="overview-card"><EmptyState title="No route history" body="No immutable route versions were returned." /></Card>;
  return <Card className="overview-card route-support-card history-card"><div className="route-history-table"><div className="route-history-head"><span>Version</span><span>Status</span><span>Path</span><span>Updated</span></div>{history.map((event) => { const payload = event.payload; const version = Number(payload.version); const path = Array.isArray(payload.node_path) ? payload.node_path.join(" → ") : "Unavailable"; return <div className={`route-history-row ${version === currentVersion ? "current-version" : ""}`} key={event.id}><span><strong>v{version}</strong>{version === currentVersion ? <Badge tone="info">Current</Badge> : null}</span><span>{payload.no_safe_route ? "No safe route" : sentenceCase(String(payload.route_status ?? "Unavailable"))}</span><span>{path}</span><time dateTime={event.created_at}>{formatTime(event.created_at)}</time><small>{payload.route_changed ? "Reroute recorded" : "No route change"}{payload.invalidates_prior_commands ? ` · ${ROUTE_HINTS.priorCommandsInvalidated}` : ""}</small></div>; })}</div></Card>;
}

function EventPanel({ events }: { events: RouteEvent[] }) {
  if (!events.length) return <EmptyState title="No response activity" body="No route or actuator events have been recorded yet." />;
  return <div className="event-list">{events.slice(0, 12).map((event) => <div className="event-row" key={event.id}><div><strong>{auditEventLabel(event.event_type)}</strong><span title={`${event.entity_type} · ${event.entity_id}`}>Response update</span></div><time dateTime={event.created_at}>{formatTime(event.created_at)}</time><small>{event.human_readable_reason ?? (event.reason_code ? sentenceCase(event.reason_code) : "No additional details were recorded.")}</small></div>)}</div>;
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) { return <div className="fact">{hint ? <LabelWithHint label={label} hint={hint} /> : <span>{label}</span>}<strong>{value}</strong></div>; }
