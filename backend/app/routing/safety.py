"""Auditable hard-block and sensor-conflict edge safety decisions."""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.routing.evidence import RoadEdgeEvidence


HARD_BLOCK_OCCUPANCY_THRESHOLD = 0.80
REQUIRED_IR_SAMPLES = 5


class IRSample(BaseModel):
    """One explicitly supplied IR sample; polarity is intentionally opaque."""

    sensor_type: str = Field(min_length=1)
    timestamp: datetime
    value: Any


class IRBlockagePolicy(Protocol):
    """Explicit interpreter for the meaning of mapped IR samples."""

    def indicates_blockage(
        self,
        samples: Sequence[IRSample],
        edge_evidence: RoadEdgeEvidence,
    ) -> bool:
        """Return whether the supplied IR evidence supports blockage."""


class EdgeSafetyDecision(BaseModel):
    """Read-only safety decision; it does not mutate a routing graph."""

    edge_id: str | None
    road_roi_name: str
    status: Literal["evaluated", "not_evaluated", "conflict"]
    hard_blocked: bool | None
    sensor_conflict: bool | None
    exclude_from_active_graph: bool | None
    raw_occupancy_ratio: float
    occupancy_threshold: float = HARD_BLOCK_OCCUPANCY_THRESHOLD
    ir_sample_count: int
    required_ir_samples: int = REQUIRED_IR_SAMPLES
    relevant_ir_samples: list[IRSample] = Field(default_factory=list)
    time_matched: bool | None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    evaluated_at: datetime


def evaluate_edge_safety(
    edge_evidence: RoadEdgeEvidence,
    ir_samples: Sequence[IRSample] = (),
    *,
    ir_policy: IRBlockagePolicy | None = None,
) -> EdgeSafetyDecision:
    """Evaluate source-backed hard-block and existing conflict evidence."""

    relevant_samples = [
        sample
        for sample in ir_samples
        if edge_evidence.mapped_ir_sensor is not None
        and sample.sensor_type == edge_evidence.mapped_ir_sensor
    ]
    reasons: list[str] = []
    sensor_conflict = edge_evidence.conflict
    if sensor_conflict is True:
        reasons.append("existing camera/IR conflict excludes the edge")
    elif sensor_conflict is None:
        reasons.append("camera/IR conflict state is unresolved")

    if edge_evidence.occupancy_ratio < HARD_BLOCK_OCCUPANCY_THRESHOLD:
        hard_blocked: bool | None = False
    else:
        hard_blocked = _evaluate_high_occupancy(
            edge_evidence,
            relevant_samples,
            ir_policy,
            reasons,
        )

    exclude = _exclusion_state(hard_blocked, sensor_conflict)
    if sensor_conflict is True:
        status: Literal["evaluated", "not_evaluated", "conflict"] = "conflict"
    elif hard_blocked is None or sensor_conflict is None:
        status = "not_evaluated"
    else:
        status = "evaluated"
    return EdgeSafetyDecision(
        edge_id=edge_evidence.road_edge_id,
        road_roi_name=edge_evidence.road_roi_name,
        status=status,
        hard_blocked=hard_blocked,
        sensor_conflict=sensor_conflict,
        exclude_from_active_graph=exclude,
        raw_occupancy_ratio=edge_evidence.occupancy_ratio,
        ir_sample_count=len(relevant_samples),
        relevant_ir_samples=relevant_samples,
        time_matched=edge_evidence.time_matched,
        reasons=reasons,
        audit_references=list(edge_evidence.source_references),
        evaluated_at=datetime.now(timezone.utc),
    )


def _evaluate_high_occupancy(
    edge_evidence: RoadEdgeEvidence,
    samples: list[IRSample],
    policy: IRBlockagePolicy | None,
    reasons: list[str],
) -> bool | None:
    if edge_evidence.mapped_ir_sensor is None:
        reasons.append("high occupancy requires an explicit road-to-IR mapping")
        return None
    if edge_evidence.freshness is None or not edge_evidence.available:
        reasons.append("mapped IR/road evidence is unavailable")
        return None
    if edge_evidence.stale is True:
        reasons.append("mapped IR/road evidence is stale")
        return None
    if edge_evidence.time_matched is not True:
        reasons.append("high occupancy requires time-matched camera/IR evidence")
        return None
    if len(samples) < REQUIRED_IR_SAMPLES:
        reasons.append("at least 5 relevant IR samples are required")
        return None
    if policy is None:
        reasons.append("IR blockage interpretation policy is not configured")
        return None
    try:
        return bool(policy.indicates_blockage(samples, edge_evidence))
    except Exception as exc:
        reasons.append(f"IR blockage policy failed: {exc}")
        return None


def _exclusion_state(
    hard_blocked: bool | None,
    sensor_conflict: bool | None,
) -> bool | None:
    if hard_blocked is True or sensor_conflict is True:
        return True
    if hard_blocked is False and sensor_conflict is False:
        return False
    return None
