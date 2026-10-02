"""Concrete Fire Fusion policy implementations (TBD-FUSION-01 through 06).

Every threshold, formula, and constant in this file is sourced from the
finalized team TBD Resolutions.  Nothing is guessed or fabricated.

References
----------
TBD-FUSION-01  Sensor Normalization (S)
TBD-FUSION-02  Temporal Consistency (T)
TBD-FUSION-03  Vision Normalization (V)
TBD-FUSION-04  Historical Baseline (H)
TBD-FUSION-05  Supporting Channels
TBD-FUSION-06  Manual Button
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from app.area_risk.schemas import AreaRiskResult
from app.fusion.schemas import (
    FusionEvaluation,
    FusionInput,
    HistoricalBaselineContext,
    HistoricalChannelEvaluation,
    SensorChannelEvaluation,
    SupportingChannelDecision,
    TemporalObservation,
    VisionChannelEvaluation,
)
from app.sensors.schemas import LatestSensorState
from app.vision.schemas import Detection, FreshnessItem

# ---------------------------------------------------------------------------
# TBD-FUSION-01: Sensor Normalization (S)
# ---------------------------------------------------------------------------
# DHT22 (Temperature): normal = 30 °C, alarm = 50 °C.
# MQ-2 (Smoke):        normal = 500,    alarm = 2000.
# Normalize = (reading − normal) / (alarm − normal), clamp [0.0, 1.0].
# S = max(s_smoke, s_heat).
# Stale check: MQ-2 stale after 2.0 s; DHT22 stale after 3.0 s.
#   - If one is stale, use the other.
#   - If both are stale, S is *unavailable* → C must not be calculated.
# ---------------------------------------------------------------------------

# -- TBD-FUSION-01 constants --
MQ2_NORMAL: float = 500.0
MQ2_ALARM: float = 2000.0
DHT22_NORMAL: float = 30.0
DHT22_ALARM: float = 50.0
MQ2_STALE_SECONDS: float = 2.0    # already matches config default
DHT22_STALE_SECONDS: float = 3.0  # already matches config default


def _normalize_sensor(reading: float, normal: float, alarm: float) -> float:
    """Normalize a sensor reading into [0.0, 1.0].  (TBD-FUSION-01)"""
    raw = (reading - normal) / (alarm - normal)
    return max(0.0, min(1.0, raw))


def _is_sensor_stale(freshness: FreshnessItem, threshold_s: float) -> bool:
    """Return True if the source is stale per TBD-FUSION-01 thresholds."""
    if not freshness.available:
        return True  # unavailable ⇒ treated as stale
    if freshness.age_seconds is not None and freshness.age_seconds > threshold_s:
        return True
    return freshness.stale is True


class FireSensorNormalizationPolicy:
    """Concrete S-channel scoring policy (TBD-FUSION-01).

    Implements the ``SensorNormalizationPolicy`` protocol from
    ``app.fusion.sensors``.
    """

    def score(self, mq2: LatestSensorState, dht22: LatestSensorState) -> float:
        """Return S ∈ [0.0, 1.0] following TBD-FUSION-01 normalization rules."""
        raise NotImplementedError(
            "Use score_with_freshness(); the Protocol signature lacks freshness."
        )

    # The real entry-point used by the updated evaluation path.
    def score_with_freshness(
        self,
        mq2: LatestSensorState,
        dht22: LatestSensorState,
        mq2_freshness: FreshnessItem,
        dht22_freshness: FreshnessItem,
    ) -> tuple[float | None, str]:
        """Return ``(score, status)`` respecting TBD-FUSION-01 stale rules.

        Returns
        -------
        (score, status)
            *score* is ``None`` when both sensors are stale/unavailable.
            *status* is one of ``"available"``, ``"stale"``, ``"unavailable"``.
        """
        mq2_stale = _is_sensor_stale(mq2_freshness, MQ2_STALE_SECONDS)
        dht22_stale = _is_sensor_stale(dht22_freshness, DHT22_STALE_SECONDS)

        # --- TBD-FUSION-01: "If both are stale, S is unavailable" ---
        if mq2_stale and dht22_stale:
            return None, "unavailable"

        s_smoke: float | None = None
        s_heat: float | None = None

        if not mq2_stale and mq2.available and mq2.value is not None:
            s_smoke = _normalize_sensor(float(mq2.value), MQ2_NORMAL, MQ2_ALARM)
        if not dht22_stale and dht22.available and dht22.value is not None:
            s_heat = _normalize_sensor(float(dht22.value), DHT22_NORMAL, DHT22_ALARM)

        # --- TBD-FUSION-01: "If one is stale, use the other" ---
        available_scores = [s for s in (s_smoke, s_heat) if s is not None]
        if not available_scores:
            return None, "unavailable"

        # S = max(s_smoke, s_heat)  — TBD-FUSION-01
        return max(available_scores), "available"


# ---------------------------------------------------------------------------
# TBD-FUSION-02: Temporal Consistency (T)
# ---------------------------------------------------------------------------
# T = evidence_count / 3  over the last 3 one-second windows.
# Evidence: S >= 0.20, OR V >= 0.40, OR manual button is pressed.
# ---------------------------------------------------------------------------

TEMPORAL_WINDOW_COUNT: int = 3
S_EVIDENCE_THRESHOLD: float = 0.20  # TBD-FUSION-02
V_EVIDENCE_THRESHOLD: float = 0.40  # TBD-FUSION-02


class WindowEvidence:
    """Evidence snapshot for one 1-second window (TBD-FUSION-02)."""

    def __init__(
        self,
        s_score: float | None = None,
        v_score: float | None = None,
        button_pressed: bool = False,
    ) -> None:
        self.s_score = s_score
        self.v_score = v_score
        self.button_pressed = button_pressed

    def has_evidence(self) -> bool:
        """Return True if this window has evidence per TBD-FUSION-02 criteria."""
        # TBD-FUSION-02: S >= 0.20 OR V >= 0.40 OR manual button pressed
        if self.s_score is not None and self.s_score >= S_EVIDENCE_THRESHOLD:
            return True
        if self.v_score is not None and self.v_score >= V_EVIDENCE_THRESHOLD:
            return True
        if self.button_pressed:
            return True
        return False


class FireTemporalNormalizationPolicy:
    """Concrete T-channel scoring policy (TBD-FUSION-02).

    Implements the ``TemporalNormalizationPolicy`` protocol from
    ``app.fusion.temporal``.
    """

    def __init__(self, window_evidence_history: Sequence[WindowEvidence] = ()) -> None:
        self._window_evidence_history = list(window_evidence_history)

    def score(
        self,
        current: TemporalObservation,
        history: Sequence[TemporalObservation],
        gaps_ms: Sequence[float],
    ) -> float:
        """Return T ∈ [0.0, 1.0] = evidence_count / 3.  (TBD-FUSION-02)"""
        # Use the last 3 windows from the evidence history
        last_windows = self._window_evidence_history[-TEMPORAL_WINDOW_COUNT:]
        if not last_windows:
            return 0.0
        evidence_count = sum(1 for w in last_windows if w.has_evidence())
        # TBD-FUSION-02: T = evidence_count / 3
        return evidence_count / TEMPORAL_WINDOW_COUNT


# ---------------------------------------------------------------------------
# TBD-FUSION-03: Vision Normalization (V)
# ---------------------------------------------------------------------------
# V = max(Fire confidence, Smoke confidence).
#   - Do NOT add their confidences together.
#   - Do NOT include Person confidence.
# Minimum accepted confidence = 0.50.  Ignore detections below this value.
# Stale check: Camera frame stale after 1.0 s → V unavailable.
# ---------------------------------------------------------------------------

VISION_MIN_CONFIDENCE: float = 0.50  # TBD-FUSION-03
VISION_STALE_SECONDS: float = 1.0    # TBD-FUSION-03 (matches config default)
FIRE_CLASS_NAMES: frozenset[str] = frozenset({"fire", "Fire"})
SMOKE_CLASS_NAMES: frozenset[str] = frozenset({"smoke", "Smoke"})


class FireVisionNormalizationPolicy:
    """Concrete V-channel scoring policy (TBD-FUSION-03).

    Implements the ``VisionNormalizationPolicy`` protocol from
    ``app.fusion.vision``.
    """

    def score(
        self,
        detections: list[Detection],
        person_in_hazard: bool | None,
    ) -> float:
        """Return V ∈ [0.0, 1.0] = max(fire_conf, smoke_conf).  (TBD-FUSION-03)"""
        max_fire: float = 0.0
        max_smoke: float = 0.0

        for det in detections:
            # TBD-FUSION-03: Do NOT include Person confidence
            if det.class_name in FIRE_CLASS_NAMES:
                if det.confidence >= VISION_MIN_CONFIDENCE:  # TBD-FUSION-03
                    max_fire = max(max_fire, det.confidence)
            elif det.class_name in SMOKE_CLASS_NAMES:
                if det.confidence >= VISION_MIN_CONFIDENCE:  # TBD-FUSION-03
                    max_smoke = max(max_smoke, det.confidence)
            # Any other class (Person, etc.) is explicitly ignored — TBD-FUSION-03

        # TBD-FUSION-03: V = max(Fire confidence, Smoke confidence)
        # Do NOT add.
        return max(max_fire, max_smoke)


# ---------------------------------------------------------------------------
# TBD-FUSION-04: Historical Baseline (H)
# ---------------------------------------------------------------------------
# H = Area Risk Score / 100.
# Cold start: If no_history → H = 0 strictly.
# Do NOT use sensor anomaly detection as a replacement.
# ---------------------------------------------------------------------------


class FireHistoricalNormalizationPolicy:
    """Concrete H-channel scoring policy (TBD-FUSION-04).

    Implements the ``HistoricalNormalizationPolicy`` protocol from
    ``app.fusion.historical``.
    """

    def __init__(self, area_risk_result: AreaRiskResult | None = None) -> None:
        self._area_risk = area_risk_result

    def score(self, context: HistoricalBaselineContext) -> float:
        """Return H ∈ [0.0, 1.0].  (TBD-FUSION-04)

        * H = area_risk_score / 100 when history is available.
        * H = 0 strictly on cold start (no_history).
        * Never uses sensor anomaly detection as replacement.
        """
        # TBD-FUSION-04: Cold start fallback
        if not context.baseline_available:
            return 0.0

        if self._area_risk is None or self._area_risk.score is None:
            # TBD-FUSION-04: No history → H = 0 strictly
            return 0.0

        # TBD-FUSION-04: H = Area Risk Score / 100
        return max(0.0, min(1.0, self._area_risk.score / 100.0))


def build_historical_context(
    area_risk_result: AreaRiskResult | None,
) -> HistoricalBaselineContext:
    """Build an ``HistoricalBaselineContext`` from an ``AreaRiskResult``.

    Returns a context with ``baseline_available=True`` only when the
    area risk was successfully calculated.  (TBD-FUSION-04)
    """
    if area_risk_result is None or area_risk_result.score is None:
        # TBD-FUSION-04: no_history → cold start
        return HistoricalBaselineContext(
            baseline_available=False,
            baseline_metadata=None,
            current_evidence=None,
            anomaly_evidence=None,  # TBD-FUSION-04: never fabricate anomaly
        )
    return HistoricalBaselineContext(
        baseline_available=True,
        baseline_metadata={
            "area_id": area_risk_result.area_id,
            "area_risk_score": area_risk_result.score,
            "window_start": area_risk_result.window_start.isoformat(),
            "window_end": area_risk_result.window_end.isoformat(),
            "verified_incident_count": area_risk_result.verified_incident_count,
        },
        current_evidence=None,
        anomaly_evidence=None,  # TBD-FUSION-04: no sensor anomaly replacement
    )


# ---------------------------------------------------------------------------
# TBD-FUSION-05: Supporting Channels
# ---------------------------------------------------------------------------
# 4 independent evidence channels: MQ-2, DHT22, Camera (YOLO), Manual Button.
# A channel is a valid Supporting Channel ONLY if:
#   - It is available, AND
#   - Its normalized/confidence score >= 0.30.
# T and H do NOT count as Supporting Channels.
# Automatic fire confirmation requires at least 2 valid Supporting Channels.
# ---------------------------------------------------------------------------

SUPPORTING_SCORE_THRESHOLD: float = 0.30  # TBD-FUSION-05
BUTTON_SCORE: float = 1.0                 # TBD-FUSION-06


class FireSupportingChannelPolicy:
    """Concrete supporting-channel evaluation (TBD-FUSION-05 + TBD-FUSION-06).

    Unlike the original ``SupportingChannelPolicy`` which operates on the
    four STVH channels, this policy evaluates the **four independent
    evidence channels**: MQ-2, DHT22, Camera, and Manual Button.
    """

    def __init__(
        self,
        mq2_score: float | None = None,
        dht22_score: float | None = None,
        camera_score: float | None = None,
        button_pressed: bool = False,
        mq2_available: bool = False,
        dht22_available: bool = False,
        camera_available: bool = False,
    ) -> None:
        self.mq2_score = mq2_score
        self.dht22_score = dht22_score
        self.camera_score = camera_score
        self.button_pressed = button_pressed
        self.mq2_available = mq2_available
        self.dht22_available = dht22_available
        self.camera_available = camera_available

    def evaluate_channels(self) -> list[SupportingChannelDecision]:
        """Return supporting-channel decisions for MQ-2, DHT22, Camera, Button.

        TBD-FUSION-05: A channel is supporting iff available AND score >= 0.30.
        TBD-FUSION-06: Button press → score = 1.0 → always supporting if pressed.
        T and H are never counted.
        """
        decisions: list[SupportingChannelDecision] = []

        # --- MQ-2 (Smoke) ---  TBD-FUSION-05
        decisions.append(self._evaluate_one(
            channel_literal="MQ2",
            available=self.mq2_available,
            score=self.mq2_score,
        ))

        # --- DHT22 (Temperature) ---  TBD-FUSION-05
        decisions.append(self._evaluate_one(
            channel_literal="DHT22",
            available=self.dht22_available,
            score=self.dht22_score,
        ))

        # --- Camera (YOLO) ---  TBD-FUSION-05
        decisions.append(self._evaluate_one(
            channel_literal="Camera",
            available=self.camera_available,
            score=self.camera_score,
        ))

        # --- Manual Button ---  TBD-FUSION-06
        if self.button_pressed:
            # TBD-FUSION-06: button press → score = 1.0
            decisions.append(SupportingChannelDecision(
                channel="Button",
                decision="supporting",
                score=BUTTON_SCORE,
                reason="TBD-FUSION-06: Manual button pressed, score=1.0, counts as 1 supporting channel",
            ))
        else:
            decisions.append(SupportingChannelDecision(
                channel="Button",
                decision="not_supporting",
                score=0.0,
                reason="TBD-FUSION-06: Manual button not pressed",
            ))

        return decisions

    def count_supporting(self) -> int:
        """Return the number of valid supporting channels.  (TBD-FUSION-05)"""
        return sum(
            1 for d in self.evaluate_channels() if d.decision == "supporting"
        )

    def _evaluate_one(
        self,
        channel_literal: str,
        available: bool,
        score: float | None,
    ) -> SupportingChannelDecision:
        # TBD-FUSION-05: must be available AND score >= 0.30
        if not available or score is None:
            return SupportingChannelDecision(
                channel=channel_literal,  # type: ignore[arg-type]
                decision="not_supporting",
                score=score,
                reason=f"TBD-FUSION-05: {channel_literal} unavailable or no score",
            )
        if score >= SUPPORTING_SCORE_THRESHOLD:
            return SupportingChannelDecision(
                channel=channel_literal,  # type: ignore[arg-type]
                decision="supporting",
                score=score,
                reason=f"TBD-FUSION-05: {channel_literal} score {score:.4f} >= {SUPPORTING_SCORE_THRESHOLD}",
            )
        return SupportingChannelDecision(
            channel=channel_literal,  # type: ignore[arg-type]
            decision="not_supporting",
            score=score,
            reason=f"TBD-FUSION-05: {channel_literal} score {score:.4f} < {SUPPORTING_SCORE_THRESHOLD}",
        )


# ---------------------------------------------------------------------------
# TBD-FUSION-06: Manual Button
# ---------------------------------------------------------------------------
# A button press:
#   - Creates an alert.
#   - Counts as 1 supporting channel (score = 1.0).
#   - Does NOT skip the 3-window rule.
#   - Does NOT change the C formula.
#   - Exception: Operator manual confirm via API bypasses the
#     "at least 2 physical sensors" rule for direct dispatch.
# ---------------------------------------------------------------------------


def is_button_pressed(button: LatestSensorState) -> bool:
    """Check whether the manual button is currently pressed.  (TBD-FUSION-06)

    The button sensor reports ``value=True`` or ``value=1`` when pressed.
    """
    if not button.available or button.value is None:
        return False
    # Accept boolean True or truthy integer/string representations
    if isinstance(button.value, bool):
        return button.value
    if isinstance(button.value, (int, float)):
        return button.value != 0
    if isinstance(button.value, str):
        return button.value.lower() in {"true", "1", "pressed", "on"}
    return False


# ---------------------------------------------------------------------------
# Composite: Full Fire Fusion Engine
# ---------------------------------------------------------------------------
# C = 100 * (0.30*S + 0.20*T + 0.35*V + 0.15*H)
# Alarm threshold: C >= 40 AND 3 consecutive 1-second windows
#                  AND at least 2 independent supporting channels.
# ---------------------------------------------------------------------------

# Core formula weights (already in confidence.py; repeated here for reference)
WEIGHT_S: float = 0.30
WEIGHT_T: float = 0.20
WEIGHT_V: float = 0.35
WEIGHT_H: float = 0.15
CONFIDENCE_THRESHOLD: float = 40.0
REQUIRED_CONSECUTIVE_WINDOWS: int = 3
REQUIRED_SUPPORTING_CHANNELS: int = 2


class FireFusionResult:
    """Immutable result of one Fire Fusion evaluation cycle."""

    __slots__ = (
        "s_score", "t_score", "v_score", "h_score",
        "confidence", "status",
        "supporting_count", "supporting_details",
        "button_pressed",
        "reasons",
    )

    def __init__(
        self,
        *,
        s_score: float | None,
        t_score: float | None,
        v_score: float | None,
        h_score: float | None,
        confidence: float | None,
        status: str,
        supporting_count: int,
        supporting_details: list[SupportingChannelDecision],
        button_pressed: bool,
        reasons: list[str],
    ) -> None:
        self.s_score = s_score
        self.t_score = t_score
        self.v_score = v_score
        self.h_score = h_score
        self.confidence = confidence
        self.status = status
        self.supporting_count = supporting_count
        self.supporting_details = supporting_details
        self.button_pressed = button_pressed
        self.reasons = reasons


class FireFusionEngine:
    """Stateless composite engine that computes one window's fusion result.

    Orchestrates TBD-FUSION-01 through TBD-FUSION-06 in a single call.

    Parameters
    ----------
    area_risk_result
        The pre-computed ``AreaRiskResult`` for the monitored area, or
        ``None`` on cold start.  (TBD-FUSION-04)
    window_evidence_history
        Evidence snapshots for up to the last 3 one-second windows, used
        by the T-channel.  (TBD-FUSION-02)
    """

    def __init__(
        self,
        area_risk_result: AreaRiskResult | None = None,
        window_evidence_history: Sequence[WindowEvidence] = (),
    ) -> None:
        self._area_risk = area_risk_result
        self._window_evidence_history = list(window_evidence_history)

    def evaluate(
        self,
        *,
        mq2: LatestSensorState,
        dht22: LatestSensorState,
        mq2_freshness: FreshnessItem,
        dht22_freshness: FreshnessItem,
        detections: list[Detection],
        vision_freshness: FreshnessItem,
        button: LatestSensorState,
        person_in_hazard: bool | None = None,
    ) -> FireFusionResult:
        """Run a full Fire Fusion evaluation for one 1-second window.

        Returns a ``FireFusionResult`` containing S, T, V, H scores,
        the composite confidence C, supporting-channel count, and
        detailed audit reasons.
        """
        reasons: list[str] = []

        # --- S channel (TBD-FUSION-01) ---
        sensor_policy = FireSensorNormalizationPolicy()
        s_score, s_status = sensor_policy.score_with_freshness(
            mq2, dht22, mq2_freshness, dht22_freshness,
        )
        if s_score is None:
            reasons.append(f"TBD-FUSION-01: S unavailable ({s_status}), C cannot be calculated")

        # --- V channel (TBD-FUSION-03) ---
        # Check camera stale first (TBD-FUSION-03)
        if _is_sensor_stale(vision_freshness, VISION_STALE_SECONDS):
            v_score: float | None = None
            reasons.append("TBD-FUSION-03: Camera frame stale (>1.0s), V unavailable")
        else:
            vision_policy = FireVisionNormalizationPolicy()
            v_score = vision_policy.score(detections, person_in_hazard)

        # --- Button (TBD-FUSION-06) ---
        btn_pressed = is_button_pressed(button)

        # --- Build current window evidence for T (TBD-FUSION-02) ---
        current_evidence = WindowEvidence(
            s_score=s_score,
            v_score=v_score,
            button_pressed=btn_pressed,
        )
        # Append current window to history for T computation
        full_history = self._window_evidence_history + [current_evidence]

        # --- T channel (TBD-FUSION-02) ---
        t_policy = FireTemporalNormalizationPolicy(full_history)
        # T = evidence_count / 3 over last 3 windows
        t_score = t_policy.score(None, [], [])  # type: ignore[arg-type]

        # --- H channel (TBD-FUSION-04) ---
        h_context = build_historical_context(self._area_risk)
        h_policy = FireHistoricalNormalizationPolicy(self._area_risk)
        h_score = h_policy.score(h_context)

        # --- Compute individual sensor scores for supporting channels ---
        # TBD-FUSION-01: individual normalized scores for MQ-2 and DHT22
        mq2_stale = _is_sensor_stale(mq2_freshness, MQ2_STALE_SECONDS)
        dht22_stale = _is_sensor_stale(dht22_freshness, DHT22_STALE_SECONDS)

        mq2_score: float | None = None
        dht22_score: float | None = None
        if not mq2_stale and mq2.available and mq2.value is not None:
            mq2_score = _normalize_sensor(float(mq2.value), MQ2_NORMAL, MQ2_ALARM)
        if not dht22_stale and dht22.available and dht22.value is not None:
            dht22_score = _normalize_sensor(float(dht22.value), DHT22_NORMAL, DHT22_ALARM)

        # --- Supporting channels (TBD-FUSION-05 + TBD-FUSION-06) ---
        support_policy = FireSupportingChannelPolicy(
            mq2_score=mq2_score,
            dht22_score=dht22_score,
            camera_score=v_score,
            button_pressed=btn_pressed,
            mq2_available=mq2.available and not mq2_stale,
            dht22_available=dht22.available and not dht22_stale,
            camera_available=v_score is not None,
        )
        supporting_count = support_policy.count_supporting()
        supporting_details = support_policy.evaluate_channels()

        # --- Core formula: C = 100 * (0.30*S + 0.20*T + 0.35*V + 0.15*H) ---
        # TBD-FUSION-01: "If both sensors stale, S is unavailable → C must not be calculated"
        if s_score is None:
            return FireFusionResult(
                s_score=None,
                t_score=t_score,
                v_score=v_score,
                h_score=h_score,
                confidence=None,
                status="not_calculated",
                supporting_count=supporting_count,
                supporting_details=supporting_details,
                button_pressed=btn_pressed,
                reasons=reasons,
            )

        # Use 0.0 for V if unavailable (camera stale), allowing C to be
        # calculated but at a lower value.  S being unavailable is the only
        # hard block per TBD-FUSION-01.
        effective_v = v_score if v_score is not None else 0.0

        confidence = 100.0 * (
            WEIGHT_S * s_score
            + WEIGHT_T * t_score
            + WEIGHT_V * effective_v
            + WEIGHT_H * h_score
        )
        confidence = max(0.0, min(100.0, confidence))

        return FireFusionResult(
            s_score=s_score,
            t_score=t_score,
            v_score=v_score,
            h_score=h_score,
            confidence=confidence,
            status="calculated",
            supporting_count=supporting_count,
            supporting_details=supporting_details,
            button_pressed=btn_pressed,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Alarm decision helper
# ---------------------------------------------------------------------------

class FireAlarmDecision:
    """Stateless evaluator for the three-window automatic alarm rule.

    Alarm requires ALL of:
      1. C >= 40  (confidence threshold)
      2. 3 consecutive 1-second windows pass
      3. At least 2 independent supporting channels

    TBD-FUSION-06 exception: Operator manual confirmation via API
    bypasses the "at least 2 physical sensors" rule.  That bypass is
    NOT implemented here — it belongs in the API route layer.
    """

    def __init__(self, window_results: Sequence[FireFusionResult]) -> None:
        if len(window_results) != REQUIRED_CONSECUTIVE_WINDOWS:
            raise ValueError(
                f"Exactly {REQUIRED_CONSECUTIVE_WINDOWS} consecutive window "
                f"results are required, got {len(window_results)}"
            )
        self.windows = list(window_results)

    @property
    def all_calculated(self) -> bool:
        """True if C was successfully calculated for all 3 windows."""
        return all(w.status == "calculated" for w in self.windows)

    @property
    def all_confidence_pass(self) -> bool:
        """True if C >= 40 for all 3 windows."""
        return all(
            w.confidence is not None and w.confidence >= CONFIDENCE_THRESHOLD
            for w in self.windows
        )

    @property
    def all_supporting_pass(self) -> bool:
        """True if >= 2 supporting channels for all 3 windows."""
        return all(
            w.supporting_count >= REQUIRED_SUPPORTING_CHANNELS
            for w in self.windows
        )

    @property
    def should_alarm(self) -> bool:
        """True if automatic alarm should be triggered.

        Requires C >= 40 AND 3 consecutive windows AND >= 2 supporting channels.
        """
        return self.all_calculated and self.all_confidence_pass and self.all_supporting_pass

    def reasons(self) -> list[str]:
        """Collect human-readable reasons for the alarm/no-alarm decision."""
        reasons: list[str] = []
        for i, w in enumerate(self.windows):
            prefix = f"Window {i + 1}"
            if w.status != "calculated":
                reasons.append(f"{prefix}: C not calculated")
            elif w.confidence is not None and w.confidence < CONFIDENCE_THRESHOLD:
                reasons.append(
                    f"{prefix}: C={w.confidence:.2f} < {CONFIDENCE_THRESHOLD}"
                )
            if w.supporting_count < REQUIRED_SUPPORTING_CHANNELS:
                reasons.append(
                    f"{prefix}: {w.supporting_count} supporting channels "
                    f"< {REQUIRED_SUPPORTING_CHANNELS} required"
                )
            reasons.extend(w.reasons)
        return reasons
