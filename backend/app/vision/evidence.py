"""Unified, model-independent road vision evidence composition."""

from datetime import datetime, timezone

from app.vision.schemas import (
    EvidenceDetectionReference,
    RoadOccupancyResult,
    RoadSegmentationResult,
    RoadSpatialEvidenceResult,
    RoadVisionEvidence,
)


class RoadVisionEvidenceError(ValueError):
    """Raised when evidence inputs cannot be safely combined."""


class RoadVisionEvidenceService:
    """Combine existing road vision outputs without rerunning inference."""

    def combine(
        self,
        segmentation_results: list[RoadSegmentationResult],
        occupancy_results: list[RoadOccupancyResult],
        spatial_results: list[RoadSpatialEvidenceResult],
    ) -> list[RoadVisionEvidence]:
        """Build one unified evidence object for each road ROI."""

        occupancy_by_name = self._index_by_name(occupancy_results)
        spatial_by_name = self._index_by_name(spatial_results)
        evidence: list[RoadVisionEvidence] = []
        for segmentation in segmentation_results:
            name = segmentation.road_roi_name
            occupancy = occupancy_by_name.get(name)
            spatial = spatial_by_name.get(name)
            if occupancy is None or spatial is None:
                raise RoadVisionEvidenceError(
                    f"Missing occupancy or spatial evidence for road ROI '{name}'"
                )
            references = [
                EvidenceDetectionReference(
                    detection_index=index,
                    class_name=detection.class_name,
                )
                for index, detection in enumerate(segmentation.segmentations)
            ]
            contributing_classes = sorted(
                {reference.class_name for reference in references}
            )
            evidence.append(
                RoadVisionEvidence(
                    frame=segmentation.frame,
                    road_roi_name=name,
                    road_roi=segmentation.road_roi,
                    occupancy_ratio=occupancy.occupancy_ratio,
                    occupied_pixels=occupancy.occupied_pixels,
                    obstacle_count=spatial.obstacle_count,
                    max_obstacle_extent_px=spatial.max_obstacle_extent_px,
                    max_obstacle_extent_cm=spatial.max_obstacle_extent_cm,
                    contributing_classes=contributing_classes,
                    contributing_detections=references,
                    raw_segmentations=segmentation.segmentations,
                    processing_timestamp=datetime.now(timezone.utc),
                    inference_duration_ms=segmentation.inference_duration_ms,
                    inference_per_second=segmentation.inference_per_second,
                )
            )
        return evidence

    @staticmethod
    def _index_by_name(results: list[object]) -> dict[str, object]:
        indexed: dict[str, object] = {}
        for result in results:
            name = result.road_roi_name
            if name in indexed:
                raise RoadVisionEvidenceError(
                    f"Duplicate evidence for road ROI '{name}'"
                )
            indexed[name] = result
        return indexed
