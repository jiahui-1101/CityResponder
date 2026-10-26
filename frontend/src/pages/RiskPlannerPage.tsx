import { Download, Map, RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui";
import { useAreaRisk } from "../hooks/useAreaRisk";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { inspectionRequests, type Inspection } from "../api/inspections";
import { LabelWithHint } from "../components/InfoHint";
import {
  RISK_FACTORS,
  TECHNICAL_HINTS,
  formatWhen,
  sentenceCase,
  inspectionStatusLabel,
  inspectionActionLabel,
  type RiskFactorKey,
} from "../copy/glossary";

const tone = (status: string): "success" | "warning" | "neutral" =>
  status === "calculated" ? "success" : status === "not_evaluated" ? "warning" : "neutral";

export function RiskPlannerPage() {
  const risk = useAreaRisk();
  useLiveRefresh(["area_risk_calculated"], () => risk.refresh(), true, "risk");
  const selected = risk.selected;
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadInspections = async () => {
    try {
      setInspections(await inspectionRequests.list());
      setInspectionError(null);
    } catch (caught) {
      setInspectionError(
        caught instanceof Error ? caught.message : "Unable to load inspection queue"
      );
    }
  };

  useEffect(() => {
    void loadInspections();
  }, []);

  async function createInspection() {
    if (!selected) return;
    setCreating(true);
    try {
      await inspectionRequests.create({
        area_id: selected.area_id,
        incident_id: null,
        reason: "Planner follow-up requested from risk factors",
        status: "OPEN",
        notes: null,
      });
      await loadInspections();
    } catch (caught) {
      setInspectionError(
        caught instanceof Error ? caught.message : "Unable to create inspection"
      );
    } finally {
      setCreating(false);
    }
  }

  async function exportCsv() {
    const blob = await inspectionRequests.exportCsv();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "cityresponder-inspections.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function advanceInspection(item: Inspection) {
    const next =
      item.status === "OPEN"
        ? "IN_PROGRESS"
        : item.status === "IN_PROGRESS"
          ? "CLOSED"
          : "CLOSED";
    if (next === item.status) return;
    try {
      await inspectionRequests.update(item.inspection_id, { status: next });
      await loadInspections();
    } catch (caught) {
      setInspectionError(
        caught instanceof Error ? caught.message : "Unable to update inspection"
      );
    }
  }

  const latestCalculation = risk.areas.reduce(
    (latest, area) =>
      !latest || area.calculated_at > latest ? area.calculated_at : latest,
    ""
  );

  return (
    <div className="risk-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Risk intelligence workspace</p>
          <h2>Area risk intelligence</h2>
          <p>
            Explainable risk estimates based on verified incident history and
            environmental factors.
          </p>
        </div>
        <div className="overview-refresh">
          <span>
            {risk.lastRefreshedAt
              ? `Updated ${formatWhen(risk.lastRefreshedAt)}`
              : "Not refreshed yet"}
          </span>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void risk.refresh()}
            disabled={risk.loading}
            title="Refresh area risk calculations"
          >
            <RefreshCw size={15} className={risk.loading ? "spin" : undefined} />
            {risk.loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {risk.error ? <ErrorState body={risk.error} /> : null}

      <section className="risk-overview-grid">
        <Card className="risk-stat">
          <span>Monitored areas</span>
          <strong>{risk.areas.length}</strong>
          <small>Areas with recorded data</small>
        </Card>
        <Card className="risk-stat">
          <LabelWithHint
            label="Review timeframe"
            hint="Evaluation window for calculating frequency, recency, and electrical share factors."
          />
          <strong>Past 180 days</strong>
          <small>Standard risk window</small>
        </Card>
        <Card className="risk-stat">
          <LabelWithHint
            label="Latest calculation"
            hint={TECHNICAL_HINTS.immutableRecord}
          />
          <strong>{formatWhen(latestCalculation)}</strong>
          <small>Saved score update</small>
        </Card>
      </section>

      <section className="overview-section">
        <SectionHeader
          title="Area risk overview"
          description="Overview of monitored areas and risk levels."
        />
        <Card className="risk-map-placeholder">
          <Map size={22} />
          <div>
            <strong>Area risk overview</strong>
            <span>
              This is an area list overview. Geographic map boundaries are not configured.
            </span>
          </div>
        </Card>
      </section>

      <section className="overview-section">
        <SectionHeader
          title="Area risk list"
          description="Risk scores calculated from confirmed incident history and risk factors."
        />
        {risk.loading ? (
          <LoadingState label="Loading area risk" />
        ) : risk.areas.length === 0 ? (
          <Card>
            <EmptyState
              title="No area risk calculated"
              body="No area risk scores are available yet. Scores are calculated from confirmed incidents and the 5 risk factors (F, R, E, A, M)."
            />
          </Card>
        ) : (
          <Card className="risk-table-card">
            <div className="risk-table-head">
              <span>Area</span>
              <span>Risk score</span>
              <span>Status</span>
              <span>Confirmed incidents</span>
              <span>Last calculated</span>
            </div>
            {risk.areas.map((area) => (
              <button
                className={`risk-table-row ${
                  area.area_id === risk.selectedAreaId ? "selected" : ""
                }`}
                type="button"
                key={area.area_id}
                onClick={() => risk.selectArea(area.area_id)}
                title={`Select area ${area.area_id} to view risk factor details`}
              >
                <strong>{area.area_id}</strong>
                <span>
                  {area.score === null
                    ? "Risk not calculated"
                    : `${area.score.toFixed(2)} / 100`}
                </span>
                <StatusBadge tone={tone(area.status)}>
                  {sentenceCase(area.status)}
                </StatusBadge>
                <span>{area.verified_incident_count}</span>
                <time dateTime={area.calculated_at}>
                  {formatWhen(area.calculated_at)}
                </time>
              </button>
            ))}
          </Card>
        )}
      </section>

      {selected ? (
        <>
          <section className="overview-section">
            <SectionHeader
              title={`Risk factors · ${selected.area_id}`}
              description="Breakdown of the 5 risk factors used to calculate this score."
            />
            <Card className="risk-components">
              <div className="risk-component-head">
                <span>Risk factor</span>
                <span>Value</span>
                <span>Weight</span>
              </div>
              {(["f", "r", "e", "a", "m"] as const).map((key) => {
                const factor = RISK_FACTORS[key as RiskFactorKey];
                const weight = (selected.weights[key.toUpperCase()] ?? 0).toFixed(2);
                const valueDisplay =
                  selected[key] === null ? "Unavailable" : String(selected[key]);
                return (
                  <div className="risk-component-row" key={key}>
                    <div style={{ display: "inline-flex", alignItems: "center" }}>
                      <LabelWithHint
                        label={`${factor.symbol} · ${factor.name}`}
                        hint={`${factor.description} Formula: ${factor.formula}`}
                      />
                    </div>
                    <span>{valueDisplay}</span>
                    <span>{weight}</span>
                  </div>
                );
              })}
              {selected.score === null ? (
                <div className="risk-note">
                  <ShieldAlert size={15} />
                  Risk score cannot be calculated — insufficient data.
                </div>
              ) : null}
              <p className="risk-helper">
                Risk score formula: C = 100 × (0.30F + 0.25R + 0.20E + 0.15A + 0.10M). Meanings are defined by specification.
              </p>
            </Card>
          </section>

          <section className="overview-section">
            <SectionHeader
              title="Confirmed incident history"
              description={`${formatWhen(selected.window_start)} to ${formatWhen(selected.window_end)}`}
            />
            <Card className="risk-history">
              <p>
                {selected.verified_incident_count} confirmed incident(s) contributed to this score.
              </p>
              {selected.reasons.length ? (
                <ul>
                  {selected.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
            </Card>
          </section>

          <section className="overview-section">
            <SectionHeader
              title="Calculation history"
              description="Previous risk calculations for this area"
            />
            {risk.history.length ? (
              <Card className="risk-history-list">
                {risk.history.map((item) => (
                  <div
                    className="risk-history-row"
                    key={`${item.area_id}-${item.calculated_at}`}
                  >
                    <div>
                      <strong>{formatWhen(item.calculated_at)}</strong>
                      <span>{sentenceCase(item.status)}</span>
                    </div>
                    <span>
                      {item.score === null
                        ? "Score unavailable"
                        : `${item.score.toFixed(2)} / 100`}
                    </span>
                    <span>{item.verified_incident_count} confirmed incident(s)</span>
                  </div>
                ))}
              </Card>
            ) : (
              <Card>
                <EmptyState
                  title="No calculation history"
                  body="No previous risk records exist for this area."
                />
              </Card>
            )}
          </section>
        </>
      ) : null}

      <section className="overview-section">
        <SectionHeader
          title="Inspection queue"
          description="Follow-up tasks created from risk assessments and incidents"
          action={
            <div className="decision-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void exportCsv()}
                title="Export inspection records as a CSV file"
              >
                <Download size={14} />
                Export CSV
              </button>
              <button
                className="button button-primary"
                type="button"
                disabled={!selected || creating}
                onClick={() => void createInspection()}
                title={
                  selected
                    ? "Create an inspection follow-up for the selected area"
                    : "Select an area first to create an inspection"
                }
              >
                Create inspection
              </button>
            </div>
          }
        />
        {inspectionError ? (
          <div className="section-error" role="alert">
            {inspectionError}
          </div>
        ) : null}
        <Card className="risk-history-list">
          {inspections.length ? (
            inspections.map((item) => (
              <div className="risk-history-row" key={item.inspection_id}>
                <div>
                  <strong>{item.area_id}</strong>
                  <span>{item.inspection_id}</span>
                </div>
                <StatusBadge
                  tone={
                    item.status === "CLOSED"
                      ? "neutral"
                      : item.status === "IN_PROGRESS"
                        ? "warning"
                        : "info"
                  }
                >
                  {inspectionStatusLabel(item.status)}
                </StatusBadge>
                <span>{item.reason}</span>
                {item.status !== "CLOSED" ? (
                  <button
                    className="button button-secondary"
                    type="button"
                    onClick={() => void advanceInspection(item)}
                    title={
                      item.status === "OPEN"
                        ? "Mark inspection as in progress"
                        : "Close inspection"
                    }
                  >
                    {inspectionActionLabel(item.status)}
                  </button>
                ) : (
                  <span>Closed</span>
                )}
              </div>
            ))
          ) : (
            <EmptyState
              title="No inspections queued"
              body="Create a follow-up inspection after reviewing an area's risk factors."
            />
          )}
        </Card>
      </section>
    </div>
  );
}
