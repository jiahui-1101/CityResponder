"""Contracts for the isolated Phase 3 simulation boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


EvidenceSource = Literal["VISION", "MQ2", "DHT22", "IR_A", "IR_B", "BUTTON", "GATE"]


class SimulatedEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_type: EvidenceSource
    evidence_type: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    source_timestamp: datetime
    received_timestamp: datetime
    value: Any = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    frame_or_message_id: str = Field(min_length=1)
    association: str | None = None
    freshness_status: Literal["FRESH", "STALE"] = "FRESH"
    simulated: Literal[True] = True

    @model_validator(mode="after")
    def timestamps_are_consistent(self) -> "SimulatedEvidence":
        if self.received_timestamp < self.source_timestamp:
            raise ValueError("received_timestamp must not precede source_timestamp")
        return self


class EvidenceValidationResult(BaseModel):
    accepted: list[SimulatedEvidence] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)
    duplicate_ids: list[str] = Field(default_factory=list)
    out_of_order_ids: list[str] = Field(default_factory=list)


class ResponsePlan(BaseModel):
    scenario_id: str
    correlation_id: str
    status: Literal[
        "SIMULATED", "PENDING_REVIEW", "ACKNOWLEDGED_IN_SIMULATION", "FAILED_IN_SIMULATION"
    ]
    evidence_summary: dict[str, Any]
    verification_result: str
    confidence: float | None
    severity: str | None
    contributing_factors: list[str]
    affected_location: str
    selected_route: dict[str, Any] | None
    alternative_route: dict[str, Any] | None
    blocked_or_uncertain_roads: list[str]
    road_states: dict[str, str] = Field(default_factory=dict)
    route_explanation: str
    recommended_resources: list[dict[str, Any]]
    proposed_traffic_behavior: list[dict[str, Any]]
    proposed_alert_behavior: list[dict[str, Any]]
    uncertainty_warnings: list[str]
    human_review_required: bool
    plan_version: int = 1
    simulation_marker: Literal["SIMULATED"] = "SIMULATED"
    execution: dict[str, Any]


class ScenarioResult(BaseModel):
    scenario_id: str
    name: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    explanation: list[str]
    assertions: list[dict[str, Any]]
    timings_ms: dict[str, float]
    status: Literal["PASS", "FAIL"]
    response_plan: ResponsePlan | None = None
    audit_event_count: int
    simulation_marker: Literal["SIMULATED"] = "SIMULATED"
