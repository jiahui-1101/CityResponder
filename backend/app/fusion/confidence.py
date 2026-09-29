"""Fusion Confidence C calculator using the proposal's exact weights."""

from datetime import datetime, timezone
from math import isclose

from app.fusion.schemas import FusionConfidenceResult, FusionEvaluation


FUSION_WEIGHTS = {
    "S": 0.30,
    "T": 0.20,
    "V": 0.35,
    "H": 0.15,
}


def validate_fusion_weights() -> None:
    """Validate that the fixed proposal weights sum to exactly one."""

    if not isclose(sum(FUSION_WEIGHTS.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Fusion weights must sum to 1.0")


def calculate_fusion_confidence(
    evaluation: FusionEvaluation,
) -> FusionConfidenceResult:
    """Calculate C only when all four channel scores are valid and available."""

    validate_fusion_weights()
    scores = {
        "S": evaluation.s.score,
        "T": evaluation.t.score,
        "V": evaluation.v.score,
        "H": evaluation.h.score,
    }
    reasons: list[str] = []
    for channel, score in scores.items():
        channel_evaluation = getattr(evaluation, channel.lower())
        if channel_evaluation.status != "available":
            reasons.append(
                f"{channel} channel status is {channel_evaluation.status}"
            )
        if score is None:
            reasons.append(f"{channel} channel score is null")
        elif not 0.0 <= score <= 1.0:
            reasons.append(f"{channel} channel score is outside [0,1]")

    contributions = {
        channel: score * FUSION_WEIGHTS[channel]
        if score is not None and 0.0 <= score <= 1.0
        else None
        for channel, score in scores.items()
    }
    if reasons:
        return _result(
            status="not_calculated",
            confidence_score=None,
            scores=scores,
            contributions=contributions,
            reasons=reasons,
            evaluation=evaluation,
        )

    raw_confidence = 100 * sum(contributions[channel] for channel in FUSION_WEIGHTS)
    confidence_score = min(100.0, max(0.0, raw_confidence))
    return _result(
        status="calculated",
        confidence_score=confidence_score,
        scores=scores,
        contributions=contributions,
        reasons=[],
        evaluation=evaluation,
    )


def _result(
    *,
    status: str,
    confidence_score: float | None,
    scores: dict[str, float | None],
    contributions: dict[str, float | None],
    reasons: list[str],
    evaluation: FusionEvaluation,
) -> FusionConfidenceResult:
    return FusionConfidenceResult(
        status=status,
        confidence_score=confidence_score,
        s_score=scores["S"],
        t_score=scores["T"],
        v_score=scores["V"],
        h_score=scores["H"],
        weights=dict(FUSION_WEIGHTS),
        weighted_contributions=contributions,
        reasons=reasons,
        audit_references=evaluation.audit_references,
        calculated_at=datetime.now(timezone.utc),
    )
