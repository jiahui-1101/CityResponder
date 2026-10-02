"""Concrete Severity policy implementations (TBD-SEV-01 through 06).

Every threshold, formula, and constant in this file is sourced from
Jiabao's finalized physical thresholds and the team's TBD Resolutions.
Nothing is guessed or fabricated.

Core Formula
------------
R = 100 * (0.30*A + 0.20*S + 0.20*T_heat + 0.20*P + 0.10*Z)

Critical Override: If P = 1, immediately return CRITICAL.

Variable Isolation
------------------
- Severity S  = pure MQ-2 normalized value (NOT the fusion S = max(smoke, heat))
- Severity T_heat = pure DHT22 normalized value (NOT the fusion temporal T)
- These variables are intentionally named differently to prevent collision.

References
----------
TBD-SEV-01  A (Fire Extent Score) — pixel ratio
TBD-SEV-02  S (Smoke Score) — pure MQ-2
TBD-SEV-03  T_heat (Temperature Score) — pure DHT22
TBD-SEV-04  P (Person in Hazard Zone) — YOLO + geometry
TBD-SEV-05  Z (Zone Vulnerability) — prototype dictionary
TBD-SEV-06  Severity Bands — R score to label mapping
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.fusion.schemas import FusionSourceReference
from app.sensors.schemas import LatestSensorState
from app.vision.schemas import BoundingBox, Detection, FreshnessItem, ROI


# ---------------------------------------------------------------------------
# TBD-SEV-02: Smoke Score (S) — Pure MQ-2
# ---------------------------------------------------------------------------
# Normalize using: normal_baseline = 500, alarm_baseline = 2000.
# S_severity = (reading - normal) / (alarm - normal), clamped [0.0, 1.0].
# This is the PURE MQ-2 value.  It is NOT the fusion S = max(smoke, heat).
# ---------------------------------------------------------------------------

SEV_MQ2_NORMAL: float = 500.0   # TBD-SEV-02
SEV_MQ2_ALARM: float = 2000.0   # TBD-SEV-02


def normalize_smoke_score(mq2_reading: float) -> float:
    """Normalize MQ-2 reading into [0.0, 1.0] for severity S.  (TBD-SEV-02)

    This is the *pure* MQ-2 normalized value, distinct from the Fire Fusion
    S channel which uses max(smoke, heat).
    """
    raw = (mq2_reading - SEV_MQ2_NORMAL) / (SEV_MQ2_ALARM - SEV_MQ2_NORMAL)
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# TBD-SEV-03: Temperature Score (T_heat) — Pure DHT22
# ---------------------------------------------------------------------------
# Normalize using: normal_baseline = 30.0 C, alarm_baseline = 50.0 C.
# T_heat = (reading - normal) / (alarm - normal), clamped [0.0, 1.0].
# Variable is named T_heat to prevent collision with Fire Fusion's
# temporal consistency T.
# ---------------------------------------------------------------------------

SEV_DHT22_NORMAL: float = 30.0  # TBD-SEV-03
SEV_DHT22_ALARM: float = 50.0   # TBD-SEV-03


def normalize_t_heat_score(dht22_reading: float) -> float:
    """Normalize DHT22 reading into [0.0, 1.0] for severity T_heat.  (TBD-SEV-03)

    Variable is named T_heat (not T) to prevent collision with Fire Fusion's
    temporal consistency T channel.
    """
    raw = (dht22_reading - SEV_DHT22_NORMAL) / (SEV_DHT22_ALARM - SEV_DHT22_NORMAL)
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# TBD-SEV-01: Fire Extent Score (A) — Pixel Ratio
# ---------------------------------------------------------------------------
# A = fire_bbox_area / hazard_polygon_area, clamped [0.0, 1.0].
# fire_bbox_area = width * height of the fire detection bounding box.
# hazard_polygon_area = width * height of the hazard zone ROI.
# ---------------------------------------------------------------------------

PERSON_MIN_CONFIDENCE: float = 0.50  # TBD-SEV-04
FIRE_CLASS_NAMES: frozenset[str] = frozenset({"fire", "Fire"})


def calculate_fire_extent_score(
    detections: list[Detection],
    hazard_zone: ROI,
) -> float:
    """Calculate A = fire_bbox_area / hazard_polygon_area.  (TBD-SEV-01)

    Uses the largest fire detection bounding box area found.
    Clamped to [0.0, 1.0].
    """
    hazard_area = hazard_zone.width * hazard_zone.height
    if hazard_area <= 0:
        return 0.0

    max_fire_bbox_area: float = 0.0
    for det in detections:
        if det.class_name in FIRE_CLASS_NAMES:
            bbox_width = abs(det.bounding_box.x2 - det.bounding_box.x1)
            bbox_height = abs(det.bounding_box.y2 - det.bounding_box.y1)
            fire_bbox_area = bbox_width * bbox_height
            max_fire_bbox_area = max(max_fire_bbox_area, fire_bbox_area)

    ratio = max_fire_bbox_area / hazard_area
    # TBD-SEV-01: clamp between 0.0 and 1.0
    return max(0.0, min(1.0, ratio))


# ---------------------------------------------------------------------------
# TBD-SEV-04: Person in Hazard Zone (P) — Boolean Logic
# ---------------------------------------------------------------------------
# P = 1 ONLY IF:
#   - YOLO person detection confidence >= 0.50, AND
#   - The center coordinate of the person's bounding box intersects with
#     or falls inside the hazard zone polygon.
# Otherwise P = 0.
# If P = 1, the Critical Override fires immediately.
# ---------------------------------------------------------------------------

PERSON_CLASS_NAMES: frozenset[str] = frozenset({"person", "Person"})


def _bbox_center(box: BoundingBox) -> tuple[float, float]:
    """Return (center_x, center_y) of a bounding box."""
    return ((box.x1 + box.x2) / 2.0, (box.y1 + box.y2) / 2.0)


def _center_inside_roi(center_x: float, center_y: float, roi: ROI) -> bool:
    """Return True if the center point falls inside the ROI rectangle."""
    return (
        roi.x <= center_x <= roi.x + roi.width
        and roi.y <= center_y <= roi.y + roi.height
    )


def evaluate_person_in_hazard(
    detections: list[Detection],
    hazard_zone: ROI,
) -> bool:
    """Return True if any YOLO Person detection (confidence >= 0.50) has its
    bounding-box center inside the hazard zone.  (TBD-SEV-04)
    """
    for det in detections:
        if det.class_name not in PERSON_CLASS_NAMES:
            continue
        # TBD-SEV-04: YOLO person detection confidence >= 0.50
        if det.confidence < PERSON_MIN_CONFIDENCE:
            continue
        center_x, center_y = _bbox_center(det.bounding_box)
        # TBD-SEV-04: center coordinate intersects with or falls inside hazard zone
        if _center_inside_roi(center_x, center_y, hazard_zone):
            return True
    return False


# ---------------------------------------------------------------------------
# TBD-SEV-05: Zone Vulnerability (Z) — Prototype Dictionary
# ---------------------------------------------------------------------------
# Hardcoded prototype mappings:
#   Low-risk:    0.30
#   Normal-risk: 0.60
#   High-risk:   1.00
# ---------------------------------------------------------------------------

ZONE_VULNERABILITY_MAP: dict[str, float] = {
    "low-risk": 0.30,     # TBD-SEV-05
    "normal-risk": 0.60,  # TBD-SEV-05
    "high-risk": 1.00,    # TBD-SEV-05
}

# Normalized lookup aliases for flexibility
_ZONE_ALIASES: dict[str, str] = {
    "low": "low-risk",
    "low_risk": "low-risk",
    "normal": "normal-risk",
    "normal_risk": "normal-risk",
    "medium": "normal-risk",
    "medium_risk": "normal-risk",
    "high": "high-risk",
    "high_risk": "high-risk",
}


def get_zone_vulnerability(zone_label: str) -> float:
    """Return the Z score for a zone label.  (TBD-SEV-05)

    Performs case-insensitive lookup with alias support.
    Raises ValueError if the label is not recognized.
    """
    normalized = zone_label.strip().lower().replace(" ", "_").replace("-", "_")
    canonical = _ZONE_ALIASES.get(normalized, zone_label.strip().lower())
    if canonical in ZONE_VULNERABILITY_MAP:
        return ZONE_VULNERABILITY_MAP[canonical]
    raise ValueError(
        f"Unknown zone vulnerability label '{zone_label}'. "
        f"Valid labels: {list(ZONE_VULNERABILITY_MAP.keys())}"
    )


# ---------------------------------------------------------------------------
# TBD-SEV-06: Severity Bands
# ---------------------------------------------------------------------------
# Map the final R score (when P = 0) to severity labels:
#   0  - 29  -> LOW
#   30 - 49  -> MEDIUM
#   50 - 69  -> HIGH
#   70 - 80  -> CRITICAL
# When P = 1, immediately return CRITICAL (override, R is not checked).
# ---------------------------------------------------------------------------

SEVERITY_BANDS: list[tuple[float, float, str]] = [
    (0.0, 29.0, "LOW"),       # TBD-SEV-06
    (30.0, 49.0, "MEDIUM"),   # TBD-SEV-06
    (50.0, 69.0, "HIGH"),     # TBD-SEV-06
    (70.0, 80.0, "CRITICAL"), # TBD-SEV-06
]


def classify_severity_band(r_score: float) -> str:
    """Map an R score to a severity label string.  (TBD-SEV-06)

    Scores above 80 are also classified as CRITICAL.
    """
    for low, high, label in SEVERITY_BANDS:
        if low <= r_score <= high:
            return label
    # Scores above 80 → CRITICAL (upper boundary extension)
    if r_score > 80.0:
        return "CRITICAL"
    # Should not happen with valid scores, but defensive fallback
    return "LOW"


# ---------------------------------------------------------------------------
# Core Formula: R = 100 * (0.30*A + 0.20*S + 0.20*T_heat + 0.20*P + 0.10*Z)
# ---------------------------------------------------------------------------

SEVERITY_WEIGHT_A: float = 0.30      # Fire Extent Score
SEVERITY_WEIGHT_S: float = 0.20      # Smoke Score (pure MQ-2)
SEVERITY_WEIGHT_T_HEAT: float = 0.20 # Temperature Score (pure DHT22)
SEVERITY_WEIGHT_P: float = 0.20      # Person in Hazard Zone
SEVERITY_WEIGHT_Z: float = 0.10      # Zone Vulnerability


class SeverityPolicyResult(BaseModel):
    """Immutable result of one severity evaluation cycle."""

    status: Literal["calculated", "critical_override", "not_calculated"]
    severity_score: float | None = Field(default=None, ge=0.0, le=100.0)
    severity_label: str | None = None
    a_score: float | None = Field(default=None, ge=0.0, le=1.0)
    s_score: float | None = Field(default=None, ge=0.0, le=1.0)
    t_heat_score: float | None = Field(default=None, ge=0.0, le=1.0)
    p_score: float | None = Field(default=None, ge=0.0, le=1.0)
    z_score: float | None = Field(default=None, ge=0.0, le=1.0)
    weights: dict[str, float] = Field(default_factory=dict)
    critical_override: bool = False
    person_in_hazard: bool = False
    reasons: list[str] = Field(default_factory=list)
    calculated_at: datetime


class SeverityPolicyClassification(BaseModel):
    """Policy for SeverityClassificationPolicy protocol compliance."""

    version: str = "1.0.0-jiabao-thresholds"

    def classify(self, severity_score: float) -> str | None:
        """Map R score to severity band label.  (TBD-SEV-06)"""
        return classify_severity_band(severity_score)


class SeverityComponentPolicyProvider:
    """Concrete SeverityComponentProvider implementation.

    Provides A, S (pure MQ-2), T_heat (pure DHT22), and Z severity
    component values from raw sensor readings and vision detections.

    This provider is intentionally isolated from the Fire Fusion module's
    S (max of smoke, heat) and T (temporal consistency) channels.

    Implements the ``SeverityComponentProvider`` protocol from
    ``app.severity.service``.
    """

    def __init__(
        self,
        zone_label: str = "normal-risk",
        hazard_zone: ROI | None = None,
    ) -> None:
        self._zone_label = zone_label
        self._hazard_zone = hazard_zone

    def provide(self, snapshot: object) -> object:
        """Protocol-compatible provider (used by the orchestration layer)."""
        # Import here to avoid circular dependency at module level
        from app.severity.schemas import SeverityComponentValues
        from app.vision.schemas import PerceptionSnapshot

        if not isinstance(snapshot, PerceptionSnapshot):
            return SeverityComponentValues(
                reasons=["snapshot is not a PerceptionSnapshot"],
            )

        reasons: list[str] = []

        # --- S: pure MQ-2 (TBD-SEV-02) ---
        mq2_state = next(
            (s for s in snapshot.sensors if s.sensor_type == "MQ2"), None
        )
        if mq2_state is not None and mq2_state.available and mq2_state.value is not None:
            s_score = normalize_smoke_score(float(mq2_state.value))
        else:
            s_score = None
            reasons.append("TBD-SEV-02: MQ-2 sensor unavailable for severity S")

        # --- T_heat: pure DHT22 (TBD-SEV-03) ---
        dht22_state = next(
            (s for s in snapshot.sensors if s.sensor_type == "DHT22"), None
        )
        if dht22_state is not None and dht22_state.available and dht22_state.value is not None:
            t_heat_score = normalize_t_heat_score(float(dht22_state.value))
        else:
            t_heat_score = None
            reasons.append("TBD-SEV-03: DHT22 sensor unavailable for severity T_heat")

        # --- A: fire extent (TBD-SEV-01) ---
        if snapshot.detection is not None and self._hazard_zone is not None:
            a_score = calculate_fire_extent_score(
                snapshot.detection.detections,
                self._hazard_zone,
            )
        else:
            a_score = None
            if snapshot.detection is None:
                reasons.append("TBD-SEV-01: no vision detection for severity A")
            if self._hazard_zone is None:
                reasons.append("TBD-SEV-01: hazard zone ROI not configured for severity A")

        # --- Z: zone vulnerability (TBD-SEV-05) ---
        try:
            z_score = get_zone_vulnerability(self._zone_label)
        except ValueError as exc:
            z_score = None
            reasons.append(f"TBD-SEV-05: {exc}")

        return SeverityComponentValues(
            a=a_score,
            s=s_score,
            t=t_heat_score,  # Maps to schema 't' field; semantically T_heat
            z=z_score,
            reasons=reasons,
        )


def calculate_severity(
    *,
    mq2_reading: float | None = None,
    dht22_reading: float | None = None,
    detections: list[Detection] | None = None,
    hazard_zone: ROI | None = None,
    zone_label: str = "normal-risk",
) -> SeverityPolicyResult:
    """Full severity evaluation entrypoint.

    Implements the complete severity pipeline:
    1. Compute P (person in hazard zone) — TBD-SEV-04
    2. Critical Override: if P = 1, immediately return CRITICAL — TBD-SEV-04
    3. Compute A (fire extent) — TBD-SEV-01
    4. Compute S (pure MQ-2 smoke) — TBD-SEV-02
    5. Compute T_heat (pure DHT22 temperature) — TBD-SEV-03
    6. Compute Z (zone vulnerability) — TBD-SEV-05
    7. Apply formula: R = 100 * (0.30*A + 0.20*S + 0.20*T_heat + 0.20*P + 0.10*Z)
    8. Map R to severity band — TBD-SEV-06

    Variable Isolation
    ------------------
    - S here is the pure MQ-2 value, NOT the fusion S = max(smoke, heat).
    - T_heat here is the pure DHT22 value, NOT the fusion temporal T.
    """
    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    detections = detections or []
    weights = {
        "A": SEVERITY_WEIGHT_A,
        "S": SEVERITY_WEIGHT_S,
        "T_heat": SEVERITY_WEIGHT_T_HEAT,
        "P": SEVERITY_WEIGHT_P,
        "Z": SEVERITY_WEIGHT_Z,
    }

    # --- Step 1: P (Person in Hazard Zone) — TBD-SEV-04 ---
    if hazard_zone is not None:
        person_detected = evaluate_person_in_hazard(detections, hazard_zone)
    else:
        person_detected = False
        reasons.append("TBD-SEV-04: hazard zone ROI not configured, P defaults to 0")

    p_score: float = 1.0 if person_detected else 0.0

    # --- Step 2: Critical Override — TBD-SEV-04 ---
    # "If P = 1, immediately terminate the calculation and return CRITICAL"
    if p_score == 1.0:
        return SeverityPolicyResult(
            status="critical_override",
            severity_score=None,  # R is not calculated for critical override
            severity_label="CRITICAL",
            a_score=None,
            s_score=None,
            t_heat_score=None,
            p_score=1.0,
            z_score=None,
            weights=weights,
            critical_override=True,
            person_in_hazard=True,
            reasons=["TBD-SEV-04: P=1, person in hazard zone -> CRITICAL override"],
            calculated_at=now,
        )

    # --- Step 3: A (Fire Extent) — TBD-SEV-01 ---
    if hazard_zone is not None:
        a_score = calculate_fire_extent_score(detections, hazard_zone)
    else:
        a_score = 0.0
        reasons.append("TBD-SEV-01: hazard zone ROI not configured, A defaults to 0")

    # --- Step 4: S (Smoke / pure MQ-2) — TBD-SEV-02 ---
    if mq2_reading is not None:
        s_score = normalize_smoke_score(mq2_reading)
    else:
        s_score = 0.0
        reasons.append("TBD-SEV-02: MQ-2 reading unavailable, S defaults to 0")

    # --- Step 5: T_heat (Temperature / pure DHT22) — TBD-SEV-03 ---
    if dht22_reading is not None:
        t_heat_score = normalize_t_heat_score(dht22_reading)
    else:
        t_heat_score = 0.0
        reasons.append("TBD-SEV-03: DHT22 reading unavailable, T_heat defaults to 0")

    # --- Step 6: Z (Zone Vulnerability) — TBD-SEV-05 ---
    try:
        z_score = get_zone_vulnerability(zone_label)
    except ValueError:
        z_score = ZONE_VULNERABILITY_MAP["normal-risk"]  # fallback to 0.60
        reasons.append(
            f"TBD-SEV-05: Unknown zone label '{zone_label}', defaulting to normal-risk (0.60)"
        )

    # --- Step 7: Core Formula — TBD-SEV-06 ---
    # R = 100 * (0.30*A + 0.20*S + 0.20*T_heat + 0.20*P + 0.10*Z)
    r_score = 100.0 * (
        SEVERITY_WEIGHT_A * a_score
        + SEVERITY_WEIGHT_S * s_score
        + SEVERITY_WEIGHT_T_HEAT * t_heat_score
        + SEVERITY_WEIGHT_P * p_score      # P = 0 here (override already handled)
        + SEVERITY_WEIGHT_Z * z_score
    )
    r_score = max(0.0, min(100.0, r_score))

    # --- Step 8: Severity Band — TBD-SEV-06 ---
    severity_label = classify_severity_band(r_score)

    return SeverityPolicyResult(
        status="calculated",
        severity_score=r_score,
        severity_label=severity_label,
        a_score=a_score,
        s_score=s_score,
        t_heat_score=t_heat_score,
        p_score=p_score,
        z_score=z_score,
        weights=weights,
        critical_override=False,
        person_in_hazard=False,
        reasons=reasons,
        calculated_at=now,
    )
