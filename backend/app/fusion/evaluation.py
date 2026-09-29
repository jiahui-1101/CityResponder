"""Stateless aggregation of the four incident-fusion channel evaluations."""

from typing import Sequence

from app.fusion.historical import HistoricalNormalizationPolicy, evaluate_historical_channel
from app.fusion.schemas import (
    FusionEvaluation,
    FusionInput,
    HistoricalBaselineContext,
    TemporalChannelEvaluation,
    TemporalObservation,
)
from app.fusion.sensors import SensorNormalizationPolicy, evaluate_sensor_channel
from app.fusion.temporal import TemporalNormalizationPolicy, evaluate_temporal_channel
from app.fusion.vision import VisionNormalizationPolicy, evaluate_vision_channel


class FusionEvaluationService:
    """Run and classify S/T/V/H evaluators without collapsing their evidence."""

    def evaluate(
        self,
        fusion_input: FusionInput,
        *,
        prior_observations: Sequence[TemporalObservation] = (),
        sensor_policy: SensorNormalizationPolicy | None = None,
        temporal_policy: TemporalNormalizationPolicy | None = None,
        vision_policy: VisionNormalizationPolicy | None = None,
        historical_context: HistoricalBaselineContext | None = None,
        historical_policy: HistoricalNormalizationPolicy | None = None,
    ) -> FusionEvaluation:
        sensor = evaluate_sensor_channel(fusion_input, policy=sensor_policy)
        temporal = evaluate_temporal_channel(
            fusion_input,
            prior_observations=prior_observations,
            policy=temporal_policy,
        )
        vision = evaluate_vision_channel(fusion_input, policy=vision_policy)
        historical = evaluate_historical_channel(
            fusion_input,
            context=historical_context,
            policy=historical_policy,
        )
        channels = {
            "S": sensor,
            "T": temporal,
            "V": vision,
            "H": historical,
        }
        available_channels = [
            channel for channel, evaluation in channels.items()
            if evaluation.status == "available"
        ]
        unavailable_channels = [
            channel for channel, evaluation in channels.items()
            if evaluation.status in {"unavailable", "incomplete"}
        ]
        stale_channels = [
            channel for channel, evaluation in channels.items()
            if evaluation.status == "stale"
        ]
        scored_channels = [
            channel for channel, evaluation in channels.items()
            if evaluation.score is not None
        ]
        unscored_channels = [
            channel for channel in channels
            if channel not in scored_channels
        ]
        warnings = [
            f"{channel}: {reason}"
            for channel, evaluation in channels.items()
            for reason in evaluation.reasons
        ]
        return FusionEvaluation(
            generated_at=fusion_input.generated_at,
            s=sensor,
            t=temporal,
            v=vision,
            h=historical,
            available_channels=available_channels,
            unavailable_channels=unavailable_channels,
            stale_channels=stale_channels,
            scored_channels=scored_channels,
            unscored_channels=unscored_channels,
            warnings=warnings,
            audit_references=fusion_input.source_references,
        )


def evaluate_fusion(
    fusion_input: FusionInput,
    *,
    prior_observations: Sequence[TemporalObservation] = (),
    sensor_policy: SensorNormalizationPolicy | None = None,
    temporal_policy: TemporalNormalizationPolicy | None = None,
    vision_policy: VisionNormalizationPolicy | None = None,
    historical_context: HistoricalBaselineContext | None = None,
    historical_policy: HistoricalNormalizationPolicy | None = None,
) -> FusionEvaluation:
    """Evaluate and classify all channels through the reusable service."""

    return FusionEvaluationService().evaluate(
        fusion_input,
        prior_observations=prior_observations,
        sensor_policy=sensor_policy,
        temporal_policy=temporal_policy,
        vision_policy=vision_policy,
        historical_context=historical_context,
        historical_policy=historical_policy,
    )
