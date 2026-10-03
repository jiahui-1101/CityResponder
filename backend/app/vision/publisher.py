"""MQTT publishing for compact structured vision evidence."""

from typing import Any

from app.mqtt.client import mqtt_client
from app.vision.schemas import (
    BuildingADetectionResult,
    PersonHazardResult,
    RoadVisionEvidence,
)


DETECTION_TOPIC = "city/vision/detection"
ROAD_TOPIC = "city/vision/road"


class VisionEvidencePublisher:
    """Publish completed vision results without coupling to inference."""

    def publish_detection(
        self,
        detection_result: BuildingADetectionResult,
        person_hazard: PersonHazardResult | None = None,
    ) -> None:
        """Publish Building A detections and optional hazard status."""

        payload: dict[str, Any] = {
            "frame": detection_result.frame.model_dump(mode="json"),
            "building_roi": detection_result.building_roi.model_dump(mode="json"),
            "detections": [
                detection.model_dump(mode="json")
                for detection in detection_result.detections
            ],
            "processing_timestamp": detection_result.processing_timestamp.isoformat(),
            "inference_duration_ms": detection_result.inference_duration_ms,
            "inference_per_second": detection_result.inference_per_second,
            "coordinate_system": detection_result.coordinate_system.value,
            "board_crop": (
                detection_result.board_crop.model_dump(mode="json")
                if detection_result.board_crop is not None
                else None
            ),
            "model": (
                detection_result.model.model_dump(mode="json")
                if detection_result.model is not None
                else None
            ),
        }
        if person_hazard is not None:
            payload["person_in_hazard"] = person_hazard.person_in_hazard
        mqtt_client.publish(DETECTION_TOPIC, payload, qos=1)

    def publish_road(self, evidence: RoadVisionEvidence) -> None:
        """Publish compact road evidence without raw polygons or frames."""

        payload = {
            "frame": evidence.frame.model_dump(mode="json"),
            "road_roi_name": evidence.road_roi_name,
            "occupancy_ratio": evidence.occupancy_ratio,
            "occupied_pixels": evidence.occupied_pixels,
            "obstacle_count": evidence.obstacle_count,
            "max_obstacle_extent_px": evidence.max_obstacle_extent_px,
            "max_obstacle_extent_cm": evidence.max_obstacle_extent_cm,
            "contributing_classes": evidence.contributing_classes,
            "contributing_detections": [
                detection.model_dump(mode="json")
                for detection in evidence.contributing_detections
            ],
            "road_roi": evidence.road_roi.model_dump(mode="json"),
            "raw_segmentations": [
                segmentation.model_dump(mode="json")
                for segmentation in evidence.raw_segmentations
            ],
            "processing_timestamp": evidence.processing_timestamp.isoformat(),
            "inference_duration_ms": evidence.inference_duration_ms,
            "inference_per_second": evidence.inference_per_second,
            "coordinate_system": evidence.coordinate_system.value,
            "board_crop": (
                evidence.board_crop.model_dump(mode="json")
                if evidence.board_crop is not None
                else None
            ),
            "model": (
                evidence.model.model_dump(mode="json")
                if evidence.model is not None
                else None
            ),
        }
        mqtt_client.publish(ROAD_TOPIC, payload, qos=1)


vision_evidence_publisher = VisionEvidencePublisher()


def publish_detection_evidence(
    detection_result: BuildingADetectionResult,
    person_hazard: PersonHazardResult | None = None,
) -> None:
    """Publish Building A detection evidence to the vision detection topic."""

    vision_evidence_publisher.publish_detection(detection_result, person_hazard)


def publish_road_evidence(evidence: RoadVisionEvidence) -> None:
    """Publish one unified road evidence object to the road topic."""

    vision_evidence_publisher.publish_road(evidence)
