import { Activity, Clock3, Radio, RotateCcw } from "lucide-react";
import { Card, EmptyState, SectionHeader, StatusBadge } from "../components/ui";
import { useLiveConnection } from "../live/LiveConnectionContext";

const formatMs = (value: number | null) => value === null ? "Not measurable" : `${value.toFixed(1)} ms`;
const stats = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const median = sorted.length % 2 ? sorted[Math.floor(sorted.length / 2)] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  const p95 = sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * .95) - 1))];
  return { median, p95, max: sorted[sorted.length - 1] };
};

export function LiveDiagnosticsPanel() {
  const { status, samples, clearSamples } = useLiveConnection();
  const successful = samples.filter((sample) => sample.refreshOutcome === "success");
  const local = stats(successful.map((sample) => sample.websocketToRefreshCompleteMs).filter((value): value is number => value !== null));
  const wall = stats(successful.filter((sample) => sample.crossClockValid).map((sample) => sample.backendEventToRefreshCompleteMs).filter((value): value is number => value !== null));
  const latest = samples.at(-1);
  const latestWall = [...samples].reverse().find((sample) => sample.crossClockValid && sample.backendEventToRefreshCompleteMs !== null);
  const target = latestWall?.backendEventToRefreshCompleteMs === undefined || latestWall?.backendEventToRefreshCompleteMs === null ? "not_measurable" : latestWall.backendEventToRefreshCompleteMs <= 1000 ? "within" : "exceeds";
  return <div className="live-diagnostics-page">
    <div className="page-header"><div><p className="eyebrow">Administrator diagnostics</p><h2>Live-update latency</h2><p>Observed client refresh timing from the authenticated live channel. This is measurement only, not final SLA validation.</p></div><button className="button button-secondary" type="button" onClick={clearSamples} disabled={!samples.length}><RotateCcw size={15} />Clear samples</button></div>
    <div className="diagnostic-notice"><Activity size={17} /><span>Diagnostics are observational. They do not constitute final ≤1 second validation.</span></div>
    <section className="overview-section"><SectionHeader title="Connection and sample window" description="The client retains the latest 100 observed refresh samples." /><div className="diagnostic-summary"><Card><span>WebSocket</span><strong><Radio size={16} />{status}</strong></Card><Card><span>Samples retained</span><strong>{samples.length} / 100</strong></Card><Card><span>Latest event</span><strong>{latest?.eventType ?? "No samples"}</strong></Card><Card><span>Latest page</span><strong>{latest?.affectedPage ?? "No samples"}</strong></Card></div></section>
    <section className="overview-section"><SectionHeader title="Successful refresh latency" description="Failed, invalid-timing, and incomplete samples remain visible below but are excluded from statistics." /><div className="diagnostic-stat-grid"><MetricCard title="WebSocket → refresh complete" data={local} /><MetricCard title="Backend event → refresh complete" data={wall} /></div></section>
    <section className="overview-section"><SectionHeader title="Latest observation" description="Separate local monotonic measurements from wall-clock comparisons." /><Card className="diagnostic-latest">{latest ? <div className="diagnostic-detail-grid"><Fact label="Outcome" value={latest.refreshOutcome} /><Fact label="Event" value={latest.eventId ?? "Unavailable"} /><Fact label="Page" value={latest.affectedPage} /><Fact label="Coalesced events" value={String(latest.coalescedEventCount)} /><Fact label="WS → refresh start" value={formatMs(latest.websocketToRefreshStartMs)} /><Fact label="Refresh duration" value={formatMs(latest.refreshDurationMs)} /><Fact label="WS → refresh complete" value={formatMs(latest.websocketToRefreshCompleteMs)} /><Fact label="Backend → refresh complete" value={formatMs(latest.backendEventToRefreshCompleteMs)} /></div> : <EmptyState title="No live refresh samples" body="No qualifying live update has completed a REST refresh in this session." />}</Card><div className="diagnostic-target"><Clock3 size={16} /><span>Latest valid backend comparison</span><StatusBadge tone={target === "within" ? "success" : target === "exceeds" ? "warning" : "neutral"}>{target === "within" ? "Within 1000 ms" : target === "exceeds" ? "Exceeds 1000 ms" : "Not measurable"}</StatusBadge></div></section>
    {samples.length && successful.length !== samples.length ? <p className="risk-helper">{samples.length - successful.length} sample(s) are retained for diagnostics but excluded from successful timing statistics.</p> : null}
  </div>;
}
function MetricCard({ title, data }: { title: string; data: { median: number; p95: number; max: number } | null }) { return <Card className="diagnostic-metric"><span>{title}</span>{data ? <><strong>{formatMs(data.median)}</strong><div><span>Median</span><span>p95 {formatMs(data.p95)}</span><span>Max {formatMs(data.max)}</span></div></> : <EmptyState title="Not measurable" body="No successful timing sample is available." />}</Card>; }
function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
