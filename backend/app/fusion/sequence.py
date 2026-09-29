"""Stateless three-window incident-confirmation sequence evaluation."""

from datetime import datetime, timedelta, timezone

from app.fusion.schemas import (
    ConfirmationSequenceResult,
    ConfirmationWindowResult,
    FusionSourceReference,
)


REQUIRED_CONSECUTIVE_WINDOWS = 3
WINDOW_DURATION_SECONDS = 1


def evaluate_confirmation_sequence(
    windows: list[ConfirmationWindowResult],
) -> ConfirmationSequenceResult:
    """Evaluate exactly three existing windows without recalculating evidence."""

    ordered_windows = sorted(windows, key=lambda window: window.window_timestamp)
    reasons: list[str] = []
    evaluated_at = datetime.now(timezone.utc)
    if len(ordered_windows) != REQUIRED_CONSECUTIVE_WINDOWS:
        reasons.append("exactly 3 confirmation windows are required")
        return _result(
            status="unresolved",
            incident_confirmed=None,
            consecutive=None,
            all_windows_pass=None,
            windows=ordered_windows,
            reasons=reasons,
            evaluated_at=evaluated_at,
        )

    consecutive = all(
        ordered_windows[index].window_timestamp
        - ordered_windows[index - 1].window_timestamp
        == timedelta(seconds=WINDOW_DURATION_SECONDS)
        for index in range(1, len(ordered_windows))
    )
    if not consecutive:
        reasons.append("confirmation windows are not consecutive 1-second windows")

    window_passes = [window.window_pass for window in ordered_windows]
    if all(window_pass is True for window_pass in window_passes):
        all_windows_pass: bool | None = True
    elif any(window_pass is False for window_pass in window_passes):
        all_windows_pass = False
    else:
        all_windows_pass = None
    if any(window_pass is None for window_pass in window_passes):
        reasons.append("one or more confirmation windows are unresolved")

    if consecutive and all_windows_pass is True:
        status = "confirmed"
        incident_confirmed = True
    elif consecutive and all_windows_pass is False:
        status = "not_confirmed"
        incident_confirmed = False
    else:
        status = "unresolved"
        incident_confirmed = None

    return _result(
        status=status,
        incident_confirmed=incident_confirmed,
        consecutive=consecutive,
        all_windows_pass=all_windows_pass,
        windows=ordered_windows,
        reasons=reasons,
        evaluated_at=evaluated_at,
    )


def _result(
    *,
    status: str,
    incident_confirmed: bool | None,
    consecutive: bool | None,
    all_windows_pass: bool | None,
    windows: list[ConfirmationWindowResult],
    reasons: list[str],
    evaluated_at: datetime,
) -> ConfirmationSequenceResult:
    audit_references: list[FusionSourceReference] = []
    for window in windows:
        audit_references.extend(window.audit_references)
    return ConfirmationSequenceResult(
        status=status,
        incident_confirmed=incident_confirmed,
        window_results=windows,
        consecutive=consecutive,
        all_windows_pass=all_windows_pass,
        reasons=reasons,
        audit_references=audit_references,
        evaluated_at=evaluated_at,
    )
