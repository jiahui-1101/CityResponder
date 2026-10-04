"""Runtime bridge from live vision evidence to automatic incident decisions."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.fusion.policies import FireFusionEngine, FireFusionResult, WindowEvidence
from app.fusion.schemas import (
    FusionConfidenceResult,
    SupportingChannelResult,
)
from app.severity.calculator import calculate_severity_score
from app.severity.classification import SeverityClassificationResult, classify_severity
from app.severity.decision import IncidentDecision, build_incident_decision
from app.severity.persistence import persist_incident_decision
from app.severity.policies import SeverityComponentPolicyProvider, SeverityPolicyClassification
from app.severity.service import build_severity_input
from app.vision.snapshot import get_perception_snapshot
from app.vision.schemas import PerceptionSnapshot
from app.fusion.sequence import evaluate_confirmation_sequence
from app.fusion.window import evaluate_confirmation_window


logger = logging.getLogger(__name__)
_MAX_WINDOWS = 3


class AutomaticIncidentCoordinator:
    """Evaluate one three-window decision sequence from live vision events.

    Vision remains an evidence source; this bridge never sends actuator
    commands. It persists one decision when the evidence state changes so the
    operator incident list can show both confirmed and policy-rejected alerts.
    """

    def __init__(self) -> None:
        self._snapshots: deque[PerceptionSnapshot] = deque(maxlen=_MAX_WINDOWS)
        self._last_window: datetime | None = None
        self._last_signal_state = False
        self._last_decision_status: str | None = None

    def observe(self, db: Session) -> IncidentDecision | None:
        """Consume the newest projection and persist a changed decision state."""

        snapshot = get_perception_snapshot(db)
        if snapshot.detection is None:
            self._reset()
            return None

        window = _as_utc(snapshot.detection.frame.timestamp).replace(microsecond=0)
        if self._last_window is not None:
            gap = (window - self._last_window).total_seconds()
            if gap == 0:
                return None
            if gap != 1:
                self._snapshots.clear()
        self._last_window = window
        self._snapshots.append(snapshot)

        signal_state = _has_incident_signal(snapshot)
        if not signal_state:
            self._last_signal_state = False
            self._last_decision_status = None
            self._snapshots.clear()
            return None
        self._last_signal_state = True
        if len(self._snapshots) < _MAX_WINDOWS:
            return None

        decision = build_runtime_incident_decision(tuple(self._snapshots))
        if decision is None:
            return None
        if decision.decision_status == self._last_decision_status:
            self._snapshots = deque(list(self._snapshots)[-2:], maxlen=_MAX_WINDOWS)
            return None

        persist_incident_decision(db, decision)
        self._last_decision_status = decision.decision_status
        self._snapshots = deque(list(self._snapshots)[-2:], maxlen=_MAX_WINDOWS)
        return decision

    def _reset(self) -> None:
        self._snapshots.clear()
        self._last_window = None
        self._last_signal_state = False
        self._last_decision_status = None


def build_runtime_incident_decision(
    snapshots: Iterable[PerceptionSnapshot],
) -> IncidentDecision | None:
    """Build one production decision from exactly three real snapshots."""

    ordered = tuple(snapshots)
    if len(ordered) != _MAX_WINDOWS or any(item.detection is None for item in ordered):
        return None

    prior_windows: list[WindowEvidence] = []
    window_results = []
    last_confidence: FusionConfidenceResult | None = None
    last_supporting: SupportingChannelResult | None = None
    for snapshot in ordered:
        sensors = {sensor.sensor_type: sensor for sensor in snapshot.sensors}
        engine = FireFusionEngine(window_evidence_history=prior_windows)
        fusion_result = engine.evaluate(
            mq2=sensors["MQ2"],
            dht22=sensors["DHT22"],
            mq2_freshness=snapshot.freshness.mq2,
            dht22_freshness=snapshot.freshness.dht22,
            detections=snapshot.detection.detections,
            vision_freshness=snapshot.freshness.detection,
            button=sensors["BUTTON"],
            person_in_hazard=snapshot.person_in_hazard,
        )
        prior_windows.append(
            WindowEvidence(
                s_score=fusion_result.s_score,
                v_score=fusion_result.v_score,
                button_pressed=fusion_result.button_pressed,
            )
        )
        prior_windows[:] = prior_windows[-2:]
        confidence = _confidence_result(fusion_result)
        supporting = _supporting_result(fusion_result)
        timestamp = _as_utc(snapshot.detection.frame.timestamp).replace(microsecond=0)
        window_results.append(evaluate_confirmation_window(confidence, supporting, timestamp))
        last_confidence = confidence
        last_supporting = supporting

    sequence = evaluate_confirmation_sequence(window_results)
    last_snapshot = ordered[-1]
    hazard_zone = last_snapshot.detection.building_roi
    severity_input = build_severity_input(
        last_snapshot,
        confirmation=sequence,
        component_provider=SeverityComponentPolicyProvider(hazard_zone=hazard_zone),
    )
    severity_score = calculate_severity_score(severity_input)
    classification: SeverityClassificationResult = classify_severity(
        severity_score,
        policy=SeverityPolicyClassification(),
    )
    if last_confidence is None or last_supporting is None:
        return None
    return build_incident_decision(sequence, last_confidence, severity_score, classification)


def _confidence_result(fusion_result: FireFusionResult) -> FusionConfidenceResult:
    result = fusion_result
    weights = {"S": 0.30, "T": 0.20, "V": 0.35, "H": 0.15}
    scores = {"S": result.s_score, "T": result.t_score, "V": result.v_score, "H": result.h_score}
    contributions = {
        name: score * weights[name] if score is not None else None
        for name, score in scores.items()
    }
    calculated = result.confidence is not None
    return FusionConfidenceResult(
        status="calculated" if calculated else "not_calculated",
        confidence_score=result.confidence,
        s_score=result.s_score,
        t_score=result.t_score,
        v_score=result.v_score,
        h_score=result.h_score,
        weights=weights,
        weighted_contributions=contributions,
        reasons=list(result.reasons),
        audit_references=[],
        calculated_at=datetime.now(timezone.utc),
    )


def _supporting_result(fusion_result: FireFusionResult) -> SupportingChannelResult:
    decisions = list(fusion_result.supporting_details)
    supporting = [item.channel for item in decisions if item.decision == "supporting"]
    non_supporting = [item.channel for item in decisions if item.decision == "not_supporting"]
    not_evaluated = [item.channel for item in decisions if item.decision == "not_evaluated"]
    return SupportingChannelResult(
        status="evaluated" if not not_evaluated else "not_evaluated",
        supporting_channels=supporting,
        non_supporting_channels=non_supporting,
        not_evaluated_channels=not_evaluated,
        supporting_count=len(supporting) if not not_evaluated else None,
        decisions=decisions,
        audit_references=[],
        evaluated_at=datetime.now(timezone.utc),
    )


def _has_incident_signal(snapshot: PerceptionSnapshot) -> bool:
    if snapshot.detection is not None and any(
        item.class_name.strip().lower() in {"fire", "smoke"}
        for item in snapshot.detection.detections
    ):
        return True
    button = next((item for item in snapshot.sensors if item.sensor_type == "BUTTON"), None)
    return bool(button and button.available and button.value in (True, 1, "1", "true", "pressed", "on"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


automatic_incident_coordinator = AutomaticIncidentCoordinator()
