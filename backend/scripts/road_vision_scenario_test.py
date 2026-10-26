"""Operator-driven, single-frame local YOLO road-prop validation GUI.

TEST_ONLY: no routing, MQTT, persistence service, dispatch, or actuators.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import queue
import threading
import time
import textwrap
from time import perf_counter
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)
SCENARIOS: dict[str, dict[str, Any]] = {
    "0": {"id": "T0", "name": "Clear road baseline", "expected_class": "NONE", "expected_region": "operator_select_clear_road", "candidate_edge": None},
    "1": {"id": "T1", "name": "Roadblock on Route A / PE04", "expected_class": "ROAD_OBSTACLE", "expected_region": "road_upper_horizontal_candidate", "candidate_edge": "PE04"},
    "2": {"id": "T2", "name": "Roadblock on Route B / PE02", "expected_class": "ROAD_OBSTACLE", "expected_region": "road_main_vertical_candidate", "candidate_edge": "PE02"},
    "3": {"id": "T3", "name": "Pothole on Route A / PE04", "expected_class": "POTHOLE", "expected_region": "road_upper_horizontal_candidate", "candidate_edge": "PE04"},
    "4": {"id": "T4", "name": "Pothole on Route B / PE02", "expected_class": "POTHOLE", "expected_region": "road_main_vertical_candidate", "candidate_edge": "PE02"},
    "5": {"id": "T5", "name": "Prop outside valid road polygons", "expected_class": "OPERATOR_RECORDED", "expected_region": "OUTSIDE_VALID_ROAD_POLYGONS", "candidate_edge": None},
    "6": {"id": "T6", "name": "Prop near a road junction", "expected_class": "OPERATOR_RECORDED", "expected_region": "JUNCTION", "candidate_edge": None},
    "7": {
        "id": "T7",
        "name": "Support exclusion (offline validation only)",
        "expected_class": "OPERATOR_RECORDED",
        "expected_region": "SUPPORT_EXCLUSION",
        "candidate_edge": None,
        "physical_validation_status": "NOT_EXECUTED_PHYSICAL — FIXTURE_CONSTRAINT",
        "physical_validation_note": (
            "Support structures are upright; do not stage a physical roadblock inside them. "
            "Use deterministic offline mask validation."
        ),
    },
}
PROP_KEYS = {ord("r"): "ROADBLOCK", ord("p"): "POTHOLE", ord("n"): "NONE", ord("u"): "UNKNOWN"}
VISIBILITY_KEYS = {ord("y"): True, ord("h"): False}
LOCATION_KEYS = {
    ord("a"): "PE04", ord("s"): "PE02", ord("d"): "OUTSIDE_VALID_ROAD_POLYGONS",
    ord("f"): "JUNCTION_J1", ord("j"): "JUNCTION_J2", ord("k"): "SUPPORT_EXCLUSION",
    ord("l"): "PE06", ord("i"): "PE07", ord("e"): "OTHER_OR_UNKNOWN",
}
LOCATION_REGION = {
    "PE04": "road_upper_horizontal_candidate", "PE06": "road_upper_horizontal_candidate",
    "PE02": "road_main_vertical_candidate", "PE07": "road_main_vertical_candidate",
    "JUNCTION_J1": "road_main_vertical_candidate", "JUNCTION_J2": "road_main_vertical_candidate",
}
TARGET_CLASSES = ("ROAD_OBSTACLE", "POTHOLE")

CONTROL_PANEL_SIZE = (1120, 760)
CONTROL_BUTTONS: list[dict[str, Any]] = []
_scenario_names = [
    "T0 Clear Road", "T1 Roadblock Route A", "T2 Roadblock Route B",
    "T3 Pothole Route A", "T4 Pothole Route B", "T5 Outside ROI",
    "T6 Junction", "T7 Support Exclusion (offline only)",
]
for _index, _label in enumerate(_scenario_names):
    CONTROL_BUTTONS.append({
        "kind": "scenario", "value": str(_index), "label": _label,
        "rect": (18 + (_index % 4) * 276, 171 + (_index // 4) * 45, 264, 38),
    })
for _index, (_label, _value) in enumerate((
    ("NONE", "NONE"), ("ROADBLOCK", "ROADBLOCK"),
    ("POTHOLE", "POTHOLE"), ("UNKNOWN", "UNKNOWN"),
)):
    CONTROL_BUTTONS.append({
        "kind": "truth", "value": _value, "label": _label,
        "rect": (18 + _index * 276, 287, 264, 38),
    })
for _index, (_label, _value) in enumerate((
    ("PE04", "PE04"), ("PE02", "PE02"), ("Outside", "OUTSIDE_VALID_ROAD_POLYGONS"),
    ("J1", "JUNCTION_J1"), ("J2", "JUNCTION_J2"), ("Support", "SUPPORT_EXCLUSION"),
    ("PE06", "PE06"), ("PE07", "PE07"), ("Other / Unknown", "OTHER_OR_UNKNOWN"),
)):
    CONTROL_BUTTONS.append({
        "kind": "location", "value": _value, "label": _label,
        "rect": (18 + (_index % 5) * 222, 365 + (_index // 5) * 44, 204, 37),
    })
CONTROL_BUTTONS.extend((
    {"kind": "visibility", "value": True, "label": "Clearly Visible", "rect": (18, 484, 535, 40)},
    {"kind": "visibility", "value": False, "label": "Not Clear", "rect": (567, 484, 535, 40)},
    {"kind": "capture", "value": None, "label": "CAPTURE & RUN YOLO", "rect": (18, 690, 780, 60)},
    {"kind": "exit", "value": None, "label": "EXIT", "rect": (816, 690, 286, 60)},
))


def normalize_key_code(key: int) -> int:
    """Normalize ASCII letter key codes so upper- and lower-case shortcuts match."""
    if 0 <= key <= 0x7F:
        return ord(chr(key).lower())
    return key


def hit_test_control_button(x: int, y: int) -> dict[str, Any] | None:
    """Return the control button under a panel coordinate, if any."""
    for button in CONTROL_BUTTONS:
        left, top, width, height = button["rect"]
        if left <= x < left + width and top <= y < top + height:
            return button
    return None


def apply_operator_selection(state: dict[str, Any], kind: str, value: Any) -> str:
    """Apply one scenario/truth/location/visibility input and return visible feedback."""
    if kind == "scenario":
        state.update(
            scenario_key=str(value), scenario_selected=True,
            actual_prop_type="NOT_RECORDED", actual_location="NOT_RECORDED", visible=None,
        )
        status = f"Selected {SCENARIOS[str(value)]['id']}; record ground truth and visibility"
    elif kind == "truth":
        state["actual_prop_type"] = value
        if value == "NONE":
            state["actual_location"] = "NOT_APPLICABLE"
        elif state.get("actual_location") == "NOT_APPLICABLE":
            state["actual_location"] = "NOT_RECORDED"
        status = f"Ground Truth: {value}; Location: {state['actual_location']}"
    elif kind == "location":
        if state.get("actual_prop_type") == "NONE":
            state["actual_location"] = "NOT_APPLICABLE"
            status = "Location is NOT_APPLICABLE for NONE ground truth"
        else:
            state["actual_location"] = value
            status = f"Location: {value}"
    elif kind == "visibility":
        state["visible"] = bool(value)
        status = "Visible: YES" if value else "Visible: NO (capture requires Clearly Visible)"
    else:
        raise ValueError(f"Unsupported operator selection: {kind}")
    state["last_status"] = status
    return status


def capture_missing_requirements(
    state: dict[str, Any],
    metadata: Any,
    frame_stats: dict[str, Any] | None,
    expected_resolution: tuple[int, int],
    max_frame_age_seconds: float,
    *,
    reader_stopped: bool = False,
) -> list[str]:
    """Return the exact conditions that currently prevent a valid sample capture."""
    missing: list[str] = []
    if not state.get("scenario_selected", False):
        missing.append("select a scenario")
    if state.get("scenario_key") == "7":
        missing.append(
            "T7 physical capture disabled: NOT_EXECUTED_PHYSICAL — FIXTURE_CONSTRAINT; "
            "use offline synthetic mask validation"
        )
    if state.get("actual_prop_type") == "NOT_RECORDED":
        missing.append("select ground truth: NONE, ROADBLOCK, POTHOLE, or UNKNOWN")
    if state.get("actual_prop_type") != "NONE" and state.get("actual_location") in {
        None, "NOT_RECORDED", "NOT_APPLICABLE",
    }:
        missing.append("select a physical location")
    if state.get("visible") is None:
        missing.append("confirm visibility: Clearly Visible or Not Clear")
    elif state.get("visible") is not True:
        missing.append("target area is marked Not Clear")
    if metadata is None:
        missing.append("wait for a successful camera frame")
    else:
        age = max(0.0, (datetime.now(timezone.utc) - metadata.timestamp).total_seconds())
        if age > max_frame_age_seconds:
            missing.append(f"wait for a fresh frame (current frame is {age:.2f}s old)")
        if frame_stats is None:
            missing.append("wait for frame brightness validation")
        elif frame_stats.get("all_black"):
            missing.append("camera frame is all black")
        reported = [int(metadata.width), int(metadata.height)]
        if reported != [int(expected_resolution[0]), int(expected_resolution[1])]:
            missing.append(
                f"camera frame is {reported[0]}x{reported[1]}, expected "
                f"{expected_resolution[0]}x{expected_resolution[1]}"
            )
    if reader_stopped:
        missing.append("camera reader stopped after repeated failures")
    return missing


def raw_camera_points(board_points: list[list[float]], crop_origin: tuple[int, int]) -> list[list[float]]:
    """Translate board-crop points into native RAW_CAMERA coordinates once."""
    ox, oy = crop_origin
    return [[round(float(x) + ox, 3), round(float(y) + oy, 3)] for x, y in board_points]


def class_outcomes(actual_prop: str, predicted_classes: set[str]) -> dict[str, dict[str, Any] | None]:
    """Return frame-level binary outcomes; unknown operator truth yields no metric."""
    if actual_prop in {"NOT_RECORDED", "UNKNOWN"}:
        return {name: None for name in TARGET_CLASSES}
    actual_class = "ROAD_OBSTACLE" if actual_prop == "ROADBLOCK" else actual_prop
    out: dict[str, dict[str, Any] | None] = {}
    for name in TARGET_CLASSES:
        actual, predicted = actual_class == name, name in predicted_classes
        outcome = "TP" if actual and predicted else "FN" if actual else "FP" if predicted else "TN"
        out[name] = {"actual_positive": actual, "predicted_positive": predicted, "outcome": outcome}
    return out


def _poly_mask(points: list[list[float]], width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if len(points) >= 3:
        coords = np.rint(np.asarray(points, dtype=np.float32)).astype(np.int32)
        cv2.fillPoly(mask, [coords], 1)
    return mask


def associate_polygon_to_regions(
    board_points: list[list[float]],
    board_shape: tuple[int, int],
    road_masks: list[Any],
    exclusions: list[Any],
) -> dict[str, Any]:
    """Associate a model polygon with exclusive S1/S2/S3 masks, never a final edge."""
    height, width = board_shape
    footprint = _poly_mask(board_points, width, height)
    area = int(np.count_nonzero(footprint))
    region_hits = []
    for mask in road_masks:
        valid = np.asarray(mask.valid_mask) != 0
        overlap = int(np.count_nonzero((footprint != 0) & valid))
        if overlap:
            region_hits.append({
                "region_id": mask.region.region_id,
                "intersection_pixels": overlap,
                "detection_pixel_overlap": round(overlap / area, 5) if area else 0.0,
                "junction_owner_rule_applied": True,
            })
    exclusion_hits = []
    for exclusion in exclusions:
        mask = _poly_mask([list(point) for point in exclusion.board_points], width, height)
        overlap = int(np.count_nonzero((footprint != 0) & (mask != 0)))
        if overlap:
            exclusion_hits.append({"region_id": exclusion.region_id, "intersection_pixels": overlap})
    if region_hits:
        primary = max(region_hits, key=lambda item: item["intersection_pixels"])["region_id"]
        status = "REGION_ONLY"
    elif exclusion_hits:
        primary, status = None, "SUPPORT_EXCLUSION_OVERLAP"
    else:
        primary, status = None, "OUTSIDE_VALID_ROAD_POLYGONS"
    return {
        "association_status": status,
        "primary_region_id": primary,
        "region_overlaps": region_hits,
        "support_exclusion_overlaps": exclusion_hits,
        "mask_pixel_count": area,
        "candidate_graph_edge_id": None,
        "edge_mapping_status": "EDGE_UNRESOLVED",
        "edge_mapping_uncertainty": "No production per-edge polygon mapping is configured; region overlap is diagnostic only.",
    }


def _frame_stats(frame: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(np.mean(gray))
    variance = float(np.var(gray))
    return {
        "resolution": [int(frame.shape[1]), int(frame.shape[0])],
        "dtype": str(frame.dtype),
        "mean_luma": round(mean, 3),
        "gray_variance": round(variance, 3),
        "all_black": bool(mean == 0 and variance == 0),
    }


def _display_sized(frame: np.ndarray, max_width: int = 1280, max_height: int = 720) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    return cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else frame


def _backend_code(name: str) -> int:
    key = name.strip().upper().removeprefix("CAP_")
    candidates = {"DSHOW": "CAP_DSHOW", "MSMF": "CAP_MSMF", "ANY": "CAP_ANY"}
    attr = candidates.get(key)
    if not attr or not hasattr(cv2, attr):
        raise RuntimeError(f"Unsupported OpenCV capture backend: {name}")
    return int(getattr(cv2, attr))


def _decode_fourcc(value: float) -> str:
    code = int(round(value))
    return "".join(chr((code >> (8 * i)) & 255) for i in range(4)).rstrip("\x00 ")


def _load_device_report() -> dict[str, Any]:
    report: dict[str, Any] = {"requested_device": "Ultralytics default/auto"}
    try:
        import torch
        report.update({"torch_version": torch.__version__, "cuda_available": bool(torch.cuda.is_available()), "cuda_version": torch.version.cuda, "gpu_count": torch.cuda.device_count()})
        if torch.cuda.is_available():
            report["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    except Exception as exc:
        report["torch_probe_error"] = f"{type(exc).__name__}: {exc}"
    try:
        import psutil
        report["process_rss_bytes_before"] = int(psutil.Process().memory_info().rss)
    except Exception:
        report["process_rss_bytes_before"] = None
    return report


def _predictor_diagnostics(wrapper: Any) -> dict[str, Any]:
    model = getattr(wrapper, "_model", None)
    predictor = getattr(model, "predictor", None)
    args = getattr(predictor, "args", None)
    return {
        "selected_device": str(getattr(predictor, "device", "unknown")),
        "effective_confidence": getattr(args, "conf", None),
        "nms_iou": getattr(args, "iou", None),
        "agnostic_nms": getattr(args, "agnostic_nms", None),
        "max_detections": getattr(args, "max_det", None),
    }


def _annotate_full_frame(raw: np.ndarray, processed: Any, config: Any, associations: list[dict[str, Any]], ground_truth: dict[str, Any]) -> np.ndarray:
    from scripts.validate_polygon_vision import render_reference_overlay

    annotated = render_reference_overlay(raw.copy(), config)
    ox, oy = config.crop.x, config.crop.y
    for detection in processed.result.detections:
        box = detection.bounding_box
        p1 = (round(box.x1 + ox), round(box.y1 + oy))
        p2 = (round(box.x2 + ox), round(box.y2 + oy))
        cv2.rectangle(annotated, p1, p2, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(annotated, f"DETECT {detection.class_name} {detection.confidence:.2f}", (p1[0], max(20, p1[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, .52, (0, 0, 255), 2, cv2.LINE_AA)
    board_h, board_w = processed.board_frame.shape[:2]
    for index, segmentation in enumerate(processed.result.segmentations):
        local = [[point.x, point.y] for point in segmentation.polygon]
        mask = _poly_mask(local, board_w, board_h)
        full = np.zeros(raw.shape[:2], dtype=np.uint8)
        y2, x2 = min(raw.shape[0], oy + board_h), min(raw.shape[1], ox + board_w)
        full[oy:y2, ox:x2] = mask[:y2-oy, :x2-ox]
        color = (0, 120, 255) if segmentation.class_name == "ROAD_OBSTACLE" else (255, 80, 0)
        overlay = annotated.copy()
        overlay[full != 0] = color
        cv2.addWeighted(overlay, .30, annotated, .70, 0, annotated)
        contours, _ = cv2.findContours(full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(annotated, contours, -1, color, 2, cv2.LINE_AA)
            x, y, _, _ = cv2.boundingRect(contours[0])
            assoc = associations[index]
            region = assoc.get("association", {}).get("primary_region_id") or assoc.get("association", {}).get("association_status")
            cv2.putText(annotated, f"SEG {segmentation.class_name} {segmentation.confidence:.2f} | {region}", (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, .48, color, 2, cv2.LINE_AA)
    headline = f"TEST_ONLY | {ground_truth['scenario_id']} | GT={ground_truth['actual_prop_type']} @ {ground_truth['actual_physical_location']} | NO ROUTING/ACTUATORS"
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 42), (25, 25, 25), -1)
    cv2.putText(annotated, headline[:150], (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .58, (255, 255, 255), 2, cv2.LINE_AA)
    return annotated


def _model_identity(wrapper: Any) -> dict[str, Any]:
    model = getattr(wrapper, "_model", None)
    path = getattr(model, "ckpt_path", None)
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        classes = [str(names[i]) for i in range(len(names))]
    elif isinstance(names, (list, tuple)):
        classes = list(map(str, names))
    else:
        classes = []
    return {
        "weights": str(Path(path).resolve()) if path else None,
        "task": getattr(model, "task", None),
        "classes": classes,
        "relevant_class_filter": [name.upper() for name in classes],
        **_predictor_diagnostics(wrapper),
    }


def _quality_status(actual_prop: str, predictions: list[dict[str, Any]], review_threshold: float) -> dict[str, Any]:
    predicted = {item["class"] for item in predictions if item["class"] in TARGET_CLASSES}
    outcomes = class_outcomes(actual_prop, predicted)
    if not predictions:
        state = "NO_DETECTION"
    elif not predicted:
        state = "OTHER_CLASS_DETECTION_ONLY"
    elif all(item["confidence"] < review_threshold for item in predictions if item["class"] in TARGET_CLASSES):
        state = "LOW_CONFIDENCE_DETECTION"
    else:
        state = "TARGET_CLASS_DETECTION"
    return {"status": state, "review_confidence_threshold": review_threshold, "class_outcomes": outcomes,
            "note": "No-detection is not evidence that a road is clear; frame-level counts are descriptive only."}


def _association_for_frame(processed: Any, polygon_config: Any, scenario: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    board_h, board_w = processed.board_frame.shape[:2]
    road_masks = polygon_config.road_masks(processed.board_frame.shape)
    associations: list[dict[str, Any]] = []
    raw_instances: list[dict[str, Any]] = []
    predicted_classes: list[dict[str, Any]] = []
    for det in processed.result.segmentations:
        points = [[p.x, p.y] for p in det.polygon]
        association = associate_polygon_to_regions(points, (board_h, board_w), road_masks, list(polygon_config.exclusions))
        raw_points = raw_camera_points(points, (polygon_config.crop.x, polygon_config.crop.y))
        item = {"source": "segmentation", "class": det.class_name, "confidence": round(det.confidence, 5),
                "bbox_board_crop": [det.bounding_box.x1, det.bounding_box.y1, det.bounding_box.x2, det.bounding_box.y2],
                "bbox_raw_camera": [det.bounding_box.x1+polygon_config.crop.x, det.bounding_box.y1+polygon_config.crop.y,
                                    det.bounding_box.x2+polygon_config.crop.x, det.bounding_box.y2+polygon_config.crop.y],
                "polygon_board_crop": points, "polygon_raw_camera": raw_points,
                "association": association,
                "diagnostic_candidate_edge": {"edge_id": scenario.get("candidate_edge"), "source": "SCENARIO_DESIGN_ONLY", "status": "EDGE_UNRESOLVED"}}
        raw_instances.append(item)
        associations.append(item)
        predicted_classes.append({"class": det.class_name, "confidence": float(det.confidence)})
    # Detector boxes are retained separately; this checkpoint has no road-prop classes.
    detector_instances = []
    for det in processed.result.detections:
        box = det.bounding_box
        points = [[box.x1, box.y1], [box.x2, box.y1], [box.x2, box.y2], [box.x1, box.y2]]
        assoc = associate_polygon_to_regions(points, (board_h, board_w), road_masks, list(polygon_config.exclusions))
        detector_instances.append({"source":"detection", "class":det.class_name, "confidence":round(det.confidence,5),
            "bbox_board_crop":[box.x1,box.y1,box.x2,box.y2],
            "bbox_raw_camera":[box.x1+polygon_config.crop.x,box.y1+polygon_config.crop.y,box.x2+polygon_config.crop.x,box.y2+polygon_config.crop.y],
            "association":assoc,"diagnostic_candidate_edge":{"edge_id":scenario.get("candidate_edge"),"source":"SCENARIO_DESIGN_ONLY","status":"EDGE_UNRESOLVED"}})
    region_data = []
    for evidence in processed.road_evidence:
        region_data.append({"region_id": next((m.region.region_id for m in road_masks if m.region.label == evidence.road_roi_name), evidence.road_roi_name),
                            "label": evidence.road_roi_name, "estimated_occupancy_ratio": evidence.occupancy_ratio,
                            "occupied_pixels": evidence.occupied_pixels,
                            "contributing_classes": evidence.contributing_classes,
                            "evidence_interpretation":"VISION_DIAGNOSTIC_ONLY_NOT_CLEAR_NOT_BLOCKED",
                            "frame_id":processed.result.raw_frame.frame_id,"frame_timestamp":processed.result.raw_frame.timestamp.isoformat()})
    return raw_instances, detector_instances, region_data


def run_operator_test(args: Any, polygon_config: Any, output_root: Path) -> int:
    """Run an operator-selected live preview; inference occurs only after a capture keypress."""
    from dataclasses import replace
    from app.vision.capture import CapturedFrame
    from app.vision.config import get_vision_config
    from app.vision.model_contract import resolve_weights_path
    from app.vision.pipeline import IntegratedVisionPipeline
    from app.vision.schemas import CoordinateSystem, FrameMetadata, FrameSourceType
    import cv2 as cv

    if args.max_frame_age_seconds <= 0:
        raise ValueError("max-frame-age-seconds must be positive")
    if not 0 <= args.test_confidence_floor <= 1 or not 0 <= args.review_confidence_threshold <= 1:
        raise ValueError("confidence thresholds must be between 0 and 1")
    if args.read_failure_limit < 1:
        raise ValueError("read-failure-limit must be at least 1")

    output_root = output_root.resolve()
    session_id = datetime.now(timezone.utc).strftime("session_%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:6]
    session = output_root / session_id
    sample_dir = session / "samples"
    sample_dir.mkdir(parents=True, exist_ok=False)

    camera_index = args.camera_index if args.camera_index is not None else 0
    backend_name = args.backend or "DSHOW"
    fourcc = (args.fourcc or "MJPG").upper()
    if len(fourcc) != 4 or not fourcc.isascii():
        raise ValueError("FOURCC must contain exactly four ASCII characters")

    cap = cv.VideoCapture(camera_index, _backend_code(backend_name))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Unable to open camera index {camera_index} using {backend_name}")
    fourcc_set = width_set = height_set = False
    backend_actual = "unknown"
    try:
        # Match the confirmed standalone test: negotiate MJPG before frame dimensions.
        fourcc_set = bool(cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*fourcc)))
        width_set = bool(cap.set(cv.CAP_PROP_FRAME_WIDTH, args.width))
        height_set = bool(cap.set(cv.CAP_PROP_FRAME_HEIGHT, args.height))
        backend_actual = cap.getBackendName()
    except (AttributeError, cv.error):
        backend_actual = "unknown"
    camera = {
        "index": camera_index,
        "backend_requested": backend_name,
        "backend_actual": backend_actual,
        "fourcc_requested": fourcc,
        "fourcc_set_succeeded": fourcc_set,
        "fourcc_actual_reported": _decode_fourcc(cap.get(cv.CAP_PROP_FOURCC)),
        "resolution_requested": [args.width, args.height],
        "width_set_succeeded": width_set,
        "height_set_succeeded": height_set,
        "resolution_reported_after_setup": [
            int(round(cap.get(cv.CAP_PROP_FRAME_WIDTH))),
            int(round(cap.get(cv.CAP_PROP_FRAME_HEIGHT))),
        ],
        "device_reported_fps": cap.get(cv.CAP_PROP_FPS),
        "actual_resolution_first_frame": None,
        "actual_fourcc_first_frame": None,
    }
    LOGGER.info(
        "Camera requested: index=%s backend_requested=%s backend_actual=%s "
        "fourcc_requested=%s fourcc_actual=%s resolution_requested=%sx%s "
        "resolution_reported=%sx%s fps_reported=%.3f set_results=(%s,%s,%s)",
        camera_index,
        backend_name,
        backend_actual,
        fourcc,
        camera["fourcc_actual_reported"] or "unknown",
        args.width,
        args.height,
        *camera["resolution_reported_after_setup"],
        camera["device_reported_fps"],
        fourcc_set,
        width_set,
        height_set,
    )

    base = get_vision_config()
    config = replace(
        base,
        source="CAMERA",
        camera_index=camera_index,
        capture_backend=backend_name,
        capture_fourcc=fourcc,
        frame_width=args.width,
        frame_height=args.height,
        polygon_roi_enabled=True,
        polygon_roi_config_path=str(polygon_config.path),
        detection_confidence_threshold=args.test_confidence_floor,
        segmentation_confidence_threshold=args.test_confidence_floor,
    )
    pipeline = None
    try:
        pipeline = IntegratedVisionPipeline(config=config)
        device_report = _load_device_report()
        session_meta: dict[str, Any] = {
            "test_only": True,
            "session_id": session_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "production_routing_active": False,
            "mqtt_publishing": False,
            "dispatch": False,
            "actuators": False,
            "camera": camera,
            "polygon_draft": str(polygon_config.path),
            "polygon_draft_status": polygon_config.status,
            "coordinate_system": "RAW_CAMERA",
            "board_crop": {
                "x": polygon_config.crop.x,
                "y": polygon_config.crop.y,
                "width": polygon_config.crop.width,
                "height": polygon_config.crop.height,
            },
            "road_regions": [region.region_id for region in polygon_config.road_segments],
            "junction_owner_region_id": polygon_config.junction_owner_region_id,
            "model_checkpoints": {
                "detection": str(resolve_weights_path(config.detection_model)),
                "segmentation": str(resolve_weights_path(config.segmentation_model)),
            },
            "model_class_contract": {
                "detection": ["fire", "smoke", "person"],
                "segmentation": ["road_obstacle", "pothole"],
                "roadblock_ground_truth_maps_to": "ROAD_OBSTACLE",
            },
            "test_confidence_floor": args.test_confidence_floor,
            "review_confidence_threshold": args.review_confidence_threshold,
            "configured_production_confidence_thresholds": {
                "detection": base.detection_confidence_threshold,
                "segmentation": base.segmentation_confidence_threshold,
            },
            "device": device_report,
            "scenario_definitions": {value["id"]: value for value in SCENARIOS.values()},
        }
        metadata_path = session / "session_metadata.json"
        metadata_path.write_text(json.dumps(session_meta, indent=2), encoding="utf-8")

        lock = threading.Lock()
        stop = threading.Event()
        jobs: queue.Queue[Any] = queue.Queue(maxsize=1)
        results: queue.Queue[Any] = queue.Queue()
        shared: dict[str, Any] = {
            "frame": None,
            "metadata": None,
            "read_latency_ms": None,
            "last_error": None,
            "read_failures": 0,
            "consecutive_failures": 0,
            "read_count": 0,
            "read_timestamps": [],
            "latencies": [],
            "reader_stopped": False,
            "last_frame_stats": None,
        }
        completed: list[dict[str, Any]] = []
        worker_busy = threading.Event()
        sample_index = 0
        state: dict[str, Any] = {
            "scenario_key": "0",
            "scenario_selected": False,
            "actual_prop_type": "NOT_RECORDED",
            "actual_location": "NOT_RECORDED",
            "visible": None,
            "last_status": "Select a scenario, ground truth, and visibility",
            "grid": False,
            "margins": True,
            "roi_overlay": True,
        }
        pending_action: dict[str, str | None] = {"value": None}
        started = time.monotonic()
        exit_requested = False

        def reader() -> None:
            first_frame_logged = False
            while not stop.is_set():
                read_started = perf_counter()
                ok, frame = cap.read()
                latency_ms = (perf_counter() - read_started) * 1000
                if not ok or frame is None:
                    with lock:
                        shared["read_failures"] += 1
                        shared["consecutive_failures"] += 1
                        failures = shared["consecutive_failures"]
                        shared["last_error"] = f"Camera read failed ({failures}/{args.read_failure_limit})"
                        if failures >= args.read_failure_limit:
                            shared["reader_stopped"] = True
                    LOGGER.warning("Camera read failed: consecutive=%s/%s", failures, args.read_failure_limit)
                    if failures >= args.read_failure_limit:
                        stop.set()
                        break
                    stop.wait(0.05)
                    continue

                captured_at = datetime.now(timezone.utc)
                height, width = frame.shape[:2]
                metadata = FrameMetadata(
                    frame_id=str(uuid4()),
                    timestamp=captured_at,
                    source=FrameSourceType.CAMERA,
                    width=width,
                    height=height,
                    coordinate_system=CoordinateSystem.RAW_CAMERA,
                )
                with lock:
                    shared["frame"] = frame
                    shared["metadata"] = metadata
                    shared["read_latency_ms"] = latency_ms
                    shared["last_error"] = None
                    shared["consecutive_failures"] = 0
                    shared["read_count"] += 1
                    shared["read_timestamps"].append(captured_at)
                    shared["latencies"].append(latency_ms)
                    if len(shared["latencies"]) > 1200:
                        del shared["latencies"][:600]
                        del shared["read_timestamps"][:600]
                    if camera["actual_resolution_first_frame"] is None:
                        camera["actual_resolution_first_frame"] = [width, height]
                        camera["actual_fourcc_first_frame"] = _decode_fourcc(
                            cap.get(cv.CAP_PROP_FOURCC)
                        )
                if not first_frame_logged:
                    first_frame_logged = True
                    LOGGER.info(
                        "Camera read success: first_frame=%sx%s dtype=%s fourcc=%s "
                        "requested=%sx%s",
                        width,
                        height,
                        frame.dtype,
                        camera["actual_fourcc_first_frame"] or "unknown",
                        args.width,
                        args.height,
                    )

        def persist_json(path: Path, value: dict[str, Any]) -> None:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

        def inference_worker() -> None:
            while True:
                task = jobs.get()
                if task is None:
                    return
                raw, captured, read_latency, gt, scenario, chosen_index, paths, frame_stats = task
                raw_path, annotated_path, json_path = paths
                sample_id = f"{gt['scenario_id']}_{chosen_index:04d}"
                started_at = perf_counter()
                load_ms: dict[str, float] = {}
                try:
                    if not cv2.imwrite(str(raw_path), raw, [cv2.IMWRITE_JPEG_QUALITY, 98]):
                        raise OSError(f"Failed to save raw reference frame: {raw_path}")
                    if frame_stats["all_black"]:
                        raise ValueError("All-black frame rejected; inference was not run")
                    if [raw.shape[1], raw.shape[0]] != [args.width, args.height]:
                        raise ValueError(
                            f"Frame is {raw.shape[1]}x{raw.shape[0]}, expected {args.width}x{args.height}"
                        )

                    for name, wrapper in (("detection", pipeline.detector), ("segmentation", pipeline.segmenter)):
                        load_started = perf_counter()
                        if getattr(wrapper, "_model", None) is None:
                            wrapper._load_model()
                        load_ms[name] = round((perf_counter() - load_started) * 1000, 3)

                    inference_wall_started = datetime.now(timezone.utc)
                    inference_started = perf_counter()
                    age_ms = max(
                        0.0,
                        (inference_wall_started - captured.metadata.timestamp).total_seconds() * 1000,
                    )
                    processed = pipeline.process_captured_frame(
                        captured,
                        capture_duration_ms=read_latency,
                        total_started_at=inference_started,
                    )
                    pipeline_elapsed_ms = (perf_counter() - inference_started) * 1000

                    mask_started = perf_counter()
                    seg_instances, det_instances, region_data = _association_for_frame(
                        processed, polygon_config, scenario
                    )
                    mask_filter_ms = (perf_counter() - mask_started) * 1000
                    overlay_started = perf_counter()
                    annotated = _annotate_full_frame(
                        raw, processed, polygon_config, seg_instances, gt
                    )
                    overlay_ms = (perf_counter() - overlay_started) * 1000
                    segmentation_predictions = [
                        {"class": item.class_name, "confidence": round(float(item.confidence), 5)}
                        for item in processed.result.segmentations
                    ]
                    quality = _quality_status(
                        gt["actual_prop_type"],
                        segmentation_predictions,
                        args.review_confidence_threshold,
                    )
                    result: dict[str, Any] = {
                        "test_only": True,
                        "status": "PROCESSED_DIAGNOSTIC_ONLY",
                        "sample_id": sample_id,
                        "scenario": scenario,
                        "ground_truth": gt,
                        "frame": {
                            "frame_id": captured.metadata.frame_id,
                            "captured_at": captured.metadata.timestamp.isoformat(),
                            "inference_started_at": inference_wall_started.isoformat(),
                            "inference_completed_at": datetime.now(timezone.utc).isoformat(),
                            "age_at_inference_start_ms": round(age_ms, 3),
                            "frame_stats": frame_stats,
                        },
                        "models": {
                            "detection": _model_identity(pipeline.detector),
                            "segmentation": _model_identity(pipeline.segmenter),
                        },
                        "predictions": {
                            "detection_model_status": "PREDICTIONS_AVAILABLE" if det_instances else "NO_DETECTION",
                            "detection_instances": det_instances,
                            "segmentation_status": "PREDICTIONS_AVAILABLE" if seg_instances else "NO_DETECTION",
                            "segmentation_instances": seg_instances,
                            "road_class_quality": quality,
                        },
                        "road_regions": region_data,
                        "road_safety_handoff": {
                            "status": "READ_ONLY_DIAGNOSTIC_UNRESOLVED",
                            "vision_only_blocked": False,
                            "vision_only_clear": False,
                            "no_detection_means_clear": False,
                            "ir_required_for_production_safety": True,
                            "dispatch_recommendation": None,
                        },
                        "latency_ms": {
                            "camera_read": round(read_latency, 3),
                            "preprocessing_board_crop": processed.result.crop_duration_ms,
                            "detection_pipeline_branch": processed.result.detection_duration_ms,
                            "detection_predict_call": pipeline.detector.last_inference_duration_ms,
                            "segmentation_pipeline_branch": processed.result.segmentation_duration_ms,
                            "segmentation_predict_call": pipeline.segmenter.last_inference_duration_ms,
                            "postprocessing": processed.result.postprocessing_duration_ms,
                            "polygon_mask_filtering": round(mask_filter_ms, 3),
                            "overlay_rendering": round(overlay_ms, 3),
                            "model_loading_excluded_from_inference_ms": load_ms,
                            "pipeline_ms": round(pipeline_elapsed_ms, 3),
                            "full_validation_after_model_load_ms": round((perf_counter() - inference_started) * 1000, 3),
                            "full_validation_fps_after_model_load": round(
                                1000 / max((perf_counter() - inference_started) * 1000, 1e-6), 4
                            ),
                        },
                        "memory": {"process_rss_bytes": None, "cuda_allocated_bytes": None, "cuda_peak_bytes": None},
                        "warnings": [
                            "TEST_ONLY; no route evidence, dispatch, MQTT, or actuator side effects.",
                            "Region overlap and scenario candidate edge are diagnostic only; graph edge remains EDGE_UNRESOLVED.",
                            "No detection is not evidence that the road is clear.",
                        ],
                    }
                    try:
                        import psutil
                        result["memory"]["process_rss_bytes"] = int(psutil.Process().memory_info().rss)
                    except Exception:
                        pass
                    try:
                        import torch
                        if torch.cuda.is_available():
                            device = getattr(getattr(pipeline.detector._model, "predictor", None), "device", 0)
                            result["memory"]["cuda_allocated_bytes"] = int(torch.cuda.memory_allocated(device))
                            result["memory"]["cuda_peak_bytes"] = int(torch.cuda.max_memory_allocated(device))
                    except Exception:
                        pass

                    if not cv2.imwrite(str(annotated_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                        raise OSError(f"Failed to save annotated reference frame: {annotated_path}")
                    result["artifacts"] = {
                        "raw_frame": str(raw_path.resolve()),
                        "annotated_frame": str(annotated_path.resolve()),
                        "sample_json": str(json_path.resolve()),
                    }
                    persist_json(json_path, result)
                    results.put({"result": result, "annotated": annotated, "error": None})
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    try:
                        fallback = render_reference_overlay(raw.copy(), polygon_config)
                        cv2.rectangle(fallback, (0, 0), (fallback.shape[1], 44), (20, 20, 20), -1)
                        cv2.putText(fallback, f"TEST_ONLY INFERENCE FAILED: {error}"[:150], (12, 29), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 255), 2, cv2.LINE_AA)
                        if not cv2.imwrite(str(annotated_path), fallback, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                            fallback = None
                    except Exception:
                        fallback = None
                    failed_result = {
                        "test_only": True,
                        "status": "INFERENCE_FAILED",
                        "sample_id": sample_id,
                        "scenario": scenario,
                        "ground_truth": gt,
                        "frame": {
                            "frame_id": captured.metadata.frame_id,
                            "captured_at": captured.metadata.timestamp.isoformat(),
                            "frame_stats": frame_stats,
                        },
                        "error": error,
                        "model_load_ms": load_ms,
                        "predictions": None,
                        "road_safety_handoff": {
                            "status": "UNAVAILABLE_FAIL_SAFE",
                            "vision_only_blocked": False,
                            "vision_only_clear": False,
                            "dispatch_recommendation": None,
                        },
                        "artifacts": {
                            "raw_frame": str(raw_path.resolve()) if raw_path.exists() else None,
                            "annotated_frame": str(annotated_path.resolve()) if annotated_path.exists() else None,
                            "sample_json": str(json_path.resolve()),
                        },
                    }
                    persist_json(json_path, failed_result)
                    results.put({"result": failed_result, "annotated": fallback, "error": error})
                finally:
                    worker_busy.clear()

        camera_thread = threading.Thread(target=reader, name="road-test-camera-reader", daemon=True)
        worker_thread = threading.Thread(target=inference_worker, name="road-test-inference", daemon=True)
        camera_thread_started = False
        worker_thread_started = False
        window = "CityResponder Real Camera Road Vision Test - TEST_ONLY"
        control_window = "Road Vision Operator Controls - TEST_ONLY"
        completed: list[dict[str, Any]] = []
        latest_frame_id: str | None = None
        last_stats_at = 0.0
        display_stats: dict[str, Any] | None = None
        last_ui_metrics_at = started
        try:
            cv.namedWindow(window, cv.WINDOW_NORMAL)
            cv.resizeWindow(window, 1280, 720)
            cv.namedWindow(control_window, cv.WINDOW_AUTOSIZE)

            def on_control_mouse(event: int, x: int, y: int, _flags: int, _param: Any) -> None:
                if event != cv.EVENT_LBUTTONUP:
                    return
                button = hit_test_control_button(x, y)
                if button is None:
                    state["last_status"] = f"No control at ({x}, {y}); click a labeled button"
                    LOGGER.info("Operator clicked an unused control-panel coordinate: x=%s y=%s", x, y)
                elif button["kind"] in {"scenario", "truth", "location", "visibility"}:
                    apply_operator_selection(state, button["kind"], button["value"])
                    LOGGER.info(
                        "Operator mouse input: kind=%s value=%s scenario=%s truth=%s location=%s visible=%s",
                        button["kind"], button["value"], state["scenario_key"],
                        state["actual_prop_type"], state["actual_location"], state["visible"],
                    )
                elif button["kind"] in {"capture", "exit"}:
                    pending_action["value"] = button["kind"]
                    state["last_status"] = (
                        "Capture requested; validating truth and current frame"
                        if button["kind"] == "capture" else "Exit requested"
                    )
                    LOGGER.info("Operator mouse action: %s", button["kind"])

            cv.setMouseCallback(control_window, on_control_mouse)
            (session / "session_metadata.json").write_text(
                json.dumps(session_meta, indent=2), encoding="utf-8"
            )
            camera_thread.start()
            camera_thread_started = True
            worker_thread.start()
            worker_thread_started = True
            print(f"TEST_ONLY session: {session.resolve()}")
            print(
                "Keys: 0-7 select T0-T7; R=ROADBLOCK, P=POTHOLE, N=NONE, U=UNKNOWN; "
                "A=PE04, S=PE02, D=outside, F=J1, J=J2, K=support, L=PE06, "
                "I=PE07, E=other/unknown; Y=target area clearly visible, H=not clear; "
                "SPACE=capture and run both models once; G=toggle grid, M=toggle margins, "
                "O=toggle read-only ROI; Q/Esc=exit."
            )
            print(
                "Record the physical truth and location, mark Y, then press SPACE. "
                "No sample is inferred or saved unless the pinned frame is fresh, non-black, "
                "native resolution, and marked clearly visible."
            )

            while True:
                with lock:
                    frame = shared["frame"]
                    metadata = shared["metadata"]
                    read_latency = shared["read_latency_ms"]
                    last_error = shared["last_error"]
                    reader_stopped = shared["reader_stopped"]
                    read_count = shared["read_count"]
                    read_failures = shared["read_failures"]
                    latencies = list(shared["latencies"])

                if frame is not None and metadata is not None and metadata.frame_id != latest_frame_id:
                    latest_frame_id = metadata.frame_id
                if frame is not None and metadata is not None and time.monotonic() - last_stats_at >= 0.5:
                    display_stats = _frame_stats(frame)
                    last_stats_at = time.monotonic()

                if frame is None or metadata is None:
                    display = np.zeros((720, 1280, 3), dtype=np.uint8)
                    status = last_error or "Opening camera / waiting for the first successful frame"
                    cv.putText(display, status[:100], (35, 80), cv.FONT_HERSHEY_SIMPLEX, .75, (255, 255, 255), 2, cv.LINE_AA)
                else:
                    frame_age = max(0.0, (datetime.now(timezone.utc) - metadata.timestamp).total_seconds())
                    stale_message = last_error
                    if frame_age > args.max_frame_age_seconds:
                        stale_message = f"STALE CAMERA FRAME ({frame_age:.1f}s old); waiting for a new read"
                    if reader_stopped:
                        stale_message = last_error or "Camera reader stopped after repeated failures"
                    display = render_preview(
                        frame,
                        polygon_config,
                        metadata,
                        state,
                        worker_busy.is_set(),
                        stale_message,
                        frame_stats=display_stats,
                    )
                cv.imshow(window, _display_sized(display))
                with lock:
                    panel_read_count = shared["read_count"]
                    panel_read_failures = shared["read_failures"]
                    panel_latencies = list(shared["latencies"])
                    panel_timestamps = list(shared["read_timestamps"])
                panel = render_control_panel(
                    camera,
                    metadata,
                    state,
                    worker_busy.is_set(),
                    stale_message if frame is not None and metadata is not None else last_error,
                    display_stats,
                    panel_read_count,
                    panel_read_failures,
                    panel_latencies,
                    panel_timestamps,
                    args,
                    reader_stopped=reader_stopped,
                )
                cv.imshow(control_window, panel)
                raw_key = cv.waitKey(1)
                key = normalize_key_code(raw_key & 0xFF) if raw_key >= 0 else -1
                if raw_key >= 0:
                    LOGGER.info("Operator keyboard input: raw=%s normalized=%s", raw_key & 0xFF, key)

                if key in (27, ord("q")) or pending_action["value"] == "exit":
                    pending_action["value"] = None
                    exit_requested = True
                    stop.set()
                    state["last_status"] = (
                        "Finishing the pinned single-frame inference before clean exit"
                        if worker_busy.is_set() else "Exiting cleanly"
                    )
                elif key in map(ord, "01234567"):
                    apply_operator_selection(state, "scenario", chr(key))
                elif key in PROP_KEYS:
                    apply_operator_selection(state, "truth", PROP_KEYS[key])
                elif key in LOCATION_KEYS:
                    apply_operator_selection(state, "location", LOCATION_KEYS[key])
                elif key in VISIBILITY_KEYS:
                    apply_operator_selection(state, "visibility", VISIBILITY_KEYS[key])
                elif key == ord("g"):
                    state["grid"] = not state.get("grid", False)
                    state["last_status"] = f"Grid {'ON' if state['grid'] else 'OFF'}"
                elif key == ord("m"):
                    state["margins"] = not state.get("margins", True)
                    state["last_status"] = f"Margin guides {'ON' if state['margins'] else 'OFF'}"
                elif key == ord("o"):
                    state["roi_overlay"] = not state.get("roi_overlay", True)
                    state["last_status"] = f"Read-only ROI overlay {'ON' if state['roi_overlay'] else 'OFF'}"
                elif key == ord(" "):
                    pending_action["value"] = "capture"
                elif 32 <= key <= 126:
                    state["last_status"] = f"Unrecognized key '{chr(key)}'; use a labeled control or listed shortcut"
                    LOGGER.warning("Unrecognized operator shortcut key: %r", chr(key))

                capture_requested = pending_action["value"] == "capture"
                if capture_requested:
                    pending_action["value"] = None
                    if worker_busy.is_set():
                        state["last_status"] = "CAPTURE BLOCKED: inference is already running"
                    else:
                        missing = capture_missing_requirements(
                            state, metadata, display_stats, (args.width, args.height),
                            args.max_frame_age_seconds, reader_stopped=reader_stopped,
                        )
                        if missing:
                            state["last_status"] = "CAPTURE BLOCKED: " + "; ".join(missing)
                            LOGGER.warning("Capture rejected: %s", state["last_status"])
                        else:
                            age_seconds = max(
                                0.0, (datetime.now(timezone.utc) - metadata.timestamp).total_seconds()
                            )
                            pinned = frame.copy()
                            pinned_stats = _frame_stats(pinned)
                            pinned_missing = []
                            if age_seconds > args.max_frame_age_seconds:
                                pinned_missing.append(f"frame is stale ({age_seconds:.2f}s old)")
                            if pinned_stats["all_black"]:
                                pinned_missing.append("current camera frame is all black")
                            if pinned_stats["resolution"] != [args.width, args.height]:
                                pinned_missing.append(
                                    f"frame is {pinned_stats['resolution'][0]}x{pinned_stats['resolution'][1]}, "
                                    f"expected {args.width}x{args.height}"
                                )
                            if pinned_missing:
                                state["last_status"] = "CAPTURE BLOCKED: " + "; ".join(pinned_missing)
                                LOGGER.warning("Pinned-frame validation rejected capture: %s", state["last_status"])
                            else:
                                sample_index += 1
                                scenario = SCENARIOS[state["scenario_key"]]
                                gt = {
                                    "scenario_id": scenario["id"],
                                    "actual_prop_type": state["actual_prop_type"],
                                    "actual_physical_location": state["actual_location"],
                                    "expected_class": scenario["expected_class"],
                                    "expected_region": scenario["expected_region"],
                                    "scenario_diagnostic_candidate_edge": scenario["candidate_edge"],
                                    "roadblock_label_mapping": "ROADBLOCK -> ROAD_OBSTACLE",
                                    "visibility_status": "CLEARLY_VISIBLE",
                                    "target_area_clearly_visible": True,
                                    "operator_confirmed_truth": True,
                                    "operator_recorded_at": datetime.now(timezone.utc).isoformat(),
                                }
                                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
                                stem = f"TEST_ONLY_{scenario['id']}_{timestamp}"
                                paths = (
                                    sample_dir / f"{stem}_raw.jpg",
                                    sample_dir / f"{stem}_annotated.jpg",
                                    sample_dir / f"{stem}.json",
                                )
                                captured = CapturedFrame(pinned, metadata)
                                worker_busy.set()
                                jobs.put((pinned, captured, float(read_latency or 0.0), gt, scenario, sample_index, paths, pinned_stats))
                                state["last_status"] = f"Pinned {metadata.frame_id}; running both models once on this frame"

                while not results.empty():
                    message = results.get()
                    result = message["result"]
                    if result is not None:
                        completed.append(result)
                    if message["error"]:
                        state["last_status"] = "Inference failed; fail-safe diagnostic saved: " + message["error"]
                        LOGGER.error(state["last_status"])
                    elif result is not None:
                        state["last_status"] = (
                            f"Saved {result['sample_id']} - "
                            f"{result['predictions']['road_class_quality']['status']}"
                        )
                        cv.imshow("Captured YOLO result - TEST_ONLY", _display_sized(message["annotated"], 1600, 900))
                        print(json.dumps({
                            "sample_id": result["sample_id"],
                            "status": result["status"],
                            "artifacts": result["artifacts"],
                            "latency_ms": result["latency_ms"],
                            "segmentation_status": result["predictions"]["segmentation_status"],
                        }, indent=2))

                now = time.monotonic()
                if now - last_ui_metrics_at >= 10.0:
                    last_ui_metrics_at = now
                    with lock:
                        read_count = shared["read_count"]
                        read_timestamps = list(shared["read_timestamps"])
                        failures = shared["read_failures"]
                        latencies = list(shared["latencies"])
                    preview_fps = (
                        (len(read_timestamps) - 1) /
                        max((read_timestamps[-1] - read_timestamps[0]).total_seconds(), 1e-6)
                        if len(read_timestamps) > 1 else 0.0
                    )
                    LOGGER.info(
                        "Camera preview diagnostics: frames=%s measured_fps=%.2f read_failures=%s "
                        "read_latency_mean_ms=%s read_latency_p95_ms=%s frame_stats=%s",
                        read_count,
                        preview_fps,
                        failures,
                        round(float(np.mean(latencies)), 3) if latencies else None,
                        round(float(np.percentile(latencies, 95)), 3) if latencies else None,
                        display_stats,
                    )

                if exit_requested and not worker_busy.is_set() and results.empty():
                    break
        finally:
            stop.set()
            if camera_thread_started:
                camera_thread.join(timeout=2.0)
            if camera_thread.is_alive():
                LOGGER.warning("Camera reader did not stop within 2 seconds; releasing capture to unblock it")
                cap.release()
                camera_thread.join(timeout=3.0)
            try:
                jobs.put_nowait(None)
            except queue.Full:
                pass
            if worker_thread_started:
                worker_thread.join(timeout=10.0)
            if worker_thread_started and worker_thread.is_alive():
                LOGGER.warning("Inference worker is still finishing; waiting before closing the pipeline")
                worker_thread.join()
            cap.release()
            pipeline.close()
            cv.destroyAllWindows()

            while not results.empty():
                message = results.get()
                if message["result"] is not None:
                    completed.append(message["result"])
            with lock:
                frame_count = shared["read_count"]
                failures = shared["read_failures"]
                latencies = list(shared["latencies"])
                read_timestamps = list(shared["read_timestamps"])
                last_frame = shared["frame"]
                last_frame_metadata = shared["metadata"]
            elapsed = max(time.monotonic() - started, 1e-6)
            measured_capture_fps = (
                (len(read_timestamps) - 1) /
                max((read_timestamps[-1] - read_timestamps[0]).total_seconds(), 1e-6)
                if len(read_timestamps) > 1 else 0.0
            )
            session_meta.update({
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 3),
                "frames_read_successfully": frame_count,
                "read_failures": failures,
                "measured_capture_fps": round(measured_capture_fps, 4),
                "capture_latency_ms_mean": round(float(np.mean(latencies)), 3) if latencies else None,
                "capture_latency_ms_p95": round(float(np.percentile(latencies, 95)), 3) if latencies else None,
                "last_valid_frame": {
                    "frame_id": last_frame_metadata.frame_id if last_frame_metadata else None,
                    "frame_stats": _frame_stats(last_frame) if last_frame is not None else None,
                },
                "sample_count": len(completed),
                "samples": [r["artifacts"]["sample_json"] for r in completed],
            })
            (session / "session_metadata.json").write_text(
                json.dumps(session_meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (session / "results.json").write_text(
                json.dumps({"test_only": True, "samples": completed}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            fields = [
                "sample_id", "status", "scenario_id", "actual_prop_type", "actual_physical_location",
                "visibility_status", "frame_captured_at", "segmentation_status", "predicted_classes",
                "region_associations", "camera_read_ms", "preprocessing_ms", "detection_ms",
                "segmentation_ms", "postprocessing_ms", "polygon_mask_filtering_ms", "overlay_rendering_ms",
                "error",
            ]
            with (session / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for result in completed:
                    predictions = result.get("predictions") or {}
                    lat = result.get("latency_ms") or {}
                    segments = predictions.get("segmentation_instances") or []
                    writer.writerow({
                        "sample_id": result.get("sample_id"),
                        "status": result.get("status"),
                        "scenario_id": result.get("ground_truth", {}).get("scenario_id"),
                        "actual_prop_type": result.get("ground_truth", {}).get("actual_prop_type"),
                        "actual_physical_location": result.get("ground_truth", {}).get("actual_physical_location"),
                        "visibility_status": result.get("ground_truth", {}).get("visibility_status"),
                        "frame_captured_at": result.get("frame", {}).get("captured_at"),
                        "segmentation_status": predictions.get("segmentation_status"),
                        "predicted_classes": json.dumps([item["class"] for item in segments]),
                        "region_associations": json.dumps([
                            item["association"].get("primary_region_id") or item["association"]["association_status"]
                            for item in segments
                        ]),
                        "camera_read_ms": lat.get("camera_read"),
                        "preprocessing_ms": lat.get("preprocessing_board_crop"),
                        "detection_ms": lat.get("detection_pipeline_branch"),
                        "segmentation_ms": lat.get("segmentation_pipeline_branch"),
                        "postprocessing_ms": lat.get("postprocessing"),
                        "polygon_mask_filtering_ms": lat.get("polygon_mask_filtering"),
                        "overlay_rendering_ms": lat.get("overlay_rendering"),
                        "error": result.get("error"),
                    })
            print(f"TEST_ONLY session complete: {session.resolve()}")
        return 0
    finally:
        cap.release()
        if pipeline is not None:
            pipeline.close()


def render_preview(
    frame: np.ndarray,
    polygon_config: Any,
    metadata: Any,
    state: dict[str, Any],
    busy: bool,
    error: str | None,
    *,
    frame_stats: dict[str, Any] | None = None,
) -> np.ndarray:
    from scripts.validate_polygon_vision import render_reference_overlay
    if state.get("roi_overlay", True):
        result = render_reference_overlay(frame.copy(), polygon_config)
    else:
        result = frame.copy()
    height, width = result.shape[:2]

    if state.get("grid", False):
        grid_color = (190, 190, 190)
        for column in range(1, 4):
            x = width * column // 4
            cv2.line(result, (x, 0), (x, height - 1), grid_color, 1, cv2.LINE_AA)
        for row in range(1, 4):
            y = height * row // 4
            cv2.line(result, (0, y), (width - 1, y), grid_color, 1, cv2.LINE_AA)

    if state.get("margins", True):
        margin_x, margin_y = round(width * 0.05), round(height * 0.05)
        cv2.rectangle(
            result,
            (margin_x, margin_y),
            (width - margin_x, height - margin_y),
            (230, 230, 230),
            1,
            cv2.LINE_AA,
        )

    stats = frame_stats or {}
    warning = error or ("ALL-BLACK CAMERA FRAME - CAPTURE DISABLED" if stats.get("all_black") else None)
    if warning:
        banner_height = 48
        cv2.rectangle(result, (0, result.shape[0] - banner_height), (result.shape[1], result.shape[0]), (0, 0, 150), -1)
        cv2.putText(result, warning[:130], (16, result.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.64, (255, 255, 255), 2, cv2.LINE_AA)
    return result


def render_control_panel(
    camera: dict[str, Any],
    metadata: Any,
    state: dict[str, Any],
    busy: bool,
    error: str | None,
    frame_stats: dict[str, Any] | None,
    read_count: int,
    read_failures: int,
    latencies: list[float],
    read_timestamps: list[datetime],
    args: Any,
    *,
    reader_stopped: bool = False,
) -> np.ndarray:
    """Render a clickable operator panel with live truth and readiness feedback."""
    panel = np.full((CONTROL_PANEL_SIZE[1], CONTROL_PANEL_SIZE[0], 3), 28, dtype=np.uint8)
    stats = frame_stats or {}
    measured_fps = (
        (len(read_timestamps) - 1)
        / max((read_timestamps[-1] - read_timestamps[0]).total_seconds(), 1e-6)
        if len(read_timestamps) > 1 else 0.0
    )
    scenario = SCENARIOS[state["scenario_key"]]
    frame_line = (
        f"{metadata.width}x{metadata.height} | age "
        f"{max(0.0, (datetime.now(timezone.utc) - metadata.timestamp).total_seconds()):.2f}s | "
        f"{stats.get('dtype', 'unknown')}"
        if metadata is not None else "Waiting for the first successful camera read"
    )
    stats_line = (
        f"mean luma {stats['mean_luma']:.2f} | gray variance {stats['gray_variance']:.2f}"
        if "mean_luma" in stats else "brightness and variance pending"
    )
    actual_resolution = camera.get("actual_resolution_first_frame") or camera.get("resolution_reported_after_setup")
    actual_resolution_text = f"{actual_resolution[0]}x{actual_resolution[1]}" if actual_resolution else "unknown"
    actual_fourcc = camera.get("actual_fourcc_first_frame") or camera.get("fourcc_actual_reported") or "unknown"
    device_fps = camera.get("device_reported_fps")
    device_fps_text = f"{device_fps:.2f}" if device_fps is not None and device_fps > 0 else "unavailable"
    expected_resolution = (int(getattr(args, "width", 1920)), int(getattr(args, "height", 1080)))
    max_age = float(getattr(args, "max_frame_age_seconds", 1.0))
    missing = capture_missing_requirements(
        state, metadata, frame_stats, expected_resolution, max_age,
        reader_stopped=reader_stopped,
    )
    ready = not busy and not missing
    if busy:
        readiness = "INFERENCE RUNNING - CAPTURE DISABLED"
    elif ready:
        readiness = "READY TO CAPTURE"
    else:
        readiness = "INCOMPLETE - Missing: " + "; ".join(missing)
    if state.get("last_status", "").startswith("CAPTURE BLOCKED:"):
        readiness = state["last_status"]

    def put(text: str, x: int, y: int, color: tuple[int, int, int], scale: float = 0.48, thickness: int = 1) -> None:
        cv2.putText(panel, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)

    put("CITYRESPONDER PHASE B2 - TEST_ONLY", 18, 26, (100, 220, 255), 0.66, 2)
    put(f"Camera {camera['index']} | {camera['backend_actual']} | {actual_fourcc} | {actual_resolution_text}", 18, 50, (240, 240, 240))
    put(f"Device FPS {device_fps_text} | preview FPS {measured_fps:.2f} | reads {read_count} | failures {read_failures}", 18, 72, (240, 240, 240))
    latency_line = (
        f"Read latency mean {float(np.mean(latencies)):.2f}ms | p95 {float(np.percentile(latencies, 95)):.2f}ms"
        if latencies else "Read latency pending"
    )
    put(latency_line, 18, 94, (220, 220, 220))
    put(f"Frame {frame_line} | Image {stats_line}"[:145], 18, 116, (220, 220, 220), 0.43)
    put("SCENARIO", 18, 155, (185, 220, 255), 0.48, 1)
    put("GROUND TRUTH", 18, 271, (185, 220, 255), 0.48, 1)
    put("LOCATION", 18, 349, (185, 220, 255), 0.48, 1)
    put("VISIBILITY", 18, 469, (185, 220, 255), 0.48, 1)

    for button in CONTROL_BUTTONS:
        kind, value = button["kind"], button["value"]
        left, top, width, height = button["rect"]
        selected = (
            (kind == "scenario" and state.get("scenario_selected") and state["scenario_key"] == value)
            or (kind == "truth" and state.get("actual_prop_type") == value)
            or (kind == "location" and state.get("actual_location") == value)
            or (kind == "visibility" and state.get("visible") is value)
        )
        if kind == "capture":
            fill = (35, 125, 55) if ready else (65, 65, 65)
            border = (80, 220, 120) if ready else (100, 100, 100)
        elif kind == "exit":
            fill, border = (70, 55, 115), (155, 120, 220)
        elif selected:
            fill, border = (55, 105, 45), (120, 220, 100)
        else:
            fill, border = (54, 54, 54), (110, 110, 110)
        cv2.rectangle(panel, (left, top), (left + width, top + height), fill, -1)
        cv2.rectangle(panel, (left, top), (left + width, top + height), border, 1)
        label_scale = 0.42 if len(button["label"]) > 17 else 0.48
        (text_width, text_height), _baseline = cv2.getTextSize(
            button["label"], cv2.FONT_HERSHEY_SIMPLEX, label_scale, 1
        )
        tx = left + max(6, (width - text_width) // 2)
        ty = top + (height + text_height) // 2 - 1
        put(button["label"], tx, ty, (245, 245, 245), label_scale)

    visible_text = "YES" if state.get("visible") is True else "NO" if state.get("visible") is False else "NOT_RECORDED"
    put(f"Scenario: {scenario['id']} - {scenario['name']}", 18, 552, (185, 255, 185), 0.50)
    put(f"Ground Truth: {state.get('actual_prop_type', 'NOT_RECORDED')}", 18, 576, (245, 245, 245), 0.50)
    put(f"Location: {state.get('actual_location', 'NOT_RECORDED')}", 405, 576, (245, 245, 245), 0.50)
    put(f"Visible: {visible_text}", 18, 600, (245, 245, 245), 0.50)
    status_lines = textwrap.wrap(readiness, width=145, subsequent_indent="  ") or [readiness]
    for index, status_line in enumerate(status_lines[:3]):
        put(
            status_line, 18, 624 + index * 19,
            (130, 255, 150) if ready else (100, 190, 255), 0.39, 1,
        )
    status_end_y = 624 + min(len(status_lines), 3) * 19
    if ready:
        put(f"Last action: {state.get('last_status', '')}"[:145], 18, status_end_y, (255, 230, 140), 0.38)
    put("Keys: 0-7 scenarios | R/P/N/U truth | A/S/D/F/J/K/L/I/E locations | Y/H visibility | Space capture | Q/Esc exit", 18, 676, (205, 205, 205), 0.35)
    put("G grid | M margins | O read-only ROI | No detection is not evidence a road is clear.", 18, 757, (130, 230, 255), 0.39)
    if error:
        put(f"CAMERA WARNING: {error[:115]}", 580, 26, (80, 100, 255), 0.43)
    if stats.get("all_black"):
        put("WARNING: BLACK FRAME", 850, 50, (80, 100, 255), 0.45, 2)
    return panel
