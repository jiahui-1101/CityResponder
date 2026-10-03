"""Shared frame metadata and result envelopes for vision branches."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.sensors.schemas import LatestSensorState


class FrameSourceType(str, Enum):
    CAMERA = "CAMERA"
    VIDEO_FILE = "VIDEO_FILE"
    IMAGE_FILE = "IMAGE_FILE"


class CoordinateSystem(str, Enum):
    RAW_CAMERA = "RAW_CAMERA"
    RAW_BOARD_CROP = "RAW_BOARD_CROP"


class FrameMetadata(BaseModel):
    """Lightweight metadata for one shared frame."""

    frame_id: str
    timestamp: datetime
    source: FrameSourceType
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_CAMERA
    parent_frame_id: str | None = None
    crop_origin_x: int = Field(default=0, ge=0)
    crop_origin_y: int = Field(default=0, ge=0)


class ROI(BaseModel):
    """A named rectangular region in a captured frame."""

    name: str = Field(min_length=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class BoundingBox(BaseModel):
    """Pixel coordinates for a detected object."""

    x1: float
    y1: float
    x2: float
    y2: float


class FrozenModelIdentity(BaseModel):
    """Auditable identity of one configured frozen inference model."""

    name: str
    version: str
    task: str
    weights: str
    classes: list[str]


class Detection(BaseModel):
    """One relevant object detection from a shared in-memory frame."""

    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: BoundingBox
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP


class PolygonPoint(BaseModel):
    """One point in a segmentation polygon in frame coordinates."""

    x: float
    y: float


class SegmentationDetection(BaseModel):
    """One relevant segmentation result."""

    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: BoundingBox
    polygon: list[PolygonPoint] = Field(min_length=1)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP


class BuildingADetectionResult(BaseModel):
    """Detection results for Building A in full-frame coordinates."""

    frame: FrameMetadata
    building_roi: ROI
    detections: list[Detection]
    processing_timestamp: datetime
    inference_duration_ms: float | None = Field(default=None, ge=0)
    inference_per_second: float | None = Field(default=None, ge=0)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP
    board_crop: ROI | None = None
    model: FrozenModelIdentity | None = None


class PersonHazardResult(BaseModel):
    """Person-in-hazard evaluation for one full-frame detection result."""

    frame: FrameMetadata
    hazard_zone: ROI
    person_detections: list[Detection]
    person_in_hazard: bool
    matched_person_indexes: list[int]
    matched_person_bounding_boxes: list[BoundingBox]


class RoadSegmentationResult(BaseModel):
    """Segmentation results for one road ROI in full-frame coordinates."""

    frame: FrameMetadata
    road_roi_name: str
    road_roi: ROI
    segmentations: list[SegmentationDetection]
    processing_timestamp: datetime
    inference_duration_ms: float | None = Field(default=None, ge=0)
    inference_per_second: float | None = Field(default=None, ge=0)


class OccupancyContribution(BaseModel):
    """One segmentation detection contributing pixels inside a road ROI."""

    detection_index: int = Field(ge=0)
    class_name: str
    occupied_pixels: int = Field(ge=0)


class RoadOccupancyResult(BaseModel):
    """Union-mask occupancy metrics for one road ROI."""

    road_roi_name: str
    occupied_pixels: int = Field(ge=0)
    roi_pixels: int = Field(gt=0)
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    contributing_detections: list[OccupancyContribution]
    contributing_classes: list[str]
    road_obstacle_occupied_pixels: int = Field(ge=0)
    pothole_occupied_pixels: int = Field(ge=0)


class ObstacleSpatialEvidence(BaseModel):
    """Raw spatial measurements for one ROAD_OBSTACLE detection."""

    detection_index: int = Field(ge=0)
    class_name: str
    bounding_width_px: float = Field(ge=0)
    bounding_height_px: float = Field(ge=0)
    polygon_span_x_px: float = Field(ge=0)
    polygon_span_y_px: float = Field(ge=0)
    max_extent_px: float = Field(ge=0)
    max_extent_cm: float | None = Field(default=None, ge=0)


class RoadSpatialEvidenceResult(BaseModel):
    """Aggregated obstacle geometry for one road ROI."""

    road_roi_name: str
    obstacle_count: int = Field(ge=0)
    max_obstacle_extent_px: float = Field(ge=0)
    obstacle_extents_px: list[float]
    max_obstacle_extent_cm: float | None = Field(default=None, ge=0)
    obstacle_extents_cm: list[float | None]
    contributing_detections: list[ObstacleSpatialEvidence]


class EvidenceDetectionReference(BaseModel):
    """Reference to a raw segmentation detection in unified evidence."""

    detection_index: int = Field(ge=0)
    class_name: str


class RoadVisionEvidence(BaseModel):
    """Unified raw vision evidence for one road ROI."""

    frame: FrameMetadata
    road_roi_name: str
    road_roi: ROI
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    occupied_pixels: int = Field(ge=0)
    obstacle_count: int = Field(ge=0)
    max_obstacle_extent_px: float = Field(ge=0)
    max_obstacle_extent_cm: float | None = Field(default=None, ge=0)
    contributing_classes: list[str]
    contributing_detections: list[EvidenceDetectionReference]
    raw_segmentations: list[SegmentationDetection]
    processing_timestamp: datetime
    inference_duration_ms: float | None = Field(default=None, ge=0)
    inference_per_second: float | None = Field(default=None, ge=0)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP
    board_crop: ROI | None = None
    model: FrozenModelIdentity | None = None


class VisionDetectionMessage(BaseModel):
    """Validated MQTT payload for Building A detection evidence."""

    frame: FrameMetadata
    building_roi: ROI
    detections: list[Detection]
    person_in_hazard: bool | None = None
    processing_timestamp: datetime
    inference_duration_ms: float | None = Field(default=None, ge=0)
    inference_per_second: float | None = Field(default=None, ge=0)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP
    board_crop: ROI | None = None
    model: FrozenModelIdentity | None = None


class VisionRoadMessage(BaseModel):
    """Validated MQTT payload for compact road evidence."""

    frame: FrameMetadata
    road_roi_name: str
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    occupied_pixels: int = Field(ge=0)
    obstacle_count: int = Field(ge=0)
    max_obstacle_extent_px: float = Field(ge=0)
    max_obstacle_extent_cm: float | None = Field(default=None, ge=0)
    contributing_classes: list[str]
    contributing_detections: list[EvidenceDetectionReference]
    road_roi: ROI | None = None
    raw_segmentations: list[SegmentationDetection] = Field(default_factory=list)
    processing_timestamp: datetime
    inference_duration_ms: float | None = Field(default=None, ge=0)
    inference_per_second: float | None = Field(default=None, ge=0)
    coordinate_system: CoordinateSystem = CoordinateSystem.RAW_BOARD_CROP
    board_crop: ROI | None = None
    model: FrozenModelIdentity | None = None


class UnifiedVisionResult(BaseModel):
    """Coordinate-explicit evidence produced from one shared camera frame."""

    raw_frame: FrameMetadata
    frame: FrameMetadata
    board_crop: ROI
    building_roi: ROI
    road_rois: list[ROI]
    detections: list[Detection]
    segmentations: list[SegmentationDetection]
    detection_model: FrozenModelIdentity
    segmentation_model: FrozenModelIdentity
    processing_timestamp: datetime
    capture_duration_ms: float = Field(ge=0)
    crop_duration_ms: float = Field(ge=0)
    detection_duration_ms: float = Field(ge=0)
    segmentation_duration_ms: float = Field(ge=0)
    postprocessing_duration_ms: float = Field(ge=0)
    total_duration_ms: float = Field(ge=0)


class LatestVisionResponse(BaseModel):
    """Read-only latest vision projection derived from immutable events."""

    available: bool
    detection: VisionDetectionMessage | None = None
    road_evidence: list[VisionRoadMessage] = Field(default_factory=list)


class FreshnessItem(BaseModel):
    """Read-only freshness state for one sensor or vision source."""

    source_type: str
    source_id: str | None = None
    available: bool
    stale: bool | None
    age_seconds: float | None
    timestamp: datetime | None


class PerceptionFreshnessResponse(BaseModel):
    """Freshness summary for supported sensor and vision projections."""

    mq2: FreshnessItem
    dht22: FreshnessItem
    button: FreshnessItem
    ir_a: FreshnessItem
    ir_b: FreshnessItem
    detection: FreshnessItem
    road_evidence: list[FreshnessItem] = Field(default_factory=list)


class RoadIRSyncEvidence(BaseModel):
    """Timestamp and optional conflict evidence for one road/IR pair."""

    road_roi_name: str
    vision_timestamp: datetime | None
    ir_sensor: str | None
    ir_timestamp: datetime | None
    time_delta_ms: float | None
    time_matched: bool | None
    conflict: bool | None
    conflict_reason: str


class PerceptionSnapshot(BaseModel):
    """Read-only combined perception state for downstream Part 3 logic."""

    generated_at: datetime
    sensors: list[LatestSensorState]
    detection: VisionDetectionMessage | None
    person_in_hazard: bool | None
    road_evidence: list[VisionRoadMessage]
    freshness: PerceptionFreshnessResponse
    road_sync: list[RoadIRSyncEvidence]
    warnings: list[str] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class VisionBranchType(str, Enum):
    DETECTION = "DETECTION"
    SEGMENTATION = "SEGMENTATION"


class VisionResultEnvelope(BaseModel):
    """Metadata envelope shared by future detection and segmentation outputs."""

    frame: FrameMetadata
    branch_type: VisionBranchType
    processing_timestamp: datetime
