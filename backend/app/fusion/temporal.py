"""Stateless Temporal Consistency (T) channel evaluation."""

from datetime import datetime, timezone
from typing import Protocol, Sequence

from app.fusion.schemas import (
    FusionInput,
    TemporalChannelEvaluation,
    TemporalObservation,
)


TEMPORAL_WINDOW_MS = 1000.0


class TemporalNormalizationPolicy(Protocol):
    """Future source-backed policy for converting temporal evidence into 0..1."""

    def score(
        self,
        current: TemporalObservation,
        history: Sequence[TemporalObservation],
        gaps_ms: Sequence[float],
    ) -> float:
        """Return an explicitly defined score in the inclusive 0..1 range."""


def evaluate_temporal_channel(
    fusion_input: FusionInput,
    prior_observations: Sequence[TemporalObservation] = (),
    policy: TemporalNormalizationPolicy | None = None,
) -> TemporalChannelEvaluation:
    """Summarize explicit temporal history without maintaining hidden state."""

    current = _current_observation(fusion_input)
    reasons: list[str] = []
    if current is None:
        reasons.append("no source timestamp is available for the current observation")
        return _evaluation(
            status="unavailable",
            score=None,
            current=None,
            history=[],
            gaps_ms=[],
            reasons=reasons,
            fusion_input=fusion_input,
        )

    history = sorted(
        [*prior_observations, current],
        key=lambda observation: _as_utc(observation.observation_timestamp),
    )
    gaps_ms = _gaps_ms(history)
    consecutive_count = _consecutive_count(gaps_ms, history)
    if any(gap > TEMPORAL_WINDOW_MS for gap in gaps_ms):
        reasons.append("observation history contains a gap larger than 1 second")
    if not _has_fresh_current_sources(fusion_input):
        reasons.append("one or more current temporal sources are unavailable or stale")
        return _evaluation(
            status="stale" if _has_stale_source(fusion_input) else "incomplete",
            score=None,
            current=current,
            history=history,
            gaps_ms=gaps_ms,
            reasons=reasons,
            fusion_input=fusion_input,
            consecutive_count=consecutive_count,
        )

    if policy is None:
        reasons.append("T score not evaluated: normalization policy is not configured")
        status = "not_evaluated"
        score = None
    else:
        try:
            score = float(policy.score(current, history, gaps_ms))
            if not 0.0 <= score <= 1.0:
                raise ValueError("policy score must be between 0 and 1")
            status = "available"
        except Exception as exc:
            score = None
            status = "not_evaluated"
            reasons.append(f"T score policy failed: {exc}")
    return _evaluation(
        status=status,
        score=score,
        current=current,
        history=history,
        gaps_ms=gaps_ms,
        reasons=reasons,
        fusion_input=fusion_input,
        consecutive_count=consecutive_count,
    )


def _current_observation(fusion_input: FusionInput) -> TemporalObservation | None:
    timestamps = [
        timestamp
        for timestamp in fusion_input.t.source_timestamps.values()
        if timestamp is not None
    ]
    if not timestamps:
        return None
    return TemporalObservation(
        observation_timestamp=max(_as_utc(timestamp) for timestamp in timestamps),
        source_timestamps=fusion_input.t.source_timestamps,
        fresh_sources=[
            item.source_type
            for item in (
                fusion_input.t.freshness.mq2,
                fusion_input.t.freshness.dht22,
                fusion_input.t.freshness.detection,
                *fusion_input.t.freshness.road_evidence,
            )
            if item.available and item.stale is False
        ],
    )


def _gaps_ms(history: list[TemporalObservation]) -> list[float]:
    return [
        (
            _as_utc(history[index].observation_timestamp)
            - _as_utc(history[index - 1].observation_timestamp)
        ).total_seconds()
        * 1000
        for index in range(1, len(history))
    ]


def _consecutive_count(
    gaps_ms: list[float],
    history: list[TemporalObservation],
) -> int | None:
    if not history:
        return None
    count = 1
    for gap in reversed(gaps_ms):
        if gap > TEMPORAL_WINDOW_MS:
            break
        count += 1
    return count


def _has_fresh_current_sources(fusion_input: FusionInput) -> bool:
    freshness = fusion_input.t.freshness
    items = [freshness.mq2, freshness.dht22, freshness.detection]
    return all(item.available and item.stale is False for item in items)


def _has_stale_source(fusion_input: FusionInput) -> bool:
    freshness = fusion_input.t.freshness
    return any(
        item.stale is True
        for item in (freshness.mq2, freshness.dht22, freshness.detection)
    )


def _evaluation(
    *,
    status: str,
    score: float | None,
    current: TemporalObservation | None,
    history: list[TemporalObservation],
    gaps_ms: list[float],
    reasons: list[str],
    fusion_input: FusionInput,
    consecutive_count: int | None = None,
) -> TemporalChannelEvaluation:
    return TemporalChannelEvaluation(
        status=status,
        score=score,
        current_observation_timestamp=(
            current.observation_timestamp if current is not None else None
        ),
        source_timestamps=(
            current.source_timestamps if current is not None else {}
        ),
        freshness=fusion_input.t.freshness,
        observation_history=history,
        consecutive_observation_count=consecutive_count,
        gaps_ms=gaps_ms,
        reasons=reasons,
        source_references=fusion_input.t.source_references,
    )


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
