import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { AlertTriangle, ArrowUpRight, X } from "lucide-react";
import { Card } from "./ui";

export type OperatorDecisionAction =
  | "confirm"
  | "reject"
  | "cancel"
  | "start_response"
  | "manual_stop"
  | "restore_safe_default";

type ActionRule = {
  allowedStatuses?: string[];
  allowedLifecycles?: string[];
  disabledReason: string;
};

// Keep operator availability policy in one editable table.
const ACTION_RULES: Record<OperatorDecisionAction, ActionRule> = {
  confirm: { allowedStatuses: ["not_confirmed", "alert"], disabledReason: "This incident already has an operator decision." },
  reject: { allowedStatuses: ["not_confirmed", "alert"], disabledReason: "This incident already has an operator decision." },
  cancel: { allowedStatuses: ["not_confirmed", "alert"], disabledReason: "This incident already has an operator decision." },
  start_response: { allowedStatuses: ["confirmed"], allowedLifecycles: ["DISPATCHED"], disabledReason: "A confirmed, dispatched incident is required." },
  manual_stop: { allowedStatuses: ["confirmed"], allowedLifecycles: ["DISPATCHED", "RESPONDING", "EN_ROUTE", "ARRIVED", "RESOLVED", "SAFE_DEFAULT"], disabledReason: "Manual stop is unavailable for the current decision or lifecycle." },
  restore_safe_default: { allowedStatuses: ["not_confirmed", "alert", "confirmed"], allowedLifecycles: ["DISPATCHED", "RESPONDING", "EN_ROUTE", "ARRIVED", "RESOLVED", "STOPPED"], disabledReason: "Safe default is unavailable for the current decision or lifecycle." },
};

type ActionDetails = {
  title: string;
  buttonLabel: string;
  description: string;
  danger?: boolean;
  warning?: string;
};

const ACTION_DETAILS: Record<OperatorDecisionAction, ActionDetails> = {
  confirm: {
    title: "Confirm incident",
    buttonLabel: "Confirm incident",
    description: "Confirm the alert and record your operational reason.",
  },
  reject: {
    title: "Reject incident",
    buttonLabel: "Reject incident",
    description: "Reject this alert and record why no response is required.",
  },
  cancel: {
    title: "Cancel incident",
    buttonLabel: "Cancel incident",
    description: "Cancel the incident and record the reason for closing it.",
  },
  start_response: {
    title: "Start response",
    buttonLabel: "Start response",
    description: "Start the coordinated response for this confirmed incident.",
  },
  manual_stop: {
    title: "Manual stop",
    buttonLabel: "Manual stop",
    description: "Stop the active response using an operator override.",
    danger: true,
    warning: "This will stop the active response. Make sure responders are ready for a manual override.",
  },
  restore_safe_default: {
    title: "Restore safe default",
    buttonLabel: "Restore safe default",
    description: "Return connected emergency hardware to its safe default state.",
    danger: true,
    warning: "This will close the gate and turn off the buzzer. Use it only if the system is unsafe.",
  },
};

const FINAL_DECISION_LABELS: Record<string, string> = {
  confirmed: "Confirmed",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

type OperatorDecisionPanelProps = {
  status: string;
  lifecycle: string;
  incidentId: string;
  onAction: (action: OperatorDecisionAction, reason: string) => Promise<void>;
};

function normalizeStatus(status: string) {
  const normalized = status.trim().toLowerCase();
  if (normalized === "confirm") return "confirmed";
  if (normalized === "reject") return "rejected";
  if (normalized === "cancel") return "cancelled";
  return normalized;
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unable to complete this action.";
}

export function OperatorDecisionPanel({ status, lifecycle, incidentId, onAction }: OperatorDecisionPanelProps) {
  const [selectedAction, setSelectedAction] = useState<OperatorDecisionAction | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const normalizedStatus = normalizeStatus(status);
  const normalizedLifecycle = lifecycle.trim().toUpperCase();
  const finalDecisionLabel = FINAL_DECISION_LABELS[normalizedStatus];

  const isAllowed = (action: OperatorDecisionAction) => {
    const rule = ACTION_RULES[action];
    const statusAllowed = !rule.allowedStatuses || rule.allowedStatuses.includes(normalizedStatus);
    const lifecycleAllowed = !rule.allowedLifecycles || rule.allowedLifecycles.includes(normalizedLifecycle);
    return statusAllowed && lifecycleAllowed;
  };
  const isDisabled = (action: OperatorDecisionAction) => isRunning || !isAllowed(action);
  const disabledTitle = (action: OperatorDecisionAction) => isAllowed(action) ? undefined : ACTION_RULES[action].disabledReason;

  useEffect(() => {
    if (!selectedAction) return;
    const frame = window.requestAnimationFrame(() => textareaRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [selectedAction]);

  useEffect(() => {
    if (!selectedAction) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isRunning) closeDialog();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [selectedAction, isRunning]);

  function openDialog(action: OperatorDecisionAction, trigger: HTMLButtonElement) {
    if (isDisabled(action)) return;
    triggerRef.current = trigger;
    setSelectedAction(action);
    setReason("");
    setError(null);
  }

  function closeDialog() {
    if (isRunning) return;
    setSelectedAction(null);
    setReason("");
    setError(null);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) closeDialog();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedAction || reason.trim().length < 3) return;
    setIsRunning(true);
    setError(null);
    try {
      await onAction(selectedAction, reason.trim());
      setSelectedAction(null);
      setReason("");
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsRunning(false);
    }
  }

  const details = selectedAction ? ACTION_DETAILS[selectedAction] : null;

  return <>
    <Card className="decision-card operator-decision-panel">
      <header className="operator-panel-header">
        <div>
          <h3>Operator decision</h3>
          <p>Manage incident decisions and response controls.</p>
        </div>
        <p className="operator-current-lifecycle">Current lifecycle: <strong>{normalizedLifecycle || "DISPATCHED"}</strong></p>
      </header>

      <div className="operator-control-row">
        <div className="operator-control-copy">
          <h4>Incident decision</h4>
          <p>Review and verify this incident.</p>
        </div>
        <div className="operator-row-actions">
          {finalDecisionLabel ? <span className="operator-final-status">{finalDecisionLabel}</span> : <>
            <button className="button button-secondary" type="button" disabled={isDisabled("cancel")} title={disabledTitle("cancel")} onClick={(event) => openDialog("cancel", event.currentTarget)}>Cancel</button>
            <button className="button button-secondary" type="button" disabled={isDisabled("reject")} title={disabledTitle("reject")} onClick={(event) => openDialog("reject", event.currentTarget)}>Reject</button>
            <button className="button button-primary" type="button" disabled={isDisabled("confirm")} title={disabledTitle("confirm")} onClick={(event) => openDialog("confirm", event.currentTarget)}>Confirm</button>
          </>}
        </div>
      </div>

      <div className="operator-control-row">
        <div className="operator-control-copy">
          <h4>Response management</h4>
          <p>Control the active response lifecycle.</p>
        </div>
        <div className="operator-row-actions">
          <button className="button button-secondary" type="button" disabled={isDisabled("manual_stop")} title={disabledTitle("manual_stop")} onClick={(event) => openDialog("manual_stop", event.currentTarget)}>Manual Stop</button>
          <button className="button button-primary" type="button" disabled={isDisabled("start_response")} title={disabledTitle("start_response")} onClick={(event) => openDialog("start_response", event.currentTarget)}>Start Response<ArrowUpRight size={14} aria-hidden="true" /></button>
        </div>
      </div>

      <div className="operator-control-row">
        <div className="operator-control-copy">
          <h4>Safety override</h4>
          <p>Restore the system to its safe default state.</p>
        </div>
        <div className="operator-row-actions">
          <button className="button button-danger operator-safe-default" type="button" disabled={isDisabled("restore_safe_default")} title={disabledTitle("restore_safe_default")} onClick={(event) => openDialog("restore_safe_default", event.currentTarget)}>Restore Safe Default</button>
        </div>
      </div>
    </Card>

    {selectedAction && details ? <div className="operator-dialog-backdrop" role="presentation" onMouseDown={handleBackdropClick}>
      <div className={`operator-dialog${details.danger ? " is-danger" : ""}`} role="dialog" aria-modal="true" aria-labelledby="operator-dialog-title" aria-describedby="operator-dialog-description">
        <div className="operator-dialog-heading">
          <div>
            <h3 id="operator-dialog-title">{details.title}</h3>
            <p id="operator-dialog-description">{details.description}</p>
          </div>
          <button className="icon-button" type="button" aria-label="Close dialog" disabled={isRunning} onClick={closeDialog}><X size={17} aria-hidden="true" /></button>
        </div>
        <p className="operator-incident-id">Incident ID · {incidentId.slice(0, 8)}</p>
        {details.warning ? <div className="operator-warning"><AlertTriangle size={16} aria-hidden="true" /><span>{details.warning}</span></div> : null}
        <form className="operator-dialog-form" onSubmit={submit}>
          <label htmlFor="operator-action-reason">Reason</label>
          <textarea ref={textareaRef} id="operator-action-reason" value={reason} disabled={isRunning} onChange={(event) => setReason(event.target.value)} placeholder="Explain the operational reason for this action" aria-describedby="operator-reason-hint" />
          <p className="operator-field-hint" id="operator-reason-hint">Required. At least 3 characters.</p>
          {error ? <p className="operator-dialog-error" role="alert">{error}</p> : null}
          <div className="operator-dialog-actions">
            <button className="button button-secondary" type="button" disabled={isRunning} onClick={closeDialog}>Back</button>
            <button className={`button ${details.danger ? "button-danger-solid" : "button-primary"}`} type="submit" disabled={isRunning || reason.trim().length < 3}>{isRunning ? "Sending…" : details.buttonLabel}</button>
          </div>
        </form>
      </div>
    </div> : null}

  </>;
}
