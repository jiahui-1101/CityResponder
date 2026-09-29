"""Historical Baseline / Anomaly (H) channel evaluation boundary."""

from typing import Protocol

from app.fusion.schemas import (
    FusionInput,
    HistoricalBaselineContext,
    HistoricalChannelEvaluation,
)


class HistoricalNormalizationPolicy(Protocol):
    """Future source-backed policy for converting H evidence into 0..1."""

    def score(
        self,
        context: HistoricalBaselineContext,
    ) -> float:
        """Return an explicitly defined score in the inclusive 0..1 range."""


def evaluate_historical_channel(
    fusion_input: FusionInput,
    context: HistoricalBaselineContext | None = None,
    policy: HistoricalNormalizationPolicy | None = None,
) -> HistoricalChannelEvaluation:
    """Evaluate only explicitly supplied H context, without hidden state."""

    if context is None:
        return _evaluation(
            status="unavailable",
            score=None,
            context=HistoricalBaselineContext(),
            reasons=["historical baseline/anomaly context is unavailable"],
            fusion_input=fusion_input,
        )
    if not context.baseline_available:
        return _evaluation(
            status="not_evaluated",
            score=None,
            context=context,
            reasons=["historical baseline is not available for evaluation"],
            fusion_input=fusion_input,
        )
    if policy is None:
        return _evaluation(
            status="not_evaluated",
            score=None,
            context=context,
            reasons=[
                "H score not evaluated: normalization policy is not configured"
            ],
            fusion_input=fusion_input,
        )
    try:
        score = float(policy.score(context))
        if not 0.0 <= score <= 1.0:
            raise ValueError("policy score must be between 0 and 1")
        return _evaluation(
            status="available",
            score=score,
            context=context,
            reasons=[],
            fusion_input=fusion_input,
        )
    except Exception as exc:
        return _evaluation(
            status="not_evaluated",
            score=None,
            context=context,
            reasons=[f"H score policy failed: {exc}"],
            fusion_input=fusion_input,
        )


def _evaluation(
    *,
    status: str,
    score: float | None,
    context: HistoricalBaselineContext,
    reasons: list[str],
    fusion_input: FusionInput,
) -> HistoricalChannelEvaluation:
    return HistoricalChannelEvaluation(
        status=status,
        score=score,
        baseline_available=context.baseline_available,
        baseline_metadata=context.baseline_metadata,
        current_evidence=context.current_evidence,
        anomaly_evidence=context.anomaly_evidence,
        reasons=reasons,
        source_references=(
            context.source_references or fusion_input.h.source_references
        ),
    )
