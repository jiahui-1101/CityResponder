import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Route as RouteIcon, Server, ShieldAlert } from "lucide-react";
import { useResponseView } from "../hooks/useResponseView";
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import type { RouteEvent, RouteIndexItem } from "../api/routes";
import { useLiveRefresh } from "../live/useLiveRefresh";

const formatTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : "Unavailable";
const routeTone = (route: RouteIndexItem): "success" | "danger" | "warning" | "neutral" => route.no_safe_route ? "danger" : route.status === "route_found" ? "success" : "warning";

export function FirefighterResponsePage() {
  const view = useResponseView();
  useLiveRefresh(["route_version", "traffic_command_invalidated"], () => view.refreshRoutes(), true, "response");
  useLiveRefresh(["actuator_command", "actuator_ack"], () => view.refreshActuatorActivity(), true, "response");
  const current = view.routes.find((route) => route.route_id === view.selectedRouteId) ?? null;
  return <div className="response-page"><div className="page-header"><div><p className="eyebrow">Firefighter workspace</p><h2>Response / Routing</h2><p>Read-only route and infrastructure state from immutable backend projections.</p></div><div className="overview-refresh"><span>{view.lastRefreshedAt ? `Updated ${formatTime(view.lastRefreshedAt)}` : "Not refreshed yet"}</span><button className="button button-secondary" type="button" onClick={() => void view.refresh()} disabled={view.loading}><RouteIcon size={15} />{view.loading ? "Refreshing" : "Refresh"}</button></div></div>{view.errors.length ? <div className="section-error" role="alert"><AlertTriangle size={15} />{view.errors.join(" · ")}</div> : null}
    <section className="overview-section"><SectionHeader title="Current route" description="Latest persisted route projection; no route is inferred or recalculated" />{view.loading && !view.routes.length ? <LoadingState label="Loading route state" /> : !view.routes.length ? <Card className="overview-card"><EmptyState title="No response route has been calculated yet" body="No immutable route versions are available." /></Card> : <><div className="route-selector"><label htmlFor="route-select">Persisted route</label><select id="route-select" value={view.selectedRouteId ?? ""} onChange={(event) => view.selectRoute(event.target.value)}>{view.routes.map((route) => <option value={route.route_id} key={route.route_id}>{route.route_id} · v{route.latest_version}</option>)}</select></div>{current ? <RouteSummary route={current} /> : null}</>}</section>
    {current ? <><section className="overview-section"><SectionHeader title="Route path" description="Schematic sequence only — not geographical geometry" /><Card className="overview-card"><RoutePath route={current} /></Card></section><section className="overview-section"><SectionHeader title="Infrastructure / actuator state" description="AC1 command and ACK projection" /><ActuatorPanel actuator={view.actuators} /></section><section className="overview-section"><SectionHeader title="Route history" description="All immutable versions for the selected route" /><HistoryPanel history={view.history} currentVersion={current.latest_version} /></section></> : null}
    <section className="overview-section"><SectionHeader title="Recent response activity" description="Immutable response-related events only" /><Card className="overview-card"><EventPanel events={view.events} /></Card></section>
  </div>;
}

function RouteSummary({ route }: { route: RouteIndexItem }) {
  return <Card className={`route-summary ${route.no_safe_route ? "route-unsafe" : ""}`}><div className="route-summary-heading"><div><span className="route-label">Current / latest version</span><h3>{route.route_id} <small>v{route.latest_version}</small></h3></div><StatusBadge tone={routeTone(route)}>{route.no_safe_route ? "NO_SAFE_ROUTE" : route.status}</StatusBadge></div>{route.no_safe_route ? <div className="no-safe-banner"><ShieldAlert size={20} /><div><strong>No safe routing path is currently available</strong><span>Excluded or unresolved edges are not presented as a usable route.</span></div></div> : null}<div className="route-facts"><Fact label="Source → destination" value={`${route.source_node_id} → ${route.destination_node_id}`} /><Fact label="Persisted" value={formatTime(route.created_at)} /><Fact label="Route changed" value={route.route_changed ? "Yes" : "No"} /><Fact label="Distance" value={route.total_distance_cm === null ? "Unavailable" : `${route.total_distance_cm} cm`} /><Fact label="Weighted routing cost" value={route.total_edge_cost === null ? "Unavailable" : String(route.total_edge_cost)} /></div></Card>;
}

function RoutePath({ route }: { route: RouteIndexItem }) {
  if (!route.node_path.length) return <EmptyState title="No route path available" body="The current route projection contains no usable node sequence." />;
  return <div className="schematic-wrap"><p className="schematic-note">Ordered node and edge sequence</p><div className="schematic-path">{route.node_path.map((node, index) => <span className="path-group" key={`${node}-${index}`}><span className="path-node"><RouteIcon size={14} />{node}</span>{index < route.node_path.length - 1 ? <span className="path-link"><ArrowRight size={15} /><small>{route.edge_path[index] ?? "Unavailable edge"}</small></span> : null}</span>)}</div></div>;
}

function ActuatorPanel({ actuator }: { actuator: ReturnType<typeof useResponseView>["actuators"] }) {
  if (!actuator) return <Card className="overview-card"><EmptyState title="Actuator state unavailable" body="No AC1 actuator projection was returned." /></Card>;
  const latest = actuator.commands[0];
  return <Card className="overview-card"><div className="actuator-node"><Server size={20} /><div><strong>{actuator.node_status.node_id}</strong><span>{actuator.node_status.available ? "ACK history available" : "No ACK history yet"}</span></div><StatusBadge tone={actuator.node_status.available ? "success" : "neutral"}>{actuator.node_status.last_ack_status ?? "Unavailable"}</StatusBadge></div>{latest ? <div className="actuator-detail"><Fact label="Latest command" value={latest.command_type} /><Fact label="Target" value={latest.node_id} /><Fact label="Sent" value={formatTime(latest.sent_at)} /><Fact label="ACK status" value={latest.ack_status ?? "No ACK"} /><Fact label="ACK time" value={formatTime(latest.ack_at)} /></div> : <EmptyState title="No actuator commands" body="No command or ACK has been recorded yet." />}</Card>;
}

function HistoryPanel({ history, currentVersion }: { history: RouteEvent[]; currentVersion: number }) {
  if (!history.length) return <Card className="overview-card"><EmptyState title="No route history" body="No immutable route versions were returned." /></Card>;
  return <Card className="overview-card history-card"><div className="route-history-table"><div className="route-history-head"><span>Version</span><span>Status</span><span>Path</span><span>Timestamp</span></div>{history.map((event) => { const payload = event.payload; const version = Number(payload.version); const path = Array.isArray(payload.node_path) ? payload.node_path.join(" → ") : "Unavailable"; return <div className={`route-history-row ${version === currentVersion ? "current-version" : ""}`} key={event.id}><span><strong>v{version}</strong>{version === currentVersion ? <Badge tone="info">Current</Badge> : null}</span><span>{payload.no_safe_route ? "NO_SAFE_ROUTE" : String(payload.route_status ?? "Unavailable")}</span><span>{path}</span><time dateTime={event.created_at}>{formatTime(event.created_at)}</time><small>{payload.route_changed ? "Reroute recorded" : "No route change"}{payload.invalidates_prior_commands ? " · prior commands invalidated" : ""}</small></div>; })}</div></Card>;
}

function EventPanel({ events }: { events: RouteEvent[] }) {
  if (!events.length) return <EmptyState title="No response activity" body="No route or actuator events have been recorded yet." />;
  return <div className="event-list">{events.slice(0, 12).map((event) => <div className="event-row" key={event.id}><div><strong>{event.event_type}</strong><span>{event.entity_type} · {event.entity_id}</span></div><time dateTime={event.created_at}>{formatTime(event.created_at)}</time><small>{event.human_readable_reason ?? event.reason_code ?? "No reason recorded"}</small></div>)}</div>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
