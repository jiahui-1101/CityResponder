"""Vision (V) channel evaluation boundary."""

from typing import Protocol

from app.vision.schemas import Detection

from app.fusion.schemas import FusionInput, VisionChannelEvaluation


class VisionNormalizationPolicy(Protocol):
    """Future source-backed policy for converting raw V evidence into 0..1."""

    def score(
        self,
        detections: list[Detection],
        person_in_hazard: bool | None,
    ) -> float:
        """Return an explicitly defined score in the inclusive 0..1 range."""


def evaluate_vision_channel(
    fusion_input: FusionInput,
    policy: VisionNormalizationPolicy | None = None,
) -> VisionChannelEvaluation:
    """Evaluate V availability/freshness without inventing score semantics."""

    vision = fusion_input.v
    detection = vision.detection
    reasons: list[str] = []
    if detection is None:
        reasons.append("vision detection evidence is unavailable")
        return _evaluation(
            status="unavailable",
            score=None,
            fusion_input=fusion_input,
            reasons=reasons,
        )
    if vision.freshness.stale is True:
        reasons.append("vision detection evidence is stale")
        return _evaluation(
            status="stale",
            score=None,
            fusion_input=fusion_input,
            reasons=reasons,
        )
    if not vision.freshness.available:
        reasons.append("vision freshness is unavailable")
        return _evaluation(
            status="incomplete",
            score=None,
            fusion_input=fusion_input,
            reasons=reasons,
        )

    if policy is None:
        reasons.append("V score not evaluated: normalization policy is not configured")
        status = "not_evaluated"
        score = None
    else:
        try:
            score = float(policy.score(detection.detections, vision.person_in_hazard))
            if not 0.0 <= score <= 1.0:
                raise ValueError("policy score must be between 0 and 1")
            status = "available"
        except Exception as exc:
            score = None
            status = "not_evaluated"
            reasons.append(f"V score policy failed: {exc}")
    return _evaluation(
        status=status,
        score=score,
        fusion_input=fusion_input,
        reasons=reasons,
    )


def _evaluation(
    *,
    status: str,
    score: float | None,
    fusion_input: FusionInput,
    reasons: list[str],
) -> VisionChannelEvaluation:
    vision = fusion_input.v
    detections = vision.detection.detections if vision.detection is not None else []
    return VisionChannelEvaluation(
        status=status,
        score=score,
        detections=detections,
        person_in_hazard=vision.person_in_hazard,
        freshness=vision.freshness,
        reasons=reasons,
        source_references=vision.source_references,
    )
