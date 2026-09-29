"""Configurable ROI validation and in-memory frame extraction helpers."""

import json
from typing import Any

from pydantic import ValidationError

from app.vision.config import VisionConfig, get_vision_config
from app.vision.schemas import ROI


class ROIValidationError(ValueError):
    """Raised when an ROI is missing, malformed, too small, or out of bounds."""


def validate_roi(
    roi: ROI,
    *,
    frame_width: int,
    frame_height: int,
    config: VisionConfig | None = None,
) -> ROI:
    """Validate an ROI against frame bounds and configured minimums."""

    if roi.x + roi.width > frame_width or roi.y + roi.height > frame_height:
        raise ROIValidationError(
            f"ROI '{roi.name}' ({roi.x},{roi.y},{roi.width},{roi.height}) "
            f"is outside frame bounds {frame_width}x{frame_height}"
        )

    vision_config = config or get_vision_config()
    normalized_name = roi.name.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_name in {"building_a", "buildinga"} and (
        roi.width < vision_config.building_roi_min_width_px
        or roi.height < vision_config.building_roi_min_height_px
    ):
        raise ROIValidationError(
            f"Building A ROI must be at least "
            f"{vision_config.building_roi_min_width_px}x"
            f"{vision_config.building_roi_min_height_px}px"
        )
    if normalized_name.startswith("road") and roi.width < vision_config.min_road_width_px:
        raise ROIValidationError(
            f"Road ROI must be at least {vision_config.min_road_width_px}px wide"
        )
    return roi


def crop_frame(
    frame: Any,
    roi: ROI,
    *,
    config: VisionConfig | None = None,
) -> Any:
    """Return a validated in-memory frame slice without clamping coordinates."""

    if not hasattr(frame, "shape") or len(frame.shape) < 2:
        raise ROIValidationError("Frame must expose height and width through shape")
    frame_height, frame_width = frame.shape[:2]
    validate_roi(
        roi,
        frame_width=frame_width,
        frame_height=frame_height,
        config=config,
    )
    return frame[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width]


def get_configured_rois(config: VisionConfig | None = None) -> dict[str, list[ROI]]:
    """Load configured building, road, and hazard ROIs; unset values remain empty."""

    vision_config = config or get_vision_config()
    return {
        "building_a": _parse_roi_value(
            vision_config.building_roi_coordinates,
            default_name="building_a",
        ),
        "road": _parse_roi_value(vision_config.road_roi_coordinates),
        "hazard_zone": _parse_roi_value(vision_config.hazard_roi_coordinates),
    }


def _parse_roi_value(raw_value: str | None, default_name: str | None = None) -> list[ROI]:
    if raw_value is None or not raw_value.strip():
        return []
    try:
        parsed = json.loads(raw_value)
        items = parsed if isinstance(parsed, list) else [parsed]
        rois = []
        for item in items:
            if default_name and isinstance(item, dict) and "name" not in item:
                item = {**item, "name": default_name}
            rois.append(ROI.model_validate(item))
        return rois
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ROIValidationError("ROI configuration must be valid JSON ROI object(s)") from exc
