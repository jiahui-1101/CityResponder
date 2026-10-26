import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Radio,
  RotateCcw,
  Zap,
} from "lucide-react";
import { Card, EmptyState, SectionHeader } from "../components/ui";
import { useLiveConnection } from "../live/LiveConnectionContext";

const formatMs = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${value.toFixed(1)} ms`;

const stats = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const median =
    sorted.length % 2
      ? sorted[Math.floor(sorted.length / 2)]
      : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  const p95 =
    sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * 0.95) - 1))];
  return { median, p95, max: sorted[sorted.length - 1] };
};

export function LiveDiagnosticsPanel() {
  const { status, samples, clearSamples } = useLiveConnection();
  const successful = samples.filter((sample) => sample.refreshOutcome === "success");
  const local = stats(
    successful
      .map((sample) => sample.websocketToRefreshCompleteMs)
      .filter((value): value is number => value !== null),
  );
  const wall = stats(
    successful
      .filter((sample) => sample.crossClockValid)
      .map((sample) => sample.backendEventToRefreshCompleteMs)
      .filter((value): value is number => value !== null),
  );
  const latest = samples.at(-1);
  const latestWall = [...samples]
    .reverse()
    .find((sample) => sample.crossClockValid && sample.backendEventToRefreshCompleteMs !== null);
  const target =
    latestWall?.backendEventToRefreshCompleteMs === undefined ||
    latestWall?.backendEventToRefreshCompleteMs === null
      ? "not_measurable"
      : latestWall.backendEventToRefreshCompleteMs <= 1000
      ? "within"
      : "exceeds";

  const statusLabel =
    status === "connected"
      ? "Connected"
      : status === "connecting"
      ? "Reconnecting..."
      : status === "error"
      ? "Offline / Error"
      : "Disconnected";

  const wallPercent = wall ? Math.min(100, Math.max(0, (wall.median / 1200) * 100)) : 0;
  const wallFillClass = !wall
    ? ""
    : wall.median < 150
    ? "latency-fill-green"
    : wall.median <= 1000
    ? "latency-fill-amber"
    : "latency-fill-red";

  const localPercent = local ? Math.min(100, Math.max(0, (local.median / 200) * 100)) : 0;
  const localFillClass = !local
    ? ""
    : local.median < 50
    ? "latency-fill-green"
    : local.median <= 150
    ? "latency-fill-amber"
    : "latency-fill-red";

  return (
    <div className="live-diagnostics-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Administrator diagnostics</p>
          <h2>Live-update latency &amp; health</h2>
          <p>
            Real-time client refresh performance from the authenticated live channel. Monitors
            end-to-end telemetry and UI responsiveness.
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={clearSamples}
          disabled={!samples.length}
        >
          <RotateCcw size={15} />
          Clear samples
        </button>
      </div>

      <div className="diagnostic-notice">
        <Activity size={17} />
        <span>
          Diagnostics are observational. They continuously benchmark browser refresh timing under
          live operation.
        </span>
      </div>

      {/* Top Executive Row (3 Summary Cards) */}
      <section className="overview-section" aria-label="Executive Health Summary">
        <div className="diagnostic-executive-row">
          <Card className="diagnostic-card diagnostic-exec-card">
            <div className="diagnostic-exec-header">
              <span>Live WebSocket Link</span>
              <Radio size={16} />
            </div>
            <div className="diagnostic-exec-body">
              <span className={`connection-dot ${status}`} aria-hidden="true" />
              <strong className="diagnostic-exec-value">{statusLabel}</strong>
            </div>
            <span className="diagnostic-exec-meta">
              {status === "connected"
                ? "Authenticated bidirectional event stream"
                : "Attempting live socket connection"}
            </span>
          </Card>

          <Card className="diagnostic-card diagnostic-exec-card">
            <div className="diagnostic-exec-header">
              <span>Latency SLA Compliance</span>
              <Clock3 size={16} />
            </div>
            <div className="diagnostic-exec-body">
              {target === "within" ? (
                <div className="sla-badge-within">
                  <CheckCircle2 size={16} />
                  <span>Within 1.0s Emergency SLA</span>
                </div>
              ) : target === "exceeds" ? (
                <div className="sla-badge-exceeds">
                  <AlertTriangle size={16} />
                  <span>Exceeds 1.0s Target</span>
                </div>
              ) : (
                <div className="sla-badge-awaiting">
                  <Clock3 size={16} />
                  <span>Awaiting Live Samples</span>
                </div>
              )}
            </div>
            <span className="diagnostic-exec-meta">
              {latestWall?.backendEventToRefreshCompleteMs != null
                ? `Latest sample: ${formatMs(latestWall.backendEventToRefreshCompleteMs)}`
                : "Operational SLA threshold: ≤ 1000 ms"}
            </span>
          </Card>

          <Card className="diagnostic-card diagnostic-exec-card">
            <div className="diagnostic-exec-header">
              <span>Rolling Latency Buffer</span>
              <span className="diagnostic-exec-meta">{samples.length} / 100</span>
            </div>
            <div className="diagnostic-exec-body">
              <strong className="diagnostic-exec-value">{samples.length} records</strong>
            </div>
            <div>
              <div className="buffer-progress-track">
                <div
                  className="buffer-progress-fill"
                  style={{ width: `${Math.min(100, (samples.length / 100) * 100)}%` }}
                />
              </div>
              <span className="diagnostic-exec-meta" style={{ display: "block", marginTop: 4 }}>
                {successful.length} valid · {samples.length - successful.length} excluded
              </span>
            </div>
          </Card>
        </div>
      </section>

      {/* Dual Gauge Cards (Key Latency Indicators) */}
      <section className="overview-section" aria-label="Key Latency Indicators">
        <SectionHeader
          title="Latency benchmarks"
          description="Monitors wall-clock sensor dispatch timing alongside local browser paint delay."
        />
        <div className="diagnostic-gauge-grid">
          {/* Card 1: End-to-End Latency */}
          <Card className="diagnostic-card diagnostic-gauge-card">
            <div className="diagnostic-gauge-header">
              <h4>End-to-End Event Latency</h4>
              <p>Sensor / backend trigger occurrence to operator screen refresh</p>
            </div>

            <div>
              <div className="diagnostic-gauge-primary">
                <span className="diagnostic-gauge-number">
                  {wall ? formatMs(wall.median) : "—"}
                </span>
                <span className="diagnostic-gauge-caption">Median latency</span>
              </div>

              <div className="latency-gauge-wrapper">
                <div className="latency-gauge-track">
                  <div
                    className={`latency-gauge-fill ${wallFillClass}`}
                    style={{ width: `${wallPercent}%` }}
                  />
                  {/* Guideline at 1000ms SLA mark (1000 / 1200 = 83.33%) */}
                  <div className="latency-sla-marker" style={{ left: "83.33%" }}>
                    <span className="latency-sla-label">1000 ms SLA</span>
                  </div>
                </div>
                <div className="latency-scale-labels">
                  <span>0 ms</span>
                  <span>400 ms</span>
                  <span>800 ms</span>
                  <span style={{ color: "#f87171", fontWeight: 700 }}>1000 ms</span>
                  <span>1200 ms</span>
                </div>
              </div>
            </div>

            <div className="diagnostic-sub-metrics">
              <span>
                Median: <strong>{formatMs(wall?.median)}</strong>
              </span>
              <span>
                P95: <strong>{formatMs(wall?.p95)}</strong>
              </span>
              <span>
                Max: <strong>{formatMs(wall?.max)}</strong>
              </span>
            </div>
          </Card>

          {/* Card 2: Client DOM Render Delay */}
          <Card className="diagnostic-card diagnostic-gauge-card">
            <div className="diagnostic-gauge-header">
              <h4>Client DOM Render Delay</h4>
              <p>WebSocket reception to browser component reconciliation and paint</p>
            </div>

            <div>
              <div className="diagnostic-gauge-primary">
                <span className="diagnostic-gauge-number">
                  {local ? formatMs(local.median) : "—"}
                </span>
                <span className="diagnostic-gauge-caption">Median paint duration</span>
              </div>

              <div className="latency-gauge-wrapper">
                <div className="latency-gauge-track">
                  <div
                    className={`latency-gauge-fill ${localFillClass}`}
                    style={{ width: `${localPercent}%` }}
                  />
                  {/* Guideline at 50ms (Optimal boundary: 50 / 200 = 25%) */}
                  <div
                    className="latency-sla-marker"
                    style={{ left: "25%", background: "#10b981", boxShadow: "0 0 6px rgba(16,185,129,0.6)" }}
                  >
                    <span className="latency-sla-label" style={{ color: "#34d399" }}>
                      50 ms Fast
                    </span>
                  </div>
                </div>
                <div className="latency-scale-labels">
                  <span>0 ms</span>
                  <span style={{ color: "#34d399", fontWeight: 600 }}>50 ms</span>
                  <span>100 ms</span>
                  <span>150 ms</span>
                  <span>200 ms</span>
                </div>
              </div>
            </div>

            <div className="diagnostic-sub-metrics">
              <span>
                Median: <strong>{formatMs(local?.median)}</strong>
              </span>
              <span>
                P95: <strong>{formatMs(local?.p95)}</strong>
              </span>
              <span>
                Max: <strong>{formatMs(local?.max)}</strong>
              </span>
            </div>
          </Card>
        </div>
      </section>

      {/* Streamlined Data Pipeline Card */}
      <section className="overview-section" aria-label="Latest Event Telemetry">
        <SectionHeader
          title="Latest event processing pipeline"
          description="Detailed execution flow of the most recent live update received by this client."
        />
        <Card className="diagnostic-card diagnostic-pipeline-card">
          <div className="pipeline-card-header">
            <div>
              <h4>Real-Time Processing Sequence</h4>
              <p>Breakdown across backend trigger, network streaming, and local browser paint</p>
            </div>
            {latest ? (
              <div className="pipeline-badges">
                <span className="pipeline-tag">{latest.eventType}</span>
                <span className="pipeline-tag page-tag">{latest.affectedPage}</span>
              </div>
            ) : null}
          </div>

          {latest ? (
            <>
              <div className="pipeline-flow">
                {/* Step 1 */}
                <div className="pipeline-step">
                  <div className="pipeline-step-header">
                    <Zap size={15} />
                    <span>1. Backend Ingestion &amp; Fusion</span>
                  </div>
                  <div className="pipeline-step-value">
                    {latest.crossClockValid && latest.backendEventToRefreshCompleteMs !== null
                      ? formatMs(latest.backendEventToRefreshCompleteMs)
                      : "Unavailable"}
                  </div>
                  <span className="pipeline-step-desc">Total transit from event trigger</span>
                </div>

                <div className="pipeline-arrow" aria-hidden="true">
                  <ArrowRight size={18} />
                </div>

                {/* Step 2 */}
                <div className="pipeline-step">
                  <div className="pipeline-step-header">
                    <Radio size={15} />
                    <span>2. WebSocket Transmission</span>
                  </div>
                  <div className="pipeline-step-value">
                    {formatMs(latest.websocketToRefreshStartMs)}
                  </div>
                  <span className="pipeline-step-desc">Transit to browser reception</span>
                </div>

                <div className="pipeline-arrow" aria-hidden="true">
                  <ArrowRight size={18} />
                </div>

                {/* Step 3 */}
                <div className="pipeline-step">
                  <div className="pipeline-step-header">
                    <Activity size={15} />
                    <span>3. Screen DOM Repaint</span>
                  </div>
                  <div className="pipeline-step-value">
                    {formatMs(latest.refreshDurationMs)}
                  </div>
                  <span className="pipeline-step-desc">Local UI reconciliation &amp; paint</span>
                </div>
              </div>

              <div className="pipeline-meta-row">
                <span>
                  Outcome:{" "}
                  <strong
                    className={
                      latest.refreshOutcome === "success" ? "text-green" : "text-amber"
                    }
                  >
                    {latest.refreshOutcome}
                  </strong>
                </span>
                <span>
                  Event ID: <strong>{latest.eventId ?? "Awaiting ID"}</strong>
                </span>
                <span>
                  Target Page: <strong>{latest.affectedPage}</strong>
                </span>
                <span>
                  Coalesced Updates: <strong>{latest.coalescedEventCount}</strong>
                </span>
                <span>
                  WS &rarr; Complete:{" "}
                  <strong>{formatMs(latest.websocketToRefreshCompleteMs)}</strong>
                </span>
              </div>
            </>
          ) : (
            <EmptyState
              title="Awaiting next live event..."
              body="No qualifying live update has completed a REST refresh in this session yet."
            />
          )}
        </Card>
      </section>

      {samples.length > 0 && successful.length !== samples.length ? (
        <p className="risk-helper">
          {samples.length - successful.length} sample(s) are retained for diagnostics but excluded
          from successful timing statistics due to refresh errors or unverified clocks.
        </p>
      ) : null}
    </div>
  );
}
