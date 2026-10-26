import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Filter,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import {
  emptyEventFilters,
  type EventFilters,
  type EventRecord,
} from "../api/events";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui";
import { useHistoryAudit } from "../hooks/useHistoryAudit";
import { useLiveRefresh } from "../live/useLiveRefresh";
import { LabelWithHint } from "../components/InfoHint";
import {
  TECHNICAL_HINTS,
  auditEventLabel,
  formatWhen,
  sentenceCase,
} from "../copy/glossary";

const EVENT_TYPES = [
  "incident_decision",
  "operator_decision",
  "incident_evidence_retained",
  "sensor_reading",
  "vision_detection",
  "vision_road_evidence",
  "route_version",
  "traffic_command_invalidated",
  "actuator_command",
  "actuator_ack",
  "area_risk_calculated",
  "calibration_candidate",
  "calibration_validation",
  "calibration_version_approved",
  "calibration_version_activated",
  "calibration_version_rollback",
];

const ENTITY_TYPES = [
  "incident",
  "route",
  "area",
  "calibration",
  "calibration_candidate",
  "sensor",
  "actuator",
];

const groupFor = (type: string) => {
  if (type.startsWith("incident_")) return "Incident / Decision";
  if (type === "operator_decision") return "Operator Feedback";
  if (type.startsWith("sensor_") || type.startsWith("vision_"))
    return "Sensor / Perception";
  if (type.startsWith("route_") || type === "traffic_command_invalidated")
    return "Routing";
  if (type.startsWith("actuator_")) return "Street Device / Actuator";
  if (type.startsWith("area_risk")) return "Risk Intelligence";
  if (type.startsWith("calibration_")) return "Calibration / Governance";
  return "Other";
};

const entityLabel = (type: string) => {
  switch (type) {
    case "actuator":
      return "Field device";
    case "sensor":
      return "Sensor";
    case "incident":
      return "Incident";
    case "route":
      return "Route";
    case "area":
      return "Area";
    case "calibration":
      return "Calibration";
    case "calibration_candidate":
      return "Calibration candidate";
    default:
      return sentenceCase(type);
  }
};

export function HistoryAuditPage() {
  const audit = useHistoryAudit();
  const [draft, setDraft] = useState<EventFilters>(emptyEventFilters);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [newActivity, setNewActivity] = useState(false);

  useLiveRefresh(
    EVENT_TYPES,
    () => {
      if (audit.skip === 0) {
        setNewActivity(false);
        return audit.refresh();
      }
      setNewActivity(true);
      return undefined;
    },
    true,
    "history"
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    setNewActivity(false);
    audit.applyFilters(draft);
  }

  function clear() {
    setDraft(emptyEventFilters());
    audit.clearFilters();
    setNewActivity(false);
  }

  return (
    <div className="history-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Official recorded history</p>
          <h2>Audit history log</h2>
          <p>
            Permanent records of all system events, operator decisions, and field
            device updates.
          </p>
        </div>
        <div className="overview-refresh">
          <span>
            {audit.lastRefreshedAt
              ? `Updated ${formatWhen(audit.lastRefreshedAt)}`
              : "Not refreshed yet"}
          </span>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void audit.refresh()}
            disabled={audit.loading}
            title="Refresh audit history log"
          >
            <RefreshCw size={15} className={audit.loading ? "spin" : undefined} />
            {audit.loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      <Card className="audit-filter-card">
        <SectionHeader
          title="Filter audit records"
          description="Search saved events by type, target, or time period."
        />
        <form className="audit-filters" onSubmit={submit}>
          <label>
            Event type
            <select
              value={draft.eventType}
              onChange={(event) =>
                setDraft({ ...draft, eventType: event.target.value })
              }
            >
              <option value="">All event types</option>
              {EVENT_TYPES.map((type) => (
                <option value={type} key={type}>
                  {auditEventLabel(type)} · {groupFor(type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Entity type
            <select
              value={draft.entityType}
              onChange={(event) =>
                setDraft({ ...draft, entityType: event.target.value })
              }
            >
              <option value="">All entity types</option>
              {ENTITY_TYPES.map((type) => (
                <option value={type} key={type}>
                  {entityLabel(type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Entity ID
            <input
              value={draft.entityId}
              onChange={(event) =>
                setDraft({ ...draft, entityId: event.target.value })
              }
              placeholder="e.g. INC-001 or SN1"
            />
          </label>
          <label>
            From
            <input
              type="datetime-local"
              value={draft.startAt}
              onChange={(event) =>
                setDraft({ ...draft, startAt: event.target.value })
              }
            />
          </label>
          <label>
            To
            <input
              type="datetime-local"
              value={draft.endAt}
              onChange={(event) =>
                setDraft({ ...draft, endAt: event.target.value })
              }
            />
          </label>
          <div className="audit-filter-actions">
            <button
              className="button button-primary"
              type="submit"
              title="Apply filters to audit records"
            >
              <Filter size={15} />
              Apply
            </button>
            <button
              className="button button-quiet"
              type="button"
              onClick={clear}
              title="Reset all filter fields"
            >
              <X size={15} />
              Clear
            </button>
          </div>
        </form>
      </Card>

      {newActivity ? (
        <button
          className="audit-new-activity"
          type="button"
          onClick={() => {
            setNewActivity(false);
            void audit.refresh();
          }}
          title="Refresh to view new events"
        >
          <Search size={15} />
          New activity available — click to refresh
        </button>
      ) : null}

      <section className="overview-section">
        <SectionHeader
          title="Recorded events"
          description={`${audit.events.length} record(s) currently loaded; newest first`}
        />
        {audit.loading ? (
          <LoadingState label="Loading audit history" />
        ) : audit.error ? (
          <ErrorState body={audit.error} />
        ) : audit.events.length === 0 ? (
          <Card>
            <EmptyState
              title="No matching audit records"
              body="No recorded events match the selected filters."
            />
          </Card>
        ) : (
          <Card className="audit-list-card">
            <div className="audit-list">
              {audit.events.map((record) => (
                <AuditRecord
                  key={record.id}
                  record={record}
                  expanded={expanded === record.id}
                  onToggle={() =>
                    setExpanded(expanded === record.id ? null : record.id)
                  }
                />
              ))}
            </div>
            {audit.hasMore ? (
              <div className="audit-load-more">
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => void audit.loadMore()}
                  disabled={audit.loadingMore}
                  title="Load earlier events"
                >
                  {audit.loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            ) : null}
          </Card>
        )}
      </section>

      <p className="audit-immutability-note">
        <ShieldCheck size={14} />
        Records are permanently preserved. This log is read-only; no history can be
        edited or deleted.
      </p>
    </div>
  );
}

function AuditRecord({
  record,
  expanded,
  onToggle,
}: {
  record: EventRecord;
  expanded: boolean;
  onToggle: () => void;
}) {
  const operator = record.event_type === "operator_decision";

  return (
    <article className={`audit-record ${expanded ? "expanded" : ""}`}>
      <button
        className="audit-record-summary"
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        title="Click to expand or collapse event details"
      >
        <span className="audit-expand">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <time dateTime={record.created_at}>
          {formatWhen(record.created_at)}
        </time>
        <div className="audit-event-title">
          <strong>{auditEventLabel(record.event_type)}</strong>
          <span>{groupFor(record.event_type)}</span>
        </div>
        <div className="audit-entity">
          <span>{entityLabel(record.entity_type)}</span>
          <strong>{record.entity_id}</strong>
        </div>
        <StatusBadge tone={operator ? "info" : "neutral"}>
          {operator ? "Operator feedback" : "Permanent record"}
        </StatusBadge>
      </button>

      {expanded ? (
        <div className="audit-record-details">
          <div className="audit-detail-grid">
            <Fact
              label="Reason code"
              value={
                record.reason_code
                  ? sentenceCase(record.reason_code)
                  : "Unavailable"
              }
            />
            <Fact
              label="Explanation"
              value={record.human_readable_reason ?? "Unavailable"}
            />
            <CrossLink record={record} />
          </div>

          {operator ? <OperatorEvidence payload={record.payload} /> : null}

          <details className="audit-raw">
            <summary>Raw event data</summary>
            <pre>{JSON.stringify(record.payload, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </article>
  );
}

function OperatorEvidence({ payload }: { payload: Record<string, unknown> }) {
  return (
    <div className="audit-operator-evidence">
      <Badge tone="info">
        {sentenceCase(String(payload.action ?? "Operator action"))}
      </Badge>
      <span>
        Operator: {String(payload.operator_id ?? "Unavailable")} ·{" "}
        {sentenceCase(String(payload.operator_role ?? "Unavailable"))}
      </span>
      <strong>
        {String(payload.written_reason ?? "No written reason provided")}
      </strong>
      <span>Incident {String(payload.incident_decision_id ?? "Unavailable")}</span>
    </div>
  );
}

function CrossLink({ record }: { record: EventRecord }) {
  if (record.entity_type === "incident") {
    return (
      <Fact
        label="Linked view"
        valueLink={`/incidents/${encodeURIComponent(record.entity_id)}`}
        value="View incident details"
      />
    );
  }
  if (record.entity_type === "route") {
    return (
      <Fact
        label="Linked view"
        valueLink="/response"
        value="View emergency response"
      />
    );
  }
  if (
    record.entity_type === "calibration" ||
    record.entity_type === "calibration_candidate"
  ) {
    return (
      <Fact
        label="Linked view"
        valueLink="/admin"
        value="View calibration governance"
      />
    );
  }
  return <Fact label="Linked view" value="None available" />;
}

function Fact({
  label,
  value,
  valueLink,
  hint,
}: {
  label: string;
  value: string;
  valueLink?: string;
  hint?: string;
}) {
  return (
    <div className="fact">
      {hint ? (
        <LabelWithHint label={label} hint={hint} />
      ) : (
        <span>{label}</span>
      )}
      {valueLink ? (
        <Link to={valueLink} title={`Navigate to ${value}`}>
          <strong>
            {value} <ExternalLink size={12} />
          </strong>
        </Link>
      ) : (
        <strong>{value}</strong>
      )}
    </div>
  );
}
