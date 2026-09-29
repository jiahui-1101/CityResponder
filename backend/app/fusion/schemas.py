"""Explicit channel-boundary contracts for incident confirmation fusion."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.sensors.schemas import LatestSensorState
from app.vision.schemas import (
    Detection,
    FreshnessItem,
    PerceptionFreshnessResponse,
    VisionDetectionMessage,
    VisionRoadMessage,
)


class FusionSourceReference(BaseModel):
    """Auditable reference to an input source and its source timestamp."""

    source_type: str
    source_id: str
    timestamp: datetime | None


class SensorFusionChannel(BaseModel):
    """S channel: MQ-2 and DHT22 raw evidence only."""

    channel: Literal["S"] = "S"
    mq2: LatestSensorState
    dht22: LatestSensorState
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class TemporalFusionChannel(BaseModel):
    """T channel: source timing and freshness evidence without a score."""

    channel: Literal["T"] = "T"
    source_timestamps: dict[str, datetime | None]
    freshness: PerceptionFreshnessResponse
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class VisionFusionChannel(BaseModel):
    """V channel: Building A vision detection evidence."""

    channel: Literal["V"] = "V"
    detection: VisionDetectionMessage | None
    person_in_hazard: bool | None
    freshness: FreshnessItem
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class HistoricalBaselineChannel(BaseModel):
    """H channel placeholder until baseline/anomaly logic is defined."""

    channel: Literal["H"] = "H"
    available: bool = False
    status: Literal["not_evaluated"] = "not_evaluated"
    reason: str = "Historical baseline/anomaly logic is not implemented"
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class AuxiliaryFusionEvidence(BaseModel):
    """Evidence preserved outside fire-confirmation channels."""

    button: LatestSensorState
    ir_a: LatestSensorState
    ir_b: LatestSensorState
    road_evidence: list[VisionRoadMessage]
    button_fusion_role: Literal["TBD"] = "TBD"
    ir_fusion_role: Literal["road_infrastructure_only"] = "road_infrastructure_only"


class FusionInput(BaseModel):
    """Raw, auditable input contract for future S/T/V/H fusion scoring."""

    generated_at: datetime
    s: SensorFusionChannel
    t: TemporalFusionChannel
    v: VisionFusionChannel
    h: HistoricalBaselineChannel
    auxiliary: AuxiliaryFusionEvidence
    source_references: list[FusionSourceReference] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class SensorChannelEvaluation(BaseModel):
    """Auditable S-channel evaluation without an implicit numeric policy."""

    channel: Literal["S"] = "S"
    status: Literal["available", "incomplete", "unavailable", "stale", "not_evaluated"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    mq2: LatestSensorState
    dht22: LatestSensorState
    mq2_freshness: FreshnessItem
    dht22_freshness: FreshnessItem
    reasons: list[str] = Field(default_factory=list)
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class VisionChannelEvaluation(BaseModel):
    """Auditable V-channel evaluation without implicit score semantics."""

    channel: Literal["V"] = "V"
    status: Literal["available", "incomplete", "unavailable", "stale", "not_evaluated"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    detections: list[Detection] = Field(default_factory=list)
    person_in_hazard: bool | None
    freshness: FreshnessItem
    reasons: list[str] = Field(default_factory=list)
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class TemporalObservation(BaseModel):
    """One caller-supplied source-timestamp observation for T evaluation."""

    observation_timestamp: datetime
    source_timestamps: dict[str, datetime | None]
    fresh_sources: list[str] = Field(default_factory=list)


class TemporalChannelEvaluation(BaseModel):
    """Auditable T-channel evidence without implicit consistency scoring."""

    channel: Literal["T"] = "T"
    status: Literal["available", "incomplete", "stale", "unavailable", "not_evaluated"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    current_observation_timestamp: datetime | None
    source_timestamps: dict[str, datetime | None]
    freshness: PerceptionFreshnessResponse
    observation_history: list[TemporalObservation] = Field(default_factory=list)
    consecutive_observation_count: int | None = Field(default=None, ge=0)
    gaps_ms: list[float] = Field(default_factory=list, min_length=0)
    window_duration_ms: int = 1000
    reasons: list[str] = Field(default_factory=list)
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class HistoricalBaselineContext(BaseModel):
    """Caller-supplied baseline/anomaly context; no lookback is implied."""

    baseline_available: bool = False
    baseline_metadata: dict[str, Any] | None = None
    current_evidence: dict[str, Any] | None = None
    anomaly_evidence: dict[str, Any] | None = None
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class HistoricalChannelEvaluation(BaseModel):
    """Auditable H-channel evaluation without implicit anomaly semantics."""

    channel: Literal["H"] = "H"
    status: Literal["available", "unavailable", "not_evaluated"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_available: bool
    baseline_metadata: dict[str, Any] | None = None
    current_evidence: dict[str, Any] | None = None
    anomaly_evidence: dict[str, Any] | None = None
    reasons: list[str] = Field(default_factory=list)
    source_references: list[FusionSourceReference] = Field(default_factory=list)


class FusionEvaluation(BaseModel):
    """Separate, auditable aggregation of S/T/V/H channel evaluations."""

    generated_at: datetime
    s: SensorChannelEvaluation
    t: TemporalChannelEvaluation
    v: VisionChannelEvaluation
    h: HistoricalChannelEvaluation
    available_channels: list[str] = Field(default_factory=list)
    unavailable_channels: list[str] = Field(default_factory=list)
    stale_channels: list[str] = Field(default_factory=list)
    scored_channels: list[str] = Field(default_factory=list)
    unscored_channels: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class FusionConfidenceResult(BaseModel):
    """Exact proposal formula output without incident interpretation."""

    status: Literal["calculated", "not_calculated"]
    confidence_score: float | None = Field(default=None, ge=0.0, le=100.0)
    s_score: float | None = Field(default=None, ge=0.0, le=1.0)
    t_score: float | None = Field(default=None, ge=0.0, le=1.0)
    v_score: float | None = Field(default=None, ge=0.0, le=1.0)
    h_score: float | None = Field(default=None, ge=0.0, le=1.0)
    weights: dict[str, float]
    weighted_contributions: dict[str, float | None]
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    calculated_at: datetime


class SupportingChannelDecision(BaseModel):
    """Policy decision for one channel without changing its evaluation."""

    channel: Literal["S", "T", "V", "H"]
    decision: Literal["supporting", "not_supporting", "not_evaluated"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class SupportingChannelResult(BaseModel):
    """Auditable supporting-channel decisions for future confirmation logic."""

    status: Literal["evaluated", "not_evaluated"]
    supporting_channels: list[str] = Field(default_factory=list)
    non_supporting_channels: list[str] = Field(default_factory=list)
    not_evaluated_channels: list[str] = Field(default_factory=list)
    supporting_count: int | None = Field(default=None, ge=0)
    decisions: list[SupportingChannelDecision] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    evaluated_at: datetime


class ConfirmationWindowResult(BaseModel):
    """Evaluation result for one incident-confirmation window only."""

    window_timestamp: datetime
    status: Literal["passed", "failed", "unresolved"]
    confidence_score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence_threshold: float
    confidence_pass: bool | None
    supporting_count: int | None = Field(default=None, ge=0)
    required_supporting_count: int
    supporting_pass: bool | None
    window_pass: bool | None
    window_duration_seconds: int = 1
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class ConfirmationSequenceResult(BaseModel):
    """Stateless result for exactly three confirmation windows."""

    status: Literal["confirmed", "not_confirmed", "unresolved"]
    incident_confirmed: bool | None
    required_consecutive_windows: int = 3
    window_duration_seconds: int = 1
    window_results: list[ConfirmationWindowResult]
    consecutive: bool | None
    all_windows_pass: bool | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    evaluated_at: datetime
