import { useEffect } from "react";
import { Activity, Database, Gauge, Radio, RefreshCw, Server, ShieldAlert, Thermometer, TriangleAlert } from "lucide-react";
import { useOperatorOverview } from "../hooks/useOperatorOverview";
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import type { ComponentStatus, FreshnessItem, SensorState } from "../api/overview";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { useLiveConnection } from "../live/LiveConnectionContext";
import { LiveVisionPanel } from "../components/LiveVisionPanel";

const sensorOrder: SensorState["sensor_type"][] = ["MQ2", "DHT22", "BUTTON", "IR_A", "IR_B"];
const formatTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : "No timestamp";
const componentTone = (status: string): "success" | "warning" | "danger" | "neutral" => status === "healthy" || status === "connected" || status === "available" ? "success" : status === "unavailable" ? "danger" : status === "unknown" ? "neutral" : "warning";
const freshnessTone = (item: FreshnessItem): "success" | "warning" | "neutral" => item.stale === true ? "warning" : item.available ? "success" : "neutral";

function ComponentRow({ label, status }: { label: string; status: ComponentStatus }) {
  return <div className="overview-row"><div><strong>{label}</strong><span>{status.detail ?? "No additional detail"}</span></div><StatusBadge tone={componentTone(status.status)}>{status.status}</StatusBadge></div>;
}

function SensorCard({ sensor, freshness }: { sensor: SensorState; freshness?: FreshnessItem }) {
  const unavailable = !sensor.available || sensor.value === null || sensor.value === undefined;
  const tone = freshness ? freshnessTone(freshness) : unavailable ? "neutral" : "success";
  return <article className="sensor-card"><div className="sensor-card-heading"><span>{sensor.sensor_type}</span><StatusBadge tone={tone}>{freshness?.stale ? "Stale" : unavailable ? "No reading yet" : "Available"}</StatusBadge></div><strong className="sensor-value">{unavailable ? "Unavailable" : String(sensor.value)}{!unavailable && sensor.unit ? <small> {sensor.unit}</small> : null}</strong><span className="sensor-meta">{sensor.node_id ?? "No source node"} · {formatTime(sensor.timestamp)}</span></article>;
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
  return <div className="overview-page">
    <div className="overview-heading"><div><p className="eyebrow">Operator workspace</p><h2>Operational overview</h2><p>Read-only status from the CityResponder backend.</p></div><div className="overview-refresh"><span>{overview.lastRefreshedAt ? `Updated ${formatTime(overview.lastRefreshedAt)}` : "Not refreshed yet"}</span><button className="button button-secondary" type="button" onClick={() => void overview.refresh()} disabled={overview.refreshing}><RefreshCw size={15} className={overview.refreshing ? "spin" : undefined} />{overview.refreshing ? "Refreshing" : "Refresh"}</button></div></div>
    <section className="overview-section"><SectionHeader title="Live annotated camera" description="Real shared frame with Detection V2 boxes, Segmentation V1 polygons and the locked Building A ROI" /><LiveVisionPanel /></section>
    <section className="overview-section" aria-labelledby="system-status-title"><SectionHeader title="System status" description="Current backend component responses" /><Card className="overview-card status-card">{overview.health.loading ? <LoadingState label="Loading system status" /> : overview.health.error ? <ErrorState body={overview.health.error} /> : overview.health.data ? <div className="overview-rows"><ComponentRow label="Backend API" status={overview.health.data.backend} /><ComponentRow label="Database" status={overview.health.data.database} /><ComponentRow label="MQTT broker" status={overview.health.data.mqtt} /><ComponentRow label="WebSocket service" status={overview.health.data.websocket} /><ComponentRow label="Vision pipeline" status={overview.health.data.vision} /><ComponentRow label="Sensor activity" status={overview.health.data.sensor_activity} /><ComponentRow label="Actuator ACK activity" status={overview.health.data.actuator_ack_activity} /></div> : <EmptyState title="No system status" body="The backend returned no system status data." />}</Card></section>
    <section className="overview-section"><SectionHeader title="Sensor snapshot" description="Latest raw readings; missing values remain explicit" /><div className="sensor-grid">{sensorOrder.map((type) => <SensorCard key={type} sensor={sensors.find((item) => item.sensor_type === type) ?? { sensor_type: type, value: null, timestamp: null, node_id: null, unit: null, available: false }} freshness={freshnessByType[type]} />)}</div>{overview.sensors.error ? <div className="section-error"><TriangleAlert size={15} />{overview.sensors.error}</div> : null}</section>
    <section className="overview-section"><SectionHeader title="Perception status" description="Freshness and evidence availability from the read-only snapshot" /><Card className="overview-card perception-card">{overview.freshness.loading || overview.snapshot.loading ? <LoadingState label="Loading perception status" /> : overview.freshness.error || overview.snapshot.error ? <ErrorState body={overview.freshness.error ?? overview.snapshot.error ?? "Unable to load perception status"} /> : overview.freshness.data && overview.snapshot.data ? <div className="perception-grid"><FreshnessRow label="MQ2" item={overview.freshness.data.mq2} /><FreshnessRow label="DHT22" item={overview.freshness.data.dht22} /><FreshnessRow label="Vision detection" item={overview.freshness.data.detection} /><FreshnessRow label="Person in hazard" item={{ source_type: "vision", source_id: "detection", available: overview.snapshot.data.person_in_hazard !== null, stale: null, age_seconds: null, timestamp: overview.snapshot.data.generated_at }} value={overview.snapshot.data.person_in_hazard === null ? "Unavailable" : overview.snapshot.data.person_in_hazard ? "Detected" : "Clear"} /><FreshnessRow label="Road evidence" item={{ source_type: "vision", source_id: "road", available: overview.snapshot.data.road_evidence.length > 0, stale: null, age_seconds: null, timestamp: overview.snapshot.data.generated_at }} value={overview.snapshot.data.road_evidence.length ? `${overview.snapshot.data.road_evidence.length} ROI(s)` : "No evidence"} /></div> : <EmptyState title="No perception status" body="The backend returned no perception snapshot." />}{overview.snapshot.data?.warnings.length ? <div className="warning-list">{overview.snapshot.data.warnings.map((warning) => <span key={warning}><ShieldAlert size={14} />{warning}</span>)}</div> : null}</Card></section>
    <section className="overview-section"><SectionHeader title="Actuator status" description="AC1 state derived from command and ACK history" /><Card className="overview-card">{overview.actuators.loading ? <LoadingState label="Loading actuator status" /> : overview.actuators.error ? <ErrorState body={overview.actuators.error} /> : overview.actuators.data ? <div className="actuator-layout"><div className="actuator-node"><Radio size={20} /><div><strong>{overview.actuators.data.node_status.node_id}</strong><span>{overview.actuators.data.node_status.available ? "ACK history available" : "No ACK history yet"}</span></div><StatusBadge tone={overview.actuators.data.node_status.available ? "success" : "neutral"}>{overview.actuators.data.node_status.last_ack_status ?? "Unavailable"}</StatusBadge></div>{overview.actuators.data.commands.length ? <div className="command-list">{overview.actuators.data.commands.slice(0, 4).map((command) => <div className="overview-row" key={command.command_id}><div><strong>{command.command_type}</strong><span>{command.node_id} · {formatTime(command.sent_at)}</span></div><Badge tone={command.ack_status ? "success" : "neutral"}>{command.ack_status ?? "No ACK"}</Badge></div>)}</div> : <EmptyState title="No actuator commands" body="No command or actuator ACK has been recorded yet." />}</div> : <EmptyState title="No actuator status" body="The backend returned no actuator status." />}</Card></section>
    <section className="overview-section"><SectionHeader title="Recent activity" description="Newest immutable Event-store records" /><Card className="overview-card">{overview.events.loading ? <LoadingState label="Loading recent activity" /> : overview.events.error ? <ErrorState body={overview.events.error} /> : overview.events.data?.length ? <div className="event-list">{overview.events.data.map((event) => <div className="event-row" key={event.id}><div><strong>{event.event_type}</strong><span>{event.entity_type} · {event.entity_id}</span></div><time dateTime={event.created_at}>{formatTime(event.created_at)}</time><small>{event.human_readable_reason ?? event.reason_code ?? "No reason recorded"}</small></div>)}</div> : <EmptyState title="No recent activity" body="No immutable events have been recorded yet." />}</Card></section>
  </div>;
}

function FreshnessRow({ label, item, value }: { label: string; item: FreshnessItem; value?: string }) {
  const text = value ?? (item.stale === true ? "Stale" : item.available ? "Fresh" : "Unavailable");
  return <div className="freshness-row"><div><strong>{label}</strong><span>{item.age_seconds === null ? "No age available" : `${item.age_seconds.toFixed(2)}s old`} · {formatTime(item.timestamp)}</span></div><StatusBadge tone={freshnessTone(item)}>{text}</StatusBadge></div>;
}
