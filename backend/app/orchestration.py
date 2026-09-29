"""End-to-end Part 3 intelligence decision orchestration."""

from collections.abc import Sequence

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.fusion.confidence import calculate_fusion_confidence
from app.fusion.evaluation import FusionEvaluationService
from app.fusion.historical import HistoricalNormalizationPolicy
from app.fusion.schemas import (
    ConfirmationSequenceResult,
    ConfirmationWindowResult,
    FusionConfidenceResult,
    FusionEvaluation,
    FusionInput,
    HistoricalBaselineContext,
    SupportingChannelResult,
    TemporalObservation,
)
from app.fusion.sensors import SensorNormalizationPolicy
from app.fusion.sequence import evaluate_confirmation_sequence
from app.fusion.supporting import SupportingChannelPolicy, evaluate_supporting_channels
from app.fusion.temporal import TemporalNormalizationPolicy
from app.fusion.vision import VisionNormalizationPolicy
from app.fusion.service import build_fusion_input
from app.fusion.window import evaluate_confirmation_window
from app.severity.calculator import SeverityScoreResult, calculate_severity_score
from app.severity.classification import (
    SeverityClassificationPolicy,
    SeverityClassificationResult,
    classify_severity,
)
from app.severity.decision import IncidentDecision, build_incident_decision
from app.severity.persistence import persist_incident_decision
from app.severity.schemas import SeverityInput
from app.severity.service import SeverityComponentProvider, build_severity_input
from app.vision.schemas import PerceptionSnapshot


class IntelligenceDecisionResult(BaseModel):
    """Complete auditable output of one three-window orchestration run."""

    fusion_inputs: list[FusionInput]
    fusion_evaluations: list[FusionEvaluation]
    fusion_confidences: list[FusionConfidenceResult]
    supporting_channels: list[SupportingChannelResult]
    confirmation_windows: list[ConfirmationWindowResult]
    confirmation_sequence: ConfirmationSequenceResult
    severity_input: SeverityInput
    severity_score: SeverityScoreResult
    severity_classification: SeverityClassificationResult
    incident_decision: IncidentDecision
    warnings: list[str] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class IntelligenceDecisionService:
    """Stateless coordinator for existing Part 3 calculation services."""

    def run(
        self,
        snapshots: Sequence[PerceptionSnapshot],
        *,
        sensor_policy: SensorNormalizationPolicy | None = None,
        temporal_policy: TemporalNormalizationPolicy | None = None,
        vision_policy: VisionNormalizationPolicy | None = None,
        historical_context: HistoricalBaselineContext | None = None,
        historical_policy: HistoricalNormalizationPolicy | None = None,
        supporting_policy: SupportingChannelPolicy | None = None,
        severity_component_provider: SeverityComponentProvider | None = None,
        severity_classification_policy: SeverityClassificationPolicy | None = None,
        db: Session | None = None,
        persistence: bool = False,
    ) -> IntelligenceDecisionResult:
        """Run exactly three supplied windows and optionally persist the decision."""

        if len(snapshots) != 3:
            raise ValueError("exactly 3 ordered PerceptionSnapshot objects are required")
        if persistence and db is None:
            raise ValueError("db is required when persistence=True")

        fusion_inputs: list[FusionInput] = []
        evaluations: list[FusionEvaluation] = []
        confidences: list[FusionConfidenceResult] = []
        supporting_results: list[SupportingChannelResult] = []
        windows: list[ConfirmationWindowResult] = []
        prior_observations: list[TemporalObservation] = []
        evaluation_service = FusionEvaluationService()

        for snapshot in snapshots:
            fusion_input = build_fusion_input(snapshot)
            evaluation = evaluation_service.evaluate(
                fusion_input,
                prior_observations=prior_observations,
                sensor_policy=sensor_policy,
                temporal_policy=temporal_policy,
                vision_policy=vision_policy,
                historical_context=historical_context,
                historical_policy=historical_policy,
            )
            confidence = calculate_fusion_confidence(evaluation)
            supporting = evaluate_supporting_channels(evaluation, supporting_policy)
            window = evaluate_confirmation_window(
                confidence,
                supporting,
                evaluation.t.current_observation_timestamp or snapshot.generated_at,
            )
            fusion_inputs.append(fusion_input)
            evaluations.append(evaluation)
            confidences.append(confidence)
            supporting_results.append(supporting)
            windows.append(window)
            prior_observations.append(_temporal_observation(fusion_input))

        sequence = evaluate_confirmation_sequence(windows)
        severity_input = build_severity_input(
            snapshots[-1],
            confirmation=sequence,
            component_provider=severity_component_provider,
        )
        severity_score = calculate_severity_score(severity_input)
        classification = classify_severity(
            severity_score,
            policy=severity_classification_policy,
        )
        incident_decision = build_incident_decision(
            sequence,
            confidences[-1],
            severity_score,
            classification,
        )

        warnings = _collect_warnings(
            fusion_inputs,
            evaluations,
            confidences,
            supporting_results,
            windows,
            sequence,
            severity_input,
            severity_score,
            classification,
            incident_decision,
        )
        unavailable_inputs = sorted(
            {
                item
                for fusion_input in fusion_inputs
                for item in fusion_input.unavailable_inputs
            }
        )
        if persistence:
            persist_incident_decision(db, incident_decision)

        return IntelligenceDecisionResult(
            fusion_inputs=fusion_inputs,
            fusion_evaluations=evaluations,
            fusion_confidences=confidences,
            supporting_channels=supporting_results,
            confirmation_windows=windows,
            confirmation_sequence=sequence,
            severity_input=severity_input,
            severity_score=severity_score,
            severity_classification=classification,
            incident_decision=incident_decision,
            warnings=warnings,
            unavailable_inputs=unavailable_inputs,
        )


def run_intelligence_decision(
    snapshots: Sequence[PerceptionSnapshot],
    **kwargs: object,
) -> IntelligenceDecisionResult:
    """Convenience wrapper around :class:`IntelligenceDecisionService`."""

    return IntelligenceDecisionService().run(snapshots, **kwargs)


def _temporal_observation(fusion_input: FusionInput) -> TemporalObservation:
    timestamps = [
        timestamp
        for timestamp in fusion_input.t.source_timestamps.values()
        if timestamp is not None
    ]
    fresh_sources = [
        source
        for source, timestamp in fusion_input.t.source_timestamps.items()
        if timestamp is not None
    ]
    return TemporalObservation(
        observation_timestamp=max(timestamps) if timestamps else fusion_input.generated_at,
        source_timestamps=dict(fusion_input.t.source_timestamps),
        fresh_sources=fresh_sources,
    )


def _collect_warnings(*parts: object) -> list[str]:
    warnings: list[str] = []
    for part in parts:
        if isinstance(part, BaseModel):
            for field in ("warnings", "reasons"):
                values = getattr(part, field, None)
                if values:
                    warnings.extend(str(value) for value in values)
    return warnings
