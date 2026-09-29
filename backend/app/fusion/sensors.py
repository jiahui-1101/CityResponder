"""Sensors (S) channel evaluation boundary."""

from typing import Protocol

from app.sensors.schemas import LatestSensorState
from app.vision.schemas import FreshnessItem

from app.fusion.schemas import FusionInput, SensorChannelEvaluation


class SensorNormalizationPolicy(Protocol):
    """Future source-backed policy for converting raw S evidence into 0..1."""

    def score(self, mq2: LatestSensorState, dht22: LatestSensorState) -> float:
        """Return an explicitly defined score in the inclusive 0..1 range."""


def evaluate_sensor_channel(
    fusion_input: FusionInput,
    policy: SensorNormalizationPolicy | None = None,
) -> SensorChannelEvaluation:
    """Evaluate S availability/freshness without inventing normalization."""

    mq2 = fusion_input.s.mq2
    dht22 = fusion_input.s.dht22
    mq2_freshness = _freshness_for("MQ2", fusion_input)
    dht22_freshness = _freshness_for("DHT22", fusion_input)
    reasons: list[str] = []
    available_sources = (mq2.available, dht22.available)
    if not mq2.available:
        reasons.append("MQ2 evidence is unavailable")
    if not dht22.available:
        reasons.append("DHT22 evidence is unavailable")

    stale = any(
        item.stale is True
        for item in (mq2_freshness, dht22_freshness)
    )
    if mq2_freshness.stale is True:
        reasons.append("MQ2 evidence is stale")
    if dht22_freshness.stale is True:
        reasons.append("DHT22 evidence is stale")

    if not all(available_sources):
        status = "unavailable" if not any(available_sources) else "incomplete"
        return _evaluation(
            status=status,
            score=None,
            mq2=mq2,
            dht22=dht22,
            mq2_freshness=mq2_freshness,
            dht22_freshness=dht22_freshness,
            reasons=reasons,
            fusion_input=fusion_input,
        )
    if stale:
        return _evaluation(
            status="stale",
            score=None,
            mq2=mq2,
            dht22=dht22,
            mq2_freshness=mq2_freshness,
            dht22_freshness=dht22_freshness,
            reasons=reasons,
            fusion_input=fusion_input,
        )
    if policy is None:
        reasons.append("S score not evaluated: normalization policy is not configured")
        status = "not_evaluated"
        score = None
    else:
        try:
            score = float(policy.score(mq2, dht22))
            if not 0.0 <= score <= 1.0:
                raise ValueError("policy score must be between 0 and 1")
            status = "available"
        except Exception as exc:
            score = None
            status = "not_evaluated"
            reasons.append(f"S score policy failed: {exc}")
    return _evaluation(
        status=status,
        score=score,
        mq2=mq2,
        dht22=dht22,
        mq2_freshness=mq2_freshness,
        dht22_freshness=dht22_freshness,
        reasons=reasons,
        fusion_input=fusion_input,
    )


def _freshness_for(sensor_type: str, fusion_input: FusionInput) -> FreshnessItem:
    return {
        "MQ2": fusion_input.t.freshness.mq2,
        "DHT22": fusion_input.t.freshness.dht22,
    }[sensor_type]


def _evaluation(
    *,
    status: str,
    score: float | None,
    mq2: LatestSensorState,
    dht22: LatestSensorState,
    mq2_freshness: FreshnessItem,
    dht22_freshness: FreshnessItem,
    reasons: list[str],
    fusion_input: FusionInput,
) -> SensorChannelEvaluation:
    return SensorChannelEvaluation(
        status=status,
        score=score,
        mq2=mq2,
        dht22=dht22,
        mq2_freshness=mq2_freshness,
        dht22_freshness=dht22_freshness,
        reasons=reasons,
        source_references=fusion_input.s.source_references,
    )
