import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Radio,
  Route,
  ShieldCheck,
} from "lucide-react";
import report from "../data/phase3SimulationResults.json";
import { LiveVisionPanel } from "../components/LiveVisionPanel";
import { RouteMap } from "../components/RouteMap";
import { Card, SectionHeader, StatusBadge } from "../components/ui";
import { LabelWithHint } from "../components/InfoHint";
import {
  ROUTE_HINTS,
  TECHNICAL_HINTS,
  sentenceCase,
} from "../copy/glossary";

type Scenario = (typeof report.scenarios)[number];
type DemoMode = "simulation" | "live";
type SimulationRoute = {
  origin_node_id: string;
  destination_node_id: string;
  node_path: string[];
  edge_path: string[];
  cost: number;
  route_version: number;
};

export function SimulationResultsPage() {
  const [mode, setMode] = useState<DemoMode>("simulation");
  const [selectedId, setSelectedId] = useState("B");
  const scenario =
    report.scenarios.find((item) => item.scenario_id === selectedId) ??
    report.scenarios[0];

  return (
    <div className="simulation-page">
      <header className="overview-heading">
        <div>
          <p className="eyebrow">Judge-ready read-only demonstration</p>
          <h2>Emergency response intelligence</h2>
          <p>
            Live observations and isolated software simulation remain explicitly
            separated.
          </p>
        </div>
        <StatusBadge tone="warning">No physical actuation</StatusBadge>
      </header>

      <div
        className="simulation-mode-tabs"
        role="tablist"
        aria-label="Demonstration source"
      >
        <button
          type="button"
          role="tab"
          aria-selected={mode === "simulation"}
          className={mode === "simulation" ? "active" : ""}
          onClick={() => setMode("simulation")}
          title="View end-to-end software simulation scenarios"
        >
          <Route size={15} />
          End-to-end software simulation
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "live"}
          className={mode === "live" ? "active" : ""}
          onClick={() => setMode("live")}
          title="View live camera AI inference in shadow mode"
        >
          <Radio size={15} />
          Live AI Observation
        </button>
      </div>

      {mode === "live" ? (
        <section className="overview-section">
          <SectionHeader
            title="Live AI shadow mode"
            description="Genuine Camera 0 inference; observation only with no physical edge assignment"
          />
          <LiveVisionPanel />
        </section>
      ) : (
        <SimulationView
          scenario={scenario}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
        />
      )}
    </div>
  );
}

function SimulationView({
  scenario,
  selectedId,
  setSelectedId,
}: {
  scenario: Scenario;
  selectedId: string;
  setSelectedId: (value: string) => void;
}) {
  const plan = scenario.response_plan;
  const selected = plan?.selected_route as SimulationRoute | null | undefined;
  const alternative = plan?.alternative_route as SimulationRoute | null | undefined;
  const blocked = plan
    ? Object.entries(plan.road_states)
        .filter(([, state]) => state === "BLOCKED")
        .map(([id]) => id)
    : [];
  const uncertain = plan
    ? Object.entries(plan.road_states)
        .filter(([, state]) => state === "UNCERTAIN")
        .map(([id]) => id)
    : [];
  const noSafeRoute = Boolean(scenario.actual.no_safe_route);

  return (
    <>
      <div className="simulation-safety">
        <ShieldCheck size={18} />
        <span>
          Isolated simulation database · Offline demonstration mode · No physical actuation · Draft image geometry
        </span>
      </div>

      <div
        className="scenario-selector"
        role="list"
        aria-label="Simulation scenarios"
      >
        {report.scenarios.map((item) => (
          <button
            type="button"
            key={item.scenario_id}
            className={item.scenario_id === selectedId ? "active" : ""}
            onClick={() => setSelectedId(item.scenario_id)}
            title={`Select Scenario ${item.scenario_id}: ${item.name}`}
          >
            <strong>{item.scenario_id}</strong>
            <span>{item.name}</span>
          </button>
        ))}
      </div>

      <section className="simulation-workspace">
        <div className="simulation-main">
          <Card className="simulation-map-card">
            <div className="simulation-card-heading">
              <div>
                <span className="scenario-id">
                  Scenario {scenario.scenario_id} · SIMULATED
                </span>
                <h3>{scenario.name}</h3>
              </div>
              <StatusBadge
                tone={
                  noSafeRoute ? "danger" : selected ? "success" : "warning"
                }
              >
                {noSafeRoute
                  ? "No safe route"
                  : selected
                    ? "Route found"
                    : "No route requested"}
              </StatusBadge>
            </div>
            <RouteMap
              selected={
                selected
                  ? { nodeIds: selected.node_path, edgeIds: selected.edge_path }
                  : null
              }
              alternative={
                alternative
                  ? {
                      nodeIds: alternative.node_path,
                      edgeIds: alternative.edge_path,
                    }
                  : null
              }
              blockedEdgeIds={blocked}
              uncertainEdgeIds={uncertain}
              noSafeRoute={noSafeRoute}
              sourceMode="SIMULATED"
              routeVersion={selected?.route_version}
            />
          </Card>
        </div>

        <aside className="simulation-sidebar">
          <Card className="simulation-card">
            <h3>Decision</h3>
            <dl className="simulation-facts">
              <Fact
                label="Verification"
                value={
                  plan?.verification_result
                    ? sentenceCase(plan.verification_result)
                    : "Rejected"
                }
              />
              <Fact
                label="Confidence"
                value={
                  plan?.confidence == null
                    ? "Unavailable"
                    : `${(plan.confidence * 100).toFixed(0)}%`
                }
              />
              <Fact
                label="Severity"
                value={
                  plan?.severity
                    ? sentenceCase(plan.severity)
                    : "Not actionable"
                }
              />
              <Fact
                label="Origin"
                value={selected?.origin_node_id ?? "None"}
              />
              <Fact
                label="Destination"
                value={selected?.destination_node_id ?? "None"}
              />
              <Fact
                label="Estimated travel score"
                value={
                  selected?.cost == null ? "Unavailable" : String(selected.cost)
                }
                hint={ROUTE_HINTS.travelScore}
              />
            </dl>
            <p className="route-decision-copy">
              {plan?.route_explanation ?? scenario.explanation[0]}
            </p>
          </Card>

          <Card className="simulation-card">
            <h3>Road conditions</h3>
            {plan && Object.keys(plan.road_states).length ? (
              <div className="road-state-list">
                {Object.entries(plan.road_states).map(([edge, state]) => (
                  <span key={edge} className={state.toLowerCase()}>
                    <strong>{edge}</strong>
                    {sentenceCase(state)}
                  </span>
                ))}
              </div>
            ) : (
              <p>No blocked or uncertain roads reported.</p>
            )}
            {plan?.uncertainty_warnings.map((warning) => (
              <small key={warning}>{warning}</small>
            ))}
          </Card>
        </aside>
      </section>

      <section className="simulation-detail-grid">
        <Card className="simulation-card">
          <h3>Evidence and reasoning</h3>
          <p>{scenario.explanation.join(" ")}</p>
          <dl className="simulation-facts">
            <Fact
              label="Accepted evidence"
              value={String(plan?.evidence_summary.accepted ?? 0)}
            />
            <Fact
              label="Rejected evidence"
              value={String(plan?.evidence_summary.rejected ?? 0)}
            />
            <Fact
              label="Sources"
              value={plan?.evidence_summary.sources.join(", ") ?? "None"}
            />
          </dl>
        </Card>

        <Card className="simulation-card">
          <h3>Response plan</h3>
          <dl className="simulation-facts">
            <Fact
              label="Recommended units"
              value={String(plan?.recommended_resources.length ?? 0)}
            />
            <Fact
              label="Traffic signals planned"
              value={String(plan?.proposed_traffic_behavior.length ?? 0)}
            />
            <Fact
              label="Alert signals planned"
              value={String(plan?.proposed_alert_behavior.length ?? 0)}
            />
            <Fact
              label="Execution status"
              value={sentenceCase(plan?.execution.status ?? "Not executed")}
            />
          </dl>
        </Card>

        <Card className="simulation-card">
          <h3>Audit and lifecycle</h3>
          <dl className="simulation-facts">
            <Fact
              label="Logged events"
              value={String(scenario.audit_event_count)}
            />
            <Fact
              label="Response stage"
              value={sentenceCase(
                plan?.execution.lifecycle?.status ?? "Not started"
              )}
            />
            <Fact
              label="Device messages sent"
              value={String(plan?.execution.mqtt_publications ?? 0)}
              hint={TECHNICAL_HINTS.mqttMessaging}
            />
          </dl>
          <footer>
            <span>
              <Clock3 size={13} />
              {scenario.timings_ms.total.toFixed(2)} ms
            </span>
            <span>
              {scenario.status === "PASS" ? (
                <CheckCircle2 size={14} />
              ) : (
                <AlertTriangle size={14} />
              )}
              {scenario.status === "PASS" ? "Passed" : "Warning"}
            </span>
          </footer>
        </Card>
      </section>
    </>
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
    <div>
      <dt>
        {hint ? <LabelWithHint label={label} hint={hint} /> : label}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}
