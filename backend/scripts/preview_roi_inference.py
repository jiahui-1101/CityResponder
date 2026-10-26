"""Run local-only YOLO inference through an inactive ROI calibration draft.

This script intentionally does not construct the integrated vision pipeline,
publish events, or call MQTT/actuator services. Its default input is the saved
RAW_CAMERA reference image; --live opens a one-frame DirectShow preview capture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_DRAFT = PROJECT_ROOT / "reports" / "debug" / "camera_alignment" / "roi_calibration_draft.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--image", type=Path, help="Reference image; defaults to image stored in the draft")
    parser.add_argument("--live", action="store_true", help="Capture one frame directly from a camera")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--backend", choices=("dshow", "any"), default="dshow")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    return parser.parse_args()


def _role_region(draft: dict[str, Any], role: str) -> dict[str, Any]:
    regions = [region for region in draft.get("regions", []) if region.get("role") == role]
    if len(regions) != 1:
        raise ValueError(f"Expected one {role} polygon, found {len(regions)}")
    return regions[0]


def _masked_crop(frame: np.ndarray, polygon: list[list[int]]) -> tuple[np.ndarray, tuple[int, int]]:
    points = np.asarray(polygon, dtype=np.int32)
    x1 = max(0, int(np.floor(points[:, 0].min())))
    y1 = max(0, int(np.floor(points[:, 1].min())))
    x2 = min(frame.shape[1], int(np.ceil(points[:, 0].max())) + 1)
    y2 = min(frame.shape[0], int(np.ceil(points[:, 1].max())) + 1)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("ROI polygon has an empty bounding box")
    crop = frame[y1:y2, x1:x2]
    local_points = points - np.array([x1, y1], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [local_points], 255)
    masked = np.zeros_like(crop)
    cv2.copyTo(crop, mask, masked)
    return masked, (x1, y1)


def _inside(point: tuple[float, float], polygon: list[list[int]]) -> bool:
    # Imported from the editor so both tools use the same RAW_CAMERA geometry rules.
    from scripts.roi_calibration import point_in_polygon

    return point_in_polygon(point, polygon)


def _load_camera_frame(args: argparse.Namespace) -> tuple[np.ndarray, dict[str, Any]]:
    api = cv2.CAP_DSHOW if args.backend == "dshow" else cv2.CAP_ANY
    cap = cv2.VideoCapture(args.camera_index, api)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Unable to open camera index {args.camera_index} using {args.backend}")
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Camera returned no frame")
        fourcc_value = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join(chr((fourcc_value >> (8 * i)) & 0xFF) for i in range(4)).rstrip("\x00")
        info = {
            "camera_index": args.camera_index,
            "capture_backend": cap.getBackendName(),
            "fourcc": fourcc,
            "requested_resolution": [args.width, args.height],
            "actual_resolution": [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))],
            "reported_fps": cap.get(cv2.CAP_PROP_FPS),
            "read_success": True,
        }
        return frame, info
    finally:
        cap.release()


def main() -> int:
    args = parse_args()
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    try:
        from app.vision.config import get_vision_config
        from app.vision.detector import YOLODetector
        from app.vision.segmentation import YOLOSegmentation
        from scripts.roi_calibration import load_draft

        draft = load_draft(args.draft.resolve())
        if args.live:
            frame, source = _load_camera_frame(args)
        else:
            image_path = args.image.resolve() if args.image else Path(draft["reference_image"])
            frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if frame is None:
                raise FileNotFoundError(f"Unable to load reference image: {image_path}")
            source = {"image": str(image_path), "source": "saved RAW_CAMERA reference"}
        expected = draft["image_size"]
        if frame.shape[1] != expected["width"] or frame.shape[0] != expected["height"]:
            raise ValueError(
                f"Frame is {frame.shape[1]}x{frame.shape[0]}, draft expects "
                f"{expected['width']}x{expected['height']} RAW_CAMERA coordinates"
            )

        building = _role_region(draft, "building_detection_roi")
        hazard = _role_region(draft, "hazard_polygon")
        road = _role_region(draft, "road_segmentation_roi")
        building_input, building_origin = _masked_crop(frame, building["points"])
        road_input, road_origin = _masked_crop(frame, road["points"])

        config = get_vision_config()
        detector = YOLODetector(config=config)
        segmenter = YOLOSegmentation(config=config)

        building_detections = []
        for detection in detector.detect(building_input):
            box = detection.bounding_box
            center = ((box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2)
            raw_center = (center[0] + building_origin[0], center[1] + building_origin[1])
            if not _inside(raw_center, building["points"]):
                continue
            raw_box = [
                round(box.x1 + building_origin[0], 1),
                round(box.y1 + building_origin[1], 1),
                round(box.x2 + building_origin[0], 1),
                round(box.y2 + building_origin[1], 1),
            ]
            building_detections.append(
                {
                    "class": detection.class_name,
                    "confidence": round(detection.confidence, 4),
                    "box_raw_camera": raw_box,
                    "center_in_hazard_polygon": _inside(raw_center, hazard["points"]),
                }
            )

        road_detections = []
        for detection in segmenter.segment(road_input):
            box = detection.bounding_box
            raw_center = (
                (box.x1 + box.x2) / 2 + road_origin[0],
                (box.y1 + box.y2) / 2 + road_origin[1],
            )
            if not _inside(raw_center, road["points"]):
                continue
            road_detections.append(
                {
                    "class": detection.class_name,
                    "confidence": round(detection.confidence, 4),
                    "box_raw_camera": [
                        round(box.x1 + road_origin[0], 1),
                        round(box.y1 + road_origin[1], 1),
                        round(box.x2 + road_origin[0], 1),
                        round(box.y2 + road_origin[1], 1),
                    ],
                }
            )

        print(
            json.dumps(
                {
                    "mode": "LOCAL_INFERENCE_ONLY_NO_EVENTS_NO_MQTT_NO_ACTUATORS",
                    "draft_status": draft["status"],
                    "source": source,
                    "capture_resolution": [frame.shape[1], frame.shape[0]],
                    "models": {
                        "detection": config.detection_model,
                        "segmentation": config.segmentation_model,
                    },
                    "building_roi_candidate": building["region_id"],
                    "hazard_polygon_candidate": hazard["region_id"],
                    "road_roi_candidate": road["region_id"],
                    "building_detections": building_detections,
                    "road_segmentations": road_detections,
                    "limitations": [
                        "Results are exploratory and do not activate or change production ROIs.",
                        "The reference image has lower structures clipped by the camera framing.",
                        "Road graph-edge and IR sensor mappings remain unconfirmed.",
                    ],
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"ROI preview inference failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
