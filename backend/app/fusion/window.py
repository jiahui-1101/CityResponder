"""Stateless evaluation of one incident-confirmation window."""

from datetime import datetime

from app.fusion.schemas import (
    ConfirmationWindowResult,
    FusionConfidenceResult,
    SupportingChannelResult,
)


CONFIDENCE_THRESHOLD = 40.0
REQUIRED_SUPPORTING_CHANNELS = 2
WINDOW_DURATION_SECONDS = 1


def evaluate_confirmation_window(
    confidence: FusionConfidenceResult,
    supporting: SupportingChannelResult,
    window_timestamp: datetime,
) -> ConfirmationWindowResult:
    """Evaluate C and support requirements for the supplied window only."""

    reasons: list[str] = []
    confidence_pass = _confidence_pass(confidence, reasons)
    supporting_pass = _supporting_pass(supporting, reasons)
    window_pass = _window_pass(confidence_pass, supporting_pass)
    if window_pass is True:
        status = "passed"
    elif window_pass is False:
        status = "failed"
    else:
        status = "unresolved"
    return ConfirmationWindowResult(
        window_timestamp=window_timestamp,
        status=status,
        confidence_score=confidence.confidence_score,
        confidence_threshold=CONFIDENCE_THRESHOLD,
        confidence_pass=confidence_pass,
        supporting_count=supporting.supporting_count,
        required_supporting_count=REQUIRED_SUPPORTING_CHANNELS,
        supporting_pass=supporting_pass,
        window_pass=window_pass,
        window_duration_seconds=WINDOW_DURATION_SECONDS,
        reasons=reasons,
        audit_references=(
            confidence.audit_references + supporting.audit_references
        ),
    )


def _confidence_pass(
    confidence: FusionConfidenceResult,
    reasons: list[str],
) -> bool | None:
    if confidence.confidence_score is None or confidence.status != "calculated":
        reasons.append("confidence C is not calculated")
        return None
    if not 0.0 <= confidence.confidence_score <= 100.0:
        reasons.append("confidence C is outside the valid 0..100 range")
        return None
    passed = confidence.confidence_score >= CONFIDENCE_THRESHOLD
    if not passed:
        reasons.append("confidence C is below the threshold of 40")
    return passed


def _supporting_pass(
    supporting: SupportingChannelResult,
    reasons: list[str],
) -> bool | None:
    count = supporting.supporting_count
    if count is None or supporting.status != "evaluated":
        reasons.append("supporting-channel count is not evaluated")
        return None
    passed = count >= REQUIRED_SUPPORTING_CHANNELS
    if not passed:
        reasons.append("fewer than 2 supporting channels")
    return passed


def _window_pass(
    confidence_pass: bool | None,
    supporting_pass: bool | None,
) -> bool | None:
    if confidence_pass is False or supporting_pass is False:
        return False
    if confidence_pass is True and supporting_pass is True:
        return True
    return None
