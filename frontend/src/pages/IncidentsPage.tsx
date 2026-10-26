import { Link } from "react-router-dom";
import { ArrowUpRight, ClipboardList } from "lucide-react";
import { useIncidents } from "../hooks/useIncidents";
import { Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { formatWhen, sentenceCase, TECHNICAL_HINTS } from "../copy/glossary";
import { InfoHint } from "../components/InfoHint";

const outcomeTone = (value: string): "success" | "warning" | "danger" | "neutral" =>
  value === "CONFIRM" || value === "confirmed"
    ? "success"
    : value === "REJECT" || value === "CANCEL" || value === "not_confirmed"
    ? "warning"
    : value === "unresolved"
    ? "danger"
    : "neutral";

const outcomeLabel = (value: string) => {
  const upper = value.toUpperCase();
  if (upper === "CONFIRM") return "Confirmed";
  if (upper === "REJECT") return "Rejected";
  if (upper === "CANCEL") return "Cancelled";
  return sentenceCase(value);
};

export function IncidentsPage() {
  const { items, loading, error, refresh } = useIncidents();
  useLiveRefresh(["incident_decision", "operator_decision"], () => refresh(), true, "incidents");

  return (
    <div className="incidents-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Operator workspace</p>
          <h2>Incidents</h2>
          <p>
            Permanent records of automatic decisions and operator actions.
            <InfoHint label="Permanent records" text={TECHNICAL_HINTS.immutableRecord} />
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label={loading ? "Refreshing incidents" : "Refresh incidents"}
          title="Refresh incident list"
        >
          <ClipboardList size={15} />
          {loading ? "Refreshing" : "Refresh"}
        </button>
      </div>

      <section className="overview-section">
        <SectionHeader
          title="Incident history"
          description="Newest automatic decisions first"
        />
        <Card className="incident-list-card">
          {loading ? (
            <LoadingState label="Loading incidents" />
          ) : error ? (
            <ErrorState
              title="Unable to load incidents"
              body={`${error} Check your connection and try again.`}
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="No incidents recorded"
              body="No incident decisions have been recorded yet."
            />
          ) : (
            <div className="incident-list">
              {items.map((item) => (
                <Link
                  className="incident-list-row"
                  to={`/incidents/${encodeURIComponent(item.decision_id)}`}
                  key={item.decision_id}
                >
                  <div className="incident-main">
                    <strong>{item.decision_id}</strong>
                    <span>
                      {formatWhen(item.created_at)} · Automatic: {sentenceCase(item.automatic_decision_status)}
                    </span>
                  </div>
                  <div className="incident-state">
                    <StatusBadge tone={outcomeTone(item.projected_outcome)}>
                      {outcomeLabel(item.projected_outcome)}
                    </StatusBadge>
                    <span>
                      {item.final_severity ? sentenceCase(item.final_severity) : "Severity pending"}
                    </span>
                  </div>
                  <ArrowUpRight size={16} aria-hidden="true" />
                </Link>
              ))}
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
