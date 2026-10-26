import React from "react";
import {
  AlertTriangle,
  ArrowRight,
  Route as RouteIcon,
  Server,
  ShieldAlert,
} from "lucide-react";
import { useResponseView } from "../hooks/useResponseView";
import { useIncidents } from "../hooks/useIncidents";
import { useIncidentLifecycle } from "../hooks/useIncidentLifecycle";
import { lifecycleRequests } from "../api/lifecycle";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui";
import type { RouteEvent, RouteIndexItem } from "../api/routes";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { LiveVisionPanel } from "../components/LiveVisionPanel";
import { DemoRouteImage } from "../components/DemoRouteImage";
import {
  formatWhen,
  sentenceCase,
  describeCommand,
  ackText,
  ackTone,
  auditEventLabel,
  lifecycleLabel,
  ROUTE_HINTS,
  TECHNICAL_HINTS,
} from "../copy/glossary";
import { InfoHint, LabelWithHint } from "../components/InfoHint";

const routeTone = (
  route: RouteIndexItem,
): "success" | "danger" | "warning" | "neutral" =>
  route.no_safe_route
    ? "danger"
    : route.status === "route_found"
    ? "success"
    : "warning";

export function FirefighterResponsePage() {
  const view = useResponseView();
  const incidents = useIncidents();
  const [selectedIncidentId, setSelectedIncidentId] = React.useState<
    string | null
  >(null);
  const lifecycle = useIncidentLifecycle(selectedIncidentId);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [outcome, setOutcome] = React.useState("UNKNOWN");
  const [cause, setCause] = React.useState("");
  const [inspection, setInspection] = React.useState(false);
  const [notes, setNotes] = React.useState("");

  React.useEffect(() => {
    if (!selectedIncidentId && incidents.items[0]) {
      setSelectedIncidentId(incidents.items[0].decision_id);
    }
  }, [incidents.items, selectedIncidentId]);

  useLiveRefresh(
    ["route_version", "traffic_command_invalidated"],
    () => view.refreshRoutes(),
    true,
    "response",
  );
  useLiveRefresh(
    ["actuator_command", "actuator_ack"],
    () => view.refreshActuatorActivity(),
    true,
    "response",
  );

  const current =
    view.routes.find((route) => route.route_id === view.selectedRouteId) ??
    null;

  async function performAction(action: "EN_ROUTE" | "ARRIVED" | "RESOLVED") {
    if (!selectedIncidentId) return;
    setSubmitting(true);
    setActionError(null);
    try {
      await lifecycleRequests.responder(selectedIncidentId, {
        action,
        preliminary_outcome: action === "RESOLVED" ? outcome : undefined,
        probable_cause: action === "RESOLVED" ? cause : undefined,
        inspection_required: action === "RESOLVED" ? inspection : undefined,
        notes: action === "RESOLVED" ? notes : undefined,
      });
      await lifecycle.refresh();
    } catch (caught) {
      setActionError(
        caught instanceof Error
          ? caught.message
          : "Unable to submit responder action",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const currentStatus = lifecycle.lifecycle?.status ?? "DISPATCHED";
  const canEnRoute =
    currentStatus === "DISPATCHED" || currentStatus === "RESPONDING";
  const canArrive = currentStatus === "EN_ROUTE";
  const canResolve = currentStatus === "ARRIVED";

  return (
    <div className="response-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Firefighter workspace</p>
          <h2>Response &amp; routing</h2>
          <p>Live route guidance, response stage, and field device status.</p>
        </div>
        <div className="overview-refresh">
          <span>
            {view.lastRefreshedAt
              ? `Updated ${formatWhen(view.lastRefreshedAt)}`
              : "Not refreshed yet"}
          </span>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void view.refresh()}
            disabled={view.loading}
            aria-label={view.loading ? "Refreshing response status" : "Refresh response status"}
            title="Refresh response status"
          >
            <RouteIcon size={15} />
            {view.loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {view.errors.length ? (
        <div className="section-error" role="alert">
          <AlertTriangle size={15} />
          {view.errors.join(" · ")}
        </div>
      ) : null}

      <section className="overview-section">
        <SectionHeader
          title="Active incident"
          description="Step-by-step response progress. Complete each stage in order."
          action={
            <InfoHint
              label="Response progress"
              text="Field status must advance in order: Dispatched → On the way → Arrived → Resolved."
            />
          }
        />
        {incidents.error ? (
          <div className="section-error" role="alert">
            {incidents.error}
          </div>
        ) : (
          <div className="route-selector">
            <label htmlFor="incident-select">Incident</label>
            <select
              id="incident-select"
              value={selectedIncidentId ?? ""}
              onChange={(event) =>
                setSelectedIncidentId(event.target.value || null)
              }
            >
              <option value="">Select incident</option>
              {incidents.items.map((item) => (
                <option key={item.decision_id} value={item.decision_id}>
                  {item.decision_id} ·{" "}
                  {item.final_severity
                    ? sentenceCase(item.final_severity)
                    : "Severity pending"}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      <section className="overview-section">
        <SectionHeader
          title="Live camera preview"
          description="Overhead camera view with fire and obstacle detection overlays."
        />
        <LiveVisionPanel compact />
      </section>

      <section className="overview-section current-route-section">
        <SectionHeader
          title="Current route"
          description="Route guidance selected from current road conditions."
        />
        {view.loading && !view.routes.length ? (
          <LoadingState label="Loading route state" />
        ) : !view.routes.length ? (
          <Card className="overview-card">
            <EmptyState
              title="No response route has been calculated yet"
              body="No saved route versions are available. Check the incident status or refresh."
            />
          </Card>
        ) : (
          <>
            <div className="route-selector">
              <label htmlFor="route-select">Saved route</label>
              <select
                id="route-select"
                value={view.selectedRouteId ?? ""}
                onChange={(event) => view.selectRoute(event.target.value)}
              >
                {view.routes.map((route) => (
                  <option value={route.route_id} key={route.route_id}>
                    {route.route_id} · Version {route.latest_version}
                  </option>
                ))}
              </select>
            </div>
            {current ? (
              <>
                <Card className="current-route-map-card">
                  <DemoRouteImage route={current} />
                </Card>
                <RouteSummary route={current} />
                {current.route_changed && current.previous_version !== null ? (
                  <div className="reroute-banner" role="status">
                    <strong>REROUTED · Version {current.latest_version}</strong>
                    <span>
                      {current.previous_version
                        ? `Version ${current.previous_version} → Version ${current.latest_version}`
                        : "New route"}{" "}
                      · {current.reasons[0] ?? "Route conditions changed"}
                    </span>
                  </div>
                ) : null}
              </>
            ) : (
              <Card className="overview-card">
                <EmptyState
                  title="Route selection unavailable"
                  body="A route exists, but no current view is selected for display."
                />
              </Card>
            )}
          </>
        )}
      </section>

      {current ? (
        <>
          <section className="overview-section route-path-support">
            <SectionHeader
              title="Route path details"
              description="Sequence of intersections and road segments for this route."
            />
            <Card className="overview-card">
              <RoutePath route={current} />
            </Card>
          </section>

          <section className="overview-section">
            <SectionHeader
              title="Field controller &amp; devices"
              description="Traffic light, barrier, and siren device status."
              action={
                <InfoHint
                  label="Field controller"
                  text={TECHNICAL_HINTS.fieldController}
                />
              }
            />
            <ActuatorPanel actuator={view.actuators} />
          </section>

          <section className="overview-section">
            <SectionHeader
              title="Route history"
              description="History of route updates for this incident."
            />
            <HistoryPanel
              history={view.history}
              currentVersion={current.latest_version}
            />
          </section>
        </>
      ) : null}

      <section className="overview-section">
        <SectionHeader
          title="Response progress"
          description="Dispatched → On the way → Arrived → Resolved"
        />
        <Card className="overview-card lifecycle-card">
          <StatusBadge tone={currentStatus === "RESOLVED" ? "success" : "info"}>
            {lifecycleLabel(currentStatus)}
          </StatusBadge>
          {actionError ? (
            <div className="section-error" role="alert">
              <AlertTriangle size={15} />
              {actionError}
            </div>
          ) : null}
          <div className="decision-actions">
            <button
              className="button button-secondary"
              disabled={!selectedIncidentId || !canEnRoute || submitting}
              onClick={() => void performAction("EN_ROUTE")}
            >
              Mark on the way
            </button>
            <button
              className="button button-secondary"
              disabled={!selectedIncidentId || !canArrive || submitting}
              onClick={() => void performAction("ARRIVED")}
            >
              Mark arrived
            </button>
            <button
              className="button button-primary"
              disabled={!selectedIncidentId || !canResolve || submitting}
              onClick={() => void performAction("RESOLVED")}
            >
              Resolve incident
            </button>
          </div>
          {canResolve ? (
            <div className="lifecycle-form">
              <label>
                Preliminary outcome
                <select
                  value={outcome}
                  onChange={(event) => setOutcome(event.target.value)}
                >
                  <option value="UNKNOWN">Unknown</option>
                  <option value="FIRE">Confirmed fire</option>
                  <option value="FALSE_ALARM">False alarm</option>
                </select>
              </label>
              <label>
                Probable cause
                <input
                  value={cause}
                  onChange={(event) => setCause(event.target.value)}
                  placeholder="Observed likely cause"
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={inspection}
                  onChange={(event) => setInspection(event.target.checked)}
                />
                Inspection required
              </label>
              <label>
                Field notes
                <textarea
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Describe the field outcome"
                />
              </label>
            </div>
          ) : null}
        </Card>
      </section>

      <section className="overview-section">
        <SectionHeader
          title="Recent response activity"
          description="Recent route and device events recorded by the system."
        />
        <Card className="overview-card">
          <EventPanel events={view.events} />
        </Card>
      </section>
    </div>
  );
}

function RouteSummary({ route }: { route: RouteIndexItem }) {
  const blockedEdge =
    [...route.reasons, ...route.warnings].find((value) =>
      /edge|blocked|conflict|unavailable/i.test(value),
    ) ?? "None reported";
  const rerouteReason = route.route_changed
    ? (route.reasons[0] ?? "Route conditions changed")
    : "No reroute recorded";

  const routeStatusText = route.no_safe_route
    ? "No safe route"
    : route.status === "route_found"
    ? "Route found"
    : sentenceCase(route.status);

  return (
    <Card className={`route-summary ${route.no_safe_route ? "route-unsafe" : ""}`}>
      <div className="route-summary-heading">
        <div>
          <span className="route-label">
            Current route · Version {route.latest_version}
          </span>
          <h3>
            {route.node_path.length
              ? route.node_path.join(" → ")
              : route.route_id}
          </h3>
          <p className="route-summary-subtitle">
            Route {route.route_id}
            {route.previous_version
              ? ` · Version ${route.previous_version} → Version ${route.latest_version}`
              : ""}
          </p>
        </div>
        <StatusBadge tone={routeTone(route)}>{routeStatusText}</StatusBadge>
      </div>
      {route.no_safe_route ? (
        <div className="no-safe-banner">
          <ShieldAlert size={20} />
          <div>
            <strong>No safe routing path is currently available</strong>
            <span>All known routes are blocked.</span>
          </div>
        </div>
      ) : null}
      <div className="route-facts">
        <Fact
          label="Traffic corridor"
          value={route.no_safe_route ? "Unavailable" : "Selected route"}
        />
        <Fact
          label="Estimated travel score"
          value={
            route.total_edge_cost === null
              ? "Unavailable"
              : String(route.total_edge_cost)
          }
          hint={ROUTE_HINTS.travelScore}
        />
        <Fact label="Blocked road segment" value={blockedEdge} />
        <Fact label="Reroute reason" value={rerouteReason} />
        <Fact label="Last update" value={formatWhen(route.created_at)} />
      </div>
    </Card>
  );
}

function RoutePath({ route }: { route: RouteIndexItem }) {
  if (!route.node_path.length) {
    return (
      <EmptyState
        title="No route path available"
        body="The current route contains no usable intersection sequence."
      />
    );
  }
  return (
    <div className="schematic-wrap">
      <p className="schematic-note">Ordered road path sequence</p>
      <div className="schematic-path">
        {route.node_path.map((node, index) => (
          <span className="path-group" key={`${node}-${index}`}>
            <span className="path-node">
              <RouteIcon size={14} />
              {node}
            </span>
            {index < route.node_path.length - 1 ? (
              <span className="path-link">
                <ArrowRight size={15} />
                <small>{route.edge_path[index] ?? "Unavailable segment"}</small>
              </span>
            ) : null}
          </span>
        ))}
      </div>
    </div>
  );
}

function ActuatorPanel({
  actuator,
}: {
  actuator: ReturnType<typeof useResponseView>["actuators"];
}) {
  if (!actuator) {
    return (
      <Card className="overview-card">
        <EmptyState
          title="Field controller state unavailable"
          body="No field controller information was returned by the server."
        />
      </Card>
    );
  }
  const latest = actuator.commands[0];
  return (
    <Card className="overview-card">
      <div
        className="actuator-node"
        title={`Device ID: ${actuator.node_status.node_id}`}
      >
        <Server size={20} />
        <div>
          <strong>Field controller</strong>
          <span>
            {actuator.node_status.available
              ? "Device connected"
              : "No confirmation yet"}
          </span>
        </div>
        <StatusBadge
          tone={actuator.node_status.available ? "success" : "neutral"}
        >
          {ackText(actuator.node_status.last_ack_status)}
        </StatusBadge>
      </div>
      {latest ? (
        <div className="actuator-detail">
          <Fact label="Latest command" value={describeCommand(latest)} />
          <Fact label="Target device" value={latest.node_id} />
          <Fact label="Sent" value={formatWhen(latest.sent_at)} />
          <Fact label="Device status" value={ackText(latest.ack_status)} />
          <Fact label="Confirmation time" value={formatWhen(latest.ack_at)} />
        </div>
      ) : (
        <EmptyState
          title="No device commands yet"
          body="No command or confirmation has been recorded yet."
        />
      )}
    </Card>
  );
}

function HistoryPanel({
  history,
  currentVersion,
}: {
  history: RouteEvent[];
  currentVersion: number;
}) {
  if (!history.length) {
    return (
      <Card className="overview-card">
        <EmptyState
          title="No route history"
          body="No saved route versions were returned."
        />
      </Card>
    );
  }
  return (
    <Card className="overview-card history-card">
      <div className="route-history-table">
        <div className="route-history-head">
          <span>Version</span>
          <span>Status</span>
          <span>Path</span>
          <span>Timestamp</span>
        </div>
        {history.map((event) => {
          const payload = event.payload;
          const version = Number(payload.version);
          const path = Array.isArray(payload.node_path)
            ? payload.node_path.join(" → ")
            : "Unavailable";
          const statusDisplay = payload.no_safe_route
            ? "No safe route"
            : sentenceCase(String(payload.route_status ?? "Unavailable"));
          return (
            <div
              className={`route-history-row ${
                version === currentVersion ? "current-version" : ""
              }`}
              key={event.id}
            >
              <span>
                <strong>Version {version}</strong>
                {version === currentVersion ? (
                  <Badge tone="info">Current</Badge>
                ) : null}
              </span>
              <span>{statusDisplay}</span>
              <span>{path}</span>
              <time dateTime={event.created_at}>
                {formatWhen(event.created_at)}
              </time>
              <small>
                {payload.route_changed
                  ? "Reroute recorded"
                  : "No route change"}
                {payload.invalidates_prior_commands
                  ? " · earlier traffic commands are no longer valid"
                  : ""}
              </small>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function EventPanel({ events }: { events: RouteEvent[] }) {
  if (!events.length) {
    return (
      <EmptyState
        title="No response activity"
        body="No route or field device events have been recorded yet."
      />
    );
  }
  return (
    <div className="event-list">
      {events.slice(0, 12).map((event) => (
        <div className="event-row" key={event.id}>
          <div>
            <strong>{auditEventLabel(event.event_type)}</strong>
            <span>
              {event.entity_type} · {event.entity_id}
            </span>
          </div>
          <time dateTime={event.created_at}>{formatWhen(event.created_at)}</time>
          <small>
            {event.human_readable_reason ??
              (event.reason_code
                ? sentenceCase(event.reason_code)
                : "No reason recorded")}
          </small>
        </div>
      ))}
    </div>
  );
}

function Fact({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="fact">
      {hint ? (
        <LabelWithHint label={label} hint={hint} />
      ) : (
        <span>{label}</span>
      )}
      <strong>{value}</strong>
    </div>
  );
}
