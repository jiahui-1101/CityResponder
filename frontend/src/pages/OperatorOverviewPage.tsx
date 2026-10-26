import { useEffect } from "react";
import { Radio, RefreshCw, ShieldAlert, TriangleAlert } from "lucide-react";
import { useOperatorOverview } from "../hooks/useOperatorOverview";
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import type { ComponentStatus, FreshnessItem, SensorState } from "../api/overview";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { useLiveConnection } from "../live/LiveConnectionContext";
import { LiveVisionPanel } from "../components/LiveVisionPanel";
import {
  FRESHNESS_LABELS,
  HEALTH_LABELS,
  ackText,
  ackTone,
  describeCommand,
  describeEvent,
  describeSensor,
  formatWhen,
  freshnessDetail,
  freshnessText,
  healthStatusText,
  personInHazardText,
  roadEvidenceText,
  sensorBadge,
} from "../utils/humanize";

const sensorOrder: SensorState["sensor_type"][] = ["MQ2", "DHT22", "BUTTON", "IR_A", "IR_B"];
const componentTone = (status: string): "success" | "warning" | "danger" | "neutral" => status === "healthy" || status === "connected" || status === "available" ? "success" : status === "unavailable" ? "danger" : status === "unknown" ? "neutral" : "warning";
const freshnessTone = (item: FreshnessItem): "success" | "warning" | "neutral" => item.stale === true ? "warning" : item.available ? "success" : "neutral";

function ComponentRow({ label, status }: { label: string; status: ComponentStatus }) {
  return <div className="overview-row">
    <div><strong>{label}</strong><span>{status.detail ?? "Nothing to report"}</span></div>
    <StatusBadge tone={componentTone(status.status)}>{healthStatusText(status.status)}</StatusBadge>
  </div>;
}

function SensorCard({ sensor, freshness }: { sensor: SensorState; freshness?: FreshnessItem }) {
  const display = describeSensor(sensor);
  const badge = sensorBadge(display.missing, freshness);
  return <article className="sensor-card" title={sensor.node_id ? `Source device: ${sensor.node_id}` : undefined}>
    <div className="sensor-card-heading"><span>{display.label}</span><StatusBadge tone={badge.tone}>{badge.text}</StatusBadge></div>
    <strong className={`sensor-value${display.alert ? " is-alert" : ""}`}>{display.value}{display.unit ? <small> {display.unit}</small> : null}</strong>
    <span className="sensor-meta">{display.missing ? "Waiting for the first reading" : `Updated ${formatWhen(sensor.timestamp)}`}</span>
  </article>;
}

function FreshnessRow({ label, item, value }: { label: string; item: FreshnessItem; value?: string }) {
  return <div className="freshness-row">
    <div><strong>{label}</strong><span>{freshnessDetail(item)}</span></div>
    <StatusBadge tone={freshnessTone(item)}>{value ?? freshnessText(item)}</StatusBadge>
  </div>;
}

export function OperatorOverviewPage() {
  const overview = useOperatorOverview();
  const { subscribe } = useLiveConnection();
  useEffect(() => {
    const unsubscribeSensors = subscribe(["sensor_reading"], overview.applySensorEvent);
    const unsubscribeVision = subscribe(["vision_detection", "vision_road_evidence"], overview.applyVisionEvent);
    return () => { unsubscribeSensors(); unsubscribeVision(); };
  }, [overview.applySensorEvent, overview.applyVisionEvent, subscribe]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      void overview.refreshSections(["freshness", "snapshot", "health"]);
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [overview.refreshSections]);
  useLiveRefresh(["actuator_command", "actuator_ack"], () => overview.refreshSections(["actuators", "health", "events"]), true, "operator-overview");
  useLiveRefresh(["incident_decision", "operator_decision", "route_version", "traffic_command_invalidated"], () => overview.refreshSections(["events"]), true, "operator-overview");

  const sensors = overview.sensors.data ?? [];
  const freshnessByType: Record<string, FreshnessItem | undefined> = overview.freshness.data ? { MQ2: overview.freshness.data.mq2, DHT22: overview.freshness.data.dht22, BUTTON: overview.freshness.data.button, IR_A: overview.freshness.data.ir_a, IR_B: overview.freshness.data.ir_b } : {};
  const snapshot = overview.snapshot.data;
  const actuators = overview.actuators.data;

  return <div className="overview-page">
    <div className="overview-heading">
      <div>
        <p className="eyebrow">Operator workspace</p>
        <h2>Operational overview</h2>
        <p>A live summary of the camera, sensors, field devices and system health. View only.</p>
      </div>
      <div className="overview-refresh">
        <span>{overview.lastRefreshedAt ? `Updated ${formatWhen(overview.lastRefreshedAt)}` : "Not updated yet"}</span>
        <button className="button button-secondary" type="button" onClick={() => void overview.refresh()} disabled={overview.refreshing}>
          <RefreshCw size={15} className={overview.refreshing ? "spin" : undefined} />{overview.refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>
    </div>

    <section className="overview-section">
      <SectionHeader title="Overhead camera" description="Live view from above, with AI outlines drawn on top. For viewing only." />
      <LiveVisionPanel />
    </section>

    <section className="overview-section" aria-labelledby="system-status-title">
      <SectionHeader title="System health" description="Whether each part of the system is running" />
      <Card className="overview-card status-card">
        {overview.health.loading ? <LoadingState label="Checking system health" />
          : overview.health.error ? <ErrorState body={overview.health.error} />
          : overview.health.data ? <div className="overview-rows">
            <ComponentRow label={HEALTH_LABELS.backend} status={overview.health.data.backend} />
            <ComponentRow label={HEALTH_LABELS.database} status={overview.health.data.database} />
            <ComponentRow label={HEALTH_LABELS.mqtt} status={overview.health.data.mqtt} />
            <ComponentRow label={HEALTH_LABELS.websocket} status={overview.health.data.websocket} />
            <ComponentRow label={HEALTH_LABELS.vision} status={overview.health.data.vision} />
            <ComponentRow label={HEALTH_LABELS.sensor_activity} status={overview.health.data.sensor_activity} />
            <ComponentRow label={HEALTH_LABELS.actuator_ack_activity} status={overview.health.data.actuator_ack_activity} />
          </div>
          : <EmptyState title="No system health yet" body="The server hasn't sent any health information." />}
      </Card>
    </section>

    <section className="overview-section">
      <SectionHeader title="Sensors" description="The latest reading from each sensor. Anything missing is shown as missing." />
      <div className="sensor-grid">
        {sensorOrder.map((type) => <SensorCard
          key={type}
          sensor={sensors.find((item) => item.sensor_type === type) ?? { sensor_type: type, value: null, timestamp: null, node_id: null, unit: null, available: false }}
          freshness={freshnessByType[type]}
        />)}
      </div>
      {overview.sensors.error ? <div className="section-error"><TriangleAlert size={15} />{overview.sensors.error}</div> : null}
    </section>

    <section className="overview-section">
      <SectionHeader title="Data freshness" description="How recent the sensor and camera data is" />
      <Card className="overview-card perception-card">
        {overview.freshness.loading || overview.snapshot.loading ? <LoadingState label="Checking data freshness" />
          : overview.freshness.error || overview.snapshot.error ? <ErrorState body={overview.freshness.error ?? overview.snapshot.error ?? "Unable to check data freshness"} />
          : overview.freshness.data && snapshot ? <div className="perception-grid">
            <FreshnessRow label={FRESHNESS_LABELS.mq2} item={overview.freshness.data.mq2} />
            <FreshnessRow label={FRESHNESS_LABELS.dht22} item={overview.freshness.data.dht22} />
            <FreshnessRow label={FRESHNESS_LABELS.detection} item={overview.freshness.data.detection} />
            <FreshnessRow
              label={FRESHNESS_LABELS.person}
              item={{ source_type: "vision", source_id: "detection", available: snapshot.person_in_hazard !== null, stale: null, age_seconds: null, timestamp: snapshot.generated_at }}
              value={personInHazardText(snapshot.person_in_hazard)}
            />
            <FreshnessRow
              label={FRESHNESS_LABELS.road}
              item={{ source_type: "vision", source_id: "road", available: snapshot.road_evidence.length > 0, stale: null, age_seconds: null, timestamp: snapshot.generated_at }}
              value={roadEvidenceText(snapshot.road_evidence.length)}
            />
          </div>
          : <EmptyState title="No freshness data yet" body="The server hasn't sent a camera and sensor summary." />}
        {snapshot?.warnings.length ? <div className="warning-list">{snapshot.warnings.map((warning) => <span key={warning}><ShieldAlert size={14} />{warning}</span>)}</div> : null}
      </Card>
    </section>

    <section className="overview-section">
      <SectionHeader title="Field devices" description="Traffic lights, siren and gate. Shows the latest commands and whether the device confirmed them." />
      <Card className="overview-card">
        {overview.actuators.loading ? <LoadingState label="Checking field devices" />
          : overview.actuators.error ? <ErrorState body={overview.actuators.error} />
          : actuators ? <div className="actuator-layout">
            <div className="actuator-node" title={`Device: ${actuators.node_status.node_id}`}>
              <Radio size={20} />
              <div>
                <strong>Field controller</strong>
                <span>{actuators.node_status.available ? `Last confirmation at ${formatWhen(actuators.node_status.last_ack_at)}` : "No confirmations received yet"}</span>
              </div>
              <StatusBadge tone={ackTone(actuators.node_status.last_ack_status)}>{actuators.node_status.available ? ackText(actuators.node_status.last_ack_status) : "No data yet"}</StatusBadge>
            </div>
            {actuators.commands.length ? <div className="command-list">
              {actuators.commands.slice(0, 4).map((command) => <div className="overview-row" key={command.command_id}>
                <div>
                  <strong>{describeCommand(command)}</strong>
                  <span>Sent {formatWhen(command.sent_at)}{command.ack_at ? ` · confirmed ${formatWhen(command.ack_at)}` : ""}</span>
                </div>
                <Badge tone={ackTone(command.ack_status)}>{ackText(command.ack_status)}</Badge>
              </div>)}
            </div>
            : <EmptyState title="No device commands yet" body="No command has been sent to the field devices yet." />}
          </div>
          : <EmptyState title="No field device data yet" body="The server hasn't sent any field device status." />}
      </Card>
    </section>

    <section className="overview-section">
      <SectionHeader title="Recent activity" description="The latest events recorded by the system" />
      <Card className="overview-card">
        {overview.events.loading ? <LoadingState label="Loading recent activity" />
          : overview.events.error ? <ErrorState body={overview.events.error} />
          : overview.events.data?.length ? <div className="event-list">
            {overview.events.data.map((event) => {
              const item = describeEvent(event);
              return <div className="event-row" key={event.id} title={item.audit}>
                <div><strong>{item.title}</strong></div>
                <time dateTime={event.created_at}>{formatWhen(event.created_at)}</time>
                {item.detail ? <small>{item.detail}</small> : null}
              </div>;
            })}
          </div>
          : <EmptyState title="No activity yet" body="Nothing has been recorded yet." />}
      </Card>
    </section>
  </div>;
}
