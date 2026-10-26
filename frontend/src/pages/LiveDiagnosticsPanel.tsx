import {
  Activity,
  ArrowRight,
  Clock3,
  Radio,
  RotateCcw,
  Zap,
} from "lucide-react";
import { Card, EmptyState, SectionHeader, StatusBadge } from "../components/ui";
import { useLiveConnection } from "../live/LiveConnectionContext";
import { InfoHint, LabelWithHint } from "../components/InfoHint";
import {
  TECHNICAL_HINTS,
  auditEventLabel,
  sentenceCase,
} from "../copy/glossary";

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
    sorted[
      Math.min(
        sorted.length - 1,
        Math.max(0, Math.ceil(sorted.length * 0.95) - 1)
      )
    ];
  return { median, p95, max: sorted[sorted.length - 1] };
};

function MetricDuration({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined)
    return <span className="diag-placeholder">—</span>;
  return (
    <>
      <span className="diag-val">{value.toFixed(1)}</span>{" "}
      <span className="diag-unit">ms</span>
    </>
  );
}

export function LiveDiagnosticsPanel() {
  const { status, samples, clearSamples } = useLiveConnection();
  const successful = samples.filter(
    (sample) => sample.refreshOutcome === "success"
  );
  const local = stats(
    successful
      .map((sample) => sample.websocketToRefreshCompleteMs)
      .filter((value): value is number => value !== null)
  );
  const wall = stats(
    successful
      .filter((sample) => sample.crossClockValid)
      .map((sample) => sample.backendEventToRefreshCompleteMs)
      .filter((value): value is number => value !== null)
  );
  const latest = samples.at(-1);
  const latestWall = [...samples]
    .reverse()
    .find(
      (sample) =>
        sample.crossClockValid &&
        sample.backendEventToRefreshCompleteMs !== null
    );
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

  const wallPercent = wall
    ? Math.min(100, Math.max(0, (wall.median / 1200) * 100))
    : 0;
  const wallFillClass = !wall
    ? ""
    : wall.median < 150
      ? "latency-fill-green"
      : wall.median <= 1000
        ? "latency-fill-amber"
        : "latency-fill-red";

  const localPercent = local
    ? Math.min(100, Math.max(0, (local.median / 200) * 100))
    : 0;
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
            Real-time client refresh performance from the authenticated live
            channel. Monitors end-to-end telemetry and UI responsiveness.
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={clearSamples}
          disabled={!samples.length}
          title={
            !samples.length
              ? "No latency samples to clear"
              : "Clear all rolling latency samples"
          }
          aria-label={
            !samples.length
              ? "Clear samples (disabled, no samples collected)"
              : "Clear samples"
          }
        >
          <RotateCcw size={15} />
          Clear samples
        </button>
      </div>

      <div
        className="diagnostic-notice"
        role="note"
        aria-label="Observational notice"
      >
        <Activity size={17} aria-hidden="true" />
        <span>
          Diagnostics are observational. They continuously benchmark browser
          refresh timing under live operation.
        </span>
      </div>

      {/* Top Executive Row (3 Summary Cards) */}
      <section
        className="overview-section"
        aria-label="Executive Health Summary"
      >
        <div className="diagnostic-executive-row">
          <Card className="diagnostic-card diagnostic-exec-card">
            <div className="diagnostic-exec-header">
              <span>Live WebSocket Link</span>
              <Radio size={16} aria-hidden="true" />
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
              <LabelWithHint
                label="Latency SLA Compliance"
                hint={TECHNICAL_HINTS.slaThreshold}
              />
              <Clock3 size={16} aria-hidden="true" />
            </div>
            <div className="diagnostic-exec-body">
              {target === "within" ? (
                <StatusBadge tone="success">
                  Within 1.0s Emergency SLA
                </StatusBadge>
              ) : target === "exceeds" ? (
                <StatusBadge tone="danger">Exceeds 1.0s Target</StatusBadge>
              ) : (
                <StatusBadge tone="neutral">Awaiting Live Samples</StatusBadge>
              )}
            </div>
            <span className="diagnostic-exec-meta">
              {latestWall?.backendEventToRefreshCompleteMs != null ? (
                <>
                  Latest sample:{" "}
                  <strong className="diag-mono-metric">
                    <MetricDuration
                      value={latestWall.backendEventToRefreshCompleteMs}
                    />
                  </strong>
                </>
              ) : (
                "Operational SLA threshold: ≤ 1000 ms"
              )}
            </span>
          </Card>

          <Card className="diagnostic-card diagnostic-exec-card">
            <div className="diagnostic-exec-header">
              <span>Rolling Latency Buffer</span>
              <span className="diagnostic-exec-counter">
                {samples.length} / 100
              </span>
            </div>
            <div className="diagnostic-exec-body">
              <strong className="diagnostic-exec-value">
                {samples.length}{" "}
                <span className="diag-gauge-unit">records</span>
              </strong>
            </div>
            <div>
              <div className="buffer-progress-track">
                <div
                  className="buffer-progress-fill"
                  style={{
                    width: `${Math.min(100, (samples.length / 100) * 100)}%`,
                  }}
                />
              </div>
              <span
                className="diagnostic-exec-meta"
                style={{ display: "block", marginTop: 6 }}
              >
                {successful.length} valid ·{" "}
                {samples.length - successful.length} excluded
              </span>
            </div>
          </Card>
        </div>
      </section>

      {/* Dual Gauge Cards (Key Latency Indicators) */}
      <section
        className="overview-section"
        aria-label="Key Latency Indicators"
      >
        <SectionHeader
          title="Latency benchmarks"
          description="Monitors wall-clock sensor dispatch timing alongside local browser paint delay."
        />
        <div className="diagnostic-gauge-grid">
          {/* Card 1: End-to-End Latency */}
          <Card className="diagnostic-card diagnostic-gauge-card">
            <div className="diagnostic-gauge-header">
              <div style={{ display: "inline-flex", alignItems: "center" }}>
                <h4>End-to-End Event Latency</h4>
                <InfoHint
                  text="Total time elapsed from sensor or backend event creation to browser UI repaint."
                  label="End-to-End Latency explanation"
                />
              </div>
              <p>
                Sensor / backend trigger occurrence to operator screen refresh
              </p>
            </div>

            <div>
              <div className="diagnostic-gauge-primary">
                <span className="diagnostic-gauge-number">
                  {wall ? (
                    <>
                      <span>{wall.median.toFixed(1)}</span>{" "}
                      <span className="diag-gauge-unit">ms</span>
                    </>
                  ) : (
                    <span className="diag-placeholder">—</span>
                  )}
                </span>
                <div className="diagnostic-gauge-legend">
                  <span className="gauge-legend-swatch" aria-hidden="true" />
                  <span className="diagnostic-gauge-caption">
                    Median latency
                  </span>
                </div>
                {wall ? (
                  <span
                    className={`gauge-state-tag ${
                      wall.median <= 1000 ? "pass" : "fail"
                    }`}
                  >
                    {wall.median <= 1000 ? "Within SLA" : "Over SLA"}
                  </span>
                ) : null}
              </div>

              <div className="latency-gauge-wrapper">
                <div className="latency-gauge-track">
                  <div
                    className={`latency-gauge-fill ${wallFillClass}`}
                    style={{ width: `${wallPercent}%` }}
                  />
                  {/* Guideline at 1000ms SLA mark (1000 / 1200 = 83.33%) */}
                  <div
                    className="latency-sla-marker"
                    style={{ left: "83.33%" }}
                  >
                    <span className="latency-sla-label">1000 ms SLA</span>
                  </div>
                </div>
                <div className="latency-scale-labels">
                  <span>0 ms</span>
                  <span>400 ms</span>
                  <span>800 ms</span>
                  <span className="scale-highlight-sla">1000 ms</span>
                  <span>1200 ms</span>
                </div>
              </div>
            </div>

            <div className="diagnostic-sub-metrics">
              <span>
                Median:{" "}
                <strong>
                  <MetricDuration value={wall?.median} />
                </strong>
              </span>
              <span>
                <LabelWithHint label="P95:" hint={TECHNICAL_HINTS.p95Latency} />{" "}
                <strong>
                  <MetricDuration value={wall?.p95} />
                </strong>
              </span>
              <span>
                Max:{" "}
                <strong>
                  <MetricDuration value={wall?.max} />
                </strong>
              </span>
            </div>
          </Card>

          {/* Card 2: Client DOM Render Delay */}
          <Card className="diagnostic-card diagnostic-gauge-card">
            <div className="diagnostic-gauge-header">
              <div style={{ display: "inline-flex", alignItems: "center" }}>
                <h4>Client DOM Render Delay</h4>
                <InfoHint
                  text={TECHNICAL_HINTS.domRenderDelay}
                  label="Client DOM Render Delay explanation"
                />
              </div>
              <p>
                WebSocket reception to browser component reconciliation and
                paint
              </p>
            </div>

            <div>
              <div className="diagnostic-gauge-primary">
                <span className="diagnostic-gauge-number">
                  {local ? (
                    <>
                      <span>{local.median.toFixed(1)}</span>{" "}
                      <span className="diag-gauge-unit">ms</span>
                    </>
                  ) : (
                    <span className="diag-placeholder">—</span>
                  )}
                </span>
                <div className="diagnostic-gauge-legend">
                  <span className="gauge-legend-swatch" aria-hidden="true" />
                  <span className="diagnostic-gauge-caption">
                    Median paint duration
                  </span>
                </div>
                {local ? (
                  <span
                    className={`gauge-state-tag ${
                      local.median <= 50 ? "pass" : "fail"
                    }`}
                  >
                    {local.median <= 50 ? "Fast paint" : "Standard"}
                  </span>
                ) : null}
              </div>

              <div className="latency-gauge-wrapper">
                <div className="latency-gauge-track">
                  <div
                    className={`latency-gauge-fill ${localFillClass}`}
                    style={{ width: `${localPercent}%` }}
                  />
                  {/* Guideline at 50ms (Optimal boundary: 50 / 200 = 25%) */}
                  <div
                    className="latency-sla-marker latency-sla-marker-green"
                    style={{ left: "25%" }}
                  >
                    <span className="latency-sla-label latency-sla-label-green">
                      50 ms Fast
                    </span>
                  </div>
                </div>
                <div className="latency-scale-labels">
                  <span>0 ms</span>
                  <span className="scale-highlight-fast">50 ms</span>
                  <span>100 ms</span>
                  <span>150 ms</span>
                  <span>200 ms</span>
                </div>
              </div>
            </div>

            <div className="diagnostic-sub-metrics">
              <span>
                Median:{" "}
                <strong>
                  <MetricDuration value={local?.median} />
                </strong>
              </span>
              <span>
                <LabelWithHint label="P95:" hint={TECHNICAL_HINTS.p95Latency} />{" "}
                <strong>
                  <MetricDuration value={local?.p95} />
                </strong>
              </span>
              <span>
                Max:{" "}
                <strong>
                  <MetricDuration value={local?.max} />
                </strong>
              </span>
            </div>
          </Card>
        </div>
      </section>

      {/* Streamlined Data Pipeline Card */}
      <section
        className="overview-section"
        aria-label="Latest Event Telemetry"
      >
        <SectionHeader
          title="Latest event processing pipeline"
          description="Detailed execution flow of the most recent live update received by this client."
        />
        <Card className="diagnostic-card diagnostic-pipeline-card">
          <div className="pipeline-card-header">
            <div>
              <h4>Real-Time Processing Sequence</h4>
              <p>
                Breakdown across backend trigger, network streaming, and local
                browser paint
              </p>
            </div>
            {latest ? (
              <div className="pipeline-badges">
                <span className="pipeline-tag">
                  {auditEventLabel(latest.eventType)}
                </span>
                <span className="pipeline-tag page-tag">
                  {latest.affectedPage}
                </span>
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
                    {latest.crossClockValid &&
                    latest.backendEventToRefreshCompleteMs !== null ? (
                      <MetricDuration
                        value={latest.backendEventToRefreshCompleteMs}
                      />
                    ) : (
                      "Unavailable"
                    )}
                  </div>
                  <span className="pipeline-step-desc">
                    Total transit from event trigger
                  </span>
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
                    <MetricDuration
                      value={latest.websocketToRefreshStartMs}
                    />
                  </div>
                  <span className="pipeline-step-desc">
                    Transit to browser reception
                  </span>
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
                    <MetricDuration value={latest.refreshDurationMs} />
                  </div>
                  <span className="pipeline-step-desc">
                    Local UI reconciliation &amp; paint
                  </span>
                </div>
              </div>

              <div className="pipeline-meta-row">
                <span>
                  Outcome:{" "}
                  <strong
                    className={
                      latest.refreshOutcome === "success"
                        ? "text-green"
                        : "text-amber"
                    }
                  >
                    {sentenceCase(latest.refreshOutcome)}
                  </strong>
                </span>
                <span>
                  Event ID: <strong>{latest.eventId ?? "Awaiting ID"}</strong>
                </span>
                <span>
                  Target Page: <strong>{latest.affectedPage}</strong>
                </span>
                <span>
                  Coalesced Updates:{" "}
                  <strong>{latest.coalescedEventCount}</strong>
                </span>
                <span>
                  WS &rarr; Complete:{" "}
                  <strong>
                    <MetricDuration
                      value={latest.websocketToRefreshCompleteMs}
                    />
                  </strong>
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
          {samples.length - successful.length} sample(s) are retained for
          diagnostics but excluded from successful timing statistics due to
          refresh errors or unverified clocks.
        </p>
      ) : null}
    </div>
  );
}
