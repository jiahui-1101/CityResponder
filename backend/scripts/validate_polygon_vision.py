"""Validate the opt-in polygon ROI adapter without publishing vision evidence.

Modes:
  render   Draw the proposed RAW_CAMERA geometry on the saved reference image.
  offline  Run the integrated detector/segmenter on that reference image.
  live     Run the integrated pipeline locally, or capture-only with --capture-only.
  test     Operator-driven, single-frame live road-prop validation (TEST_ONLY).

Every pipeline call uses publish=False. This utility never starts MQTT, dispatch,
database, or actuator services.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

import cv2
import numpy as np

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_DRAFT = (
    PROJECT_ROOT
    / "reports"
    / "debug"
    / "camera_alignment"
    / "roi_calibration_phase_a_draft.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "reports" / "debug" / "camera_alignment" / "phase_a_validation"
)
DEFAULT_TEST_OUTPUT = PROJECT_ROOT / "reports" / "debug" / "road_vision_tests"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("render", "offline", "live", "test"), default="render")
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--image", type=Path, help="RAW_CAMERA reference image for render/offline")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--camera-index", type=int, help="Overrides the configured index for this local run")
    parser.add_argument("--backend", help="For example DSHOW, MSMF, or CAP_ANY")
    parser.add_argument("--fourcc", help="Four-character camera format, for example MJPG")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--duration-seconds", type=float, default=20.0)
    parser.add_argument("--test-confidence-floor", type=float, default=0.05,
                        help="In-memory TEST_ONLY model confidence floor; does not change production settings")
    parser.add_argument("--review-confidence-threshold", type=float, default=0.25,
                        help="Confidence review label for TEST_ONLY predictions")
    parser.add_argument("--max-frame-age-seconds", type=float, default=1.0,
                        help="Reject a pinned camera frame older than this value")
    parser.add_argument("--read-failure-limit", type=int, default=30,
                        help="Stop camera retry loop after this many consecutive failed reads")
    parser.add_argument("--capture-only", action="store_true", help="Skip model loading/inference in live mode")
    parser.add_argument("--show", action="store_true", help="Show a 1280x720 max, aspect-preserving local window")
    return parser.parse_args()


def _read_raw_reference(draft: dict[str, Any], image_path: Path | None) -> tuple[np.ndarray, Path]:
    if image_path is not None:
        selected = image_path.resolve()
    else:
        selected = Path(draft["reference_image"]).expanduser()
        if not selected.is_absolute():
            selected = (PROJECT_ROOT / selected).resolve()
    image = cv2.imread(str(selected), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to load RAW_CAMERA reference image: {selected}")
    expected = draft["image_size"]
    if image.shape[1] != expected["width"] or image.shape[0] != expected["height"]:
        raise ValueError(
            f"Reference image is {image.shape[1]}x{image.shape[0]}, draft expects "
            f"{expected['width']}x{expected['height']} RAW_CAMERA"
        )
    return image, selected


def _draw_labeled_polygon(
    image: np.ndarray,
    points: np.ndarray,
    label: str,
    color: tuple[int, int, int],
    *,
    anchor: tuple[int, int] | None = None,
    thickness: int = 3,
) -> None:
    cv2.polylines(image, [points], True, color, thickness, cv2.LINE_AA)
    if anchor is None:
        anchor = (int(np.mean(points[:, 0])), int(np.mean(points[:, 1])))
    x, y = anchor
    cv2.putText(
        image,
        label,
        (x, max(24, y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (10, 10, 10),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        label,
        (x, max(24, y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        color,
        2,
        cv2.LINE_AA,
    )


def render_reference_overlay(
    raw_image: np.ndarray,
    polygon_config: Any,
) -> np.ndarray:
    """Render review geometry in native RAW_CAMERA coordinates."""

    annotated = raw_image.copy()
    overlay = annotated.copy()
    for item in polygon_config.exclusions:
        points = np.rint(item.raw_points).astype(np.int32)
        cv2.fillPoly(overlay, [points], (125, 125, 125))
    cv2.addWeighted(overlay, 0.26, annotated, 0.74, 0, annotated)

    crop = polygon_config.crop
    cv2.rectangle(
        annotated,
        (crop.x, crop.y),
        (crop.x + crop.width - 1, crop.y + crop.height - 1),
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        annotated,
        f"CROP {crop.x},{crop.y}  |  {crop.width}x{crop.height}",
        (940, 150),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        annotated,
        f"CROP {crop.x},{crop.y}  |  {crop.width}x{crop.height}",
        (940, 150),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    road_colors = ((255, 160, 0), (255, 0, 255), (0, 165, 255))
    for index, region in enumerate(polygon_config.road_segments):
        _draw_labeled_polygon(
            annotated,
            np.rint(region.raw_points).astype(np.int32),
            region.label,
            road_colors[index % len(road_colors)],
        )

    _draw_labeled_polygon(
        annotated,
        np.rint(polygon_config.building.raw_points).astype(np.int32),
        polygon_config.building.label,
        (0, 210, 110),
        anchor=tuple(np.rint(polygon_config.building.raw_points[0]).astype(np.int32)),
    )
    _draw_labeled_polygon(
        annotated,
        np.rint(polygon_config.hazard.raw_points).astype(np.int32),
        polygon_config.hazard.label,
        (0, 220, 255),
        anchor=tuple(np.rint(polygon_config.hazard.raw_points[0]).astype(np.int32)),
    )

    for index, raw_points in enumerate(polygon_config.junction_raw_regions, start=1):
        junction = np.rint(raw_points).astype(np.int32)
        _draw_labeled_polygon(
            annotated,
            junction,
            f"J{index}",
            (40, 230, 255),
            thickness=3,
        )

    for item in polygon_config.exclusions:
        points = np.rint(item.raw_points).astype(np.int32)
        _draw_labeled_polygon(
            annotated,
            points,
            item.label,
            (220, 220, 220),
            anchor=(1550, 940) if "RIGHT" in item.label.upper() else (36, 840),
            thickness=2,
        )

    header = "RAW_CAMERA  |  1920 x 1080  |  DRAFT; S1/S2/S3 UNMAPPED; S2 owns junction pixels"
    cv2.putText(annotated, header, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(annotated, header, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2, cv2.LINE_AA)
    return annotated


def _display_sized(frame: np.ndarray) -> np.ndarray:
    max_width, max_height = 1280, 720
    height, width = frame.shape[:2]
    scale = min(max_width / width, max_height / height, 1.0)
    target = (round(width * scale), round(height * scale))
    return cv2.resize(frame, target, interpolation=cv2.INTER_AREA) if scale < 1 else frame


def _frame_stats(frame: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return {
        "resolution": [int(frame.shape[1]), int(frame.shape[0])],
        "dtype": str(frame.dtype),
        "mean_luma": round(float(np.mean(gray)), 3),
        "gray_variance": round(float(np.var(gray)), 3),
    }


def _run_local_pipeline(args: argparse.Namespace, draft_path: Path, image_path: Path | None) -> int:
    from app.vision.config import get_vision_config
    from app.vision.pipeline import IntegratedVisionPipeline

    base = get_vision_config()
    config = replace(
        base,
        source=str(image_path) if image_path is not None else "CAMERA",
        camera_index=base.camera_index if args.camera_index is None else args.camera_index,
        capture_backend=base.capture_backend if args.backend is None else args.backend,
        capture_fourcc=base.capture_fourcc if args.fourcc is None else args.fourcc,
        frame_width=args.width,
        frame_height=args.height,
        polygon_roi_enabled=True,
        polygon_roi_config_path=str(draft_path),
    )
    pipeline = IntegratedVisionPipeline(config=config)
    try:
        if args.mode == "offline":
            processed = pipeline.process_one(publish=False)
            encoded, metadata = pipeline.render_annotated_frame(processed)
            target = args.output_dir / "phase_a_offline_inference_annotated.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            print(json.dumps({
                "mode": "OFFLINE_INFERENCE_ONLY_NO_PUBLISH_NO_DISPATCH_NO_ACTUATORS",
                "source_image": str(image_path),
                "annotated_frame": str(target.resolve()),
                "frame_stats": _frame_stats(processed.board_frame),
                "detection_count_in_building": len(processed.detection_result.detections),
                "person_in_hazard": processed.detection_result.person_in_hazard,
                "road_regions": [
                    {"name": item.road_roi_name, "occupancy": item.occupancy_ratio,
                     "occupied_pixels": item.occupied_pixels}
                    for item in processed.road_evidence
                ],
                "annotation_metadata": metadata,
            }, indent=2))
            return 0

        started = time.monotonic()
        frames = 0
        failures = 0
        capture_latencies_ms: list[float] = []
        last_processed = None
        duration = max(1.0, args.duration_seconds)
        try:
            while time.monotonic() - started < duration:
                try:
                    last_processed = pipeline.process_one(publish=False)
                except Exception as exc:
                    failures += 1
                    print(f"local live frame failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    break
                frames += 1
                capture_latencies_ms.append(last_processed.result.capture_duration_ms)
                if args.show:
                    encoded, _metadata = pipeline.render_annotated_frame(last_processed)
                    display = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
                    cv2.imshow("CityResponder Phase A Local Vision", _display_sized(display))
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break
        finally:
            if args.show:
                cv2.destroyAllWindows()
        elapsed = max(time.monotonic() - started, 1e-6)
        summary: dict[str, Any] = {
            "mode": "LOCAL_LIVE_NO_PUBLISH_NO_DISPATCH_NO_ACTUATORS",
            "configured_camera_index": config.camera_index,
            "backend_requested": config.capture_backend or "CAP_ANY",
            "fourcc_requested": config.capture_fourcc or "driver default",
            "resolution_requested": [config.frame_width, config.frame_height],
            "frames_processed": frames,
            "read_or_pipeline_failures": failures,
            "elapsed_seconds": round(elapsed, 3),
            "measured_pipeline_fps": round(frames / elapsed, 3),
            "capture_read_latency_ms_mean": round(float(np.mean(capture_latencies_ms)), 3)
            if capture_latencies_ms else None,
            "capture_read_latency_ms_p95": round(float(np.percentile(capture_latencies_ms, 95)), 3)
            if capture_latencies_ms else None,
            "gui_shown": bool(args.show),
        }
        if last_processed is not None:
            summary["frame_stats"] = _frame_stats(last_processed.board_frame)
            summary["person_in_hazard"] = last_processed.detection_result.person_in_hazard
            summary["road_regions"] = [
                {"name": item.road_roi_name, "occupancy": item.occupancy_ratio}
                for item in last_processed.road_evidence
            ]
            encoded, _metadata = pipeline.render_annotated_frame(last_processed)
            target = args.output_dir / "phase_a_live_annotated.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            summary["annotated_frame"] = str(target.resolve())
        print(json.dumps(summary, indent=2))
        return 0 if frames > 0 else 1
    finally:
        pipeline.close()


def _run_capture_only_live(args: argparse.Namespace, polygon_config: Any) -> int:
    from app.vision.config import get_vision_config
    from app.vision.capture import VisionCaptureService

    base = get_vision_config()
    config = replace(
        base,
        source="CAMERA",
        camera_index=base.camera_index if args.camera_index is None else args.camera_index,
        capture_backend=base.capture_backend if args.backend is None else args.backend,
        capture_fourcc=base.capture_fourcc if args.fourcc is None else args.fourcc,
        frame_width=args.width,
        frame_height=args.height,
        polygon_roi_enabled=True,
        polygon_roi_config_path=str(polygon_config.path),
    )
    capture = VisionCaptureService(config=config)
    started = time.monotonic()
    frames = failures = 0
    capture_latencies_ms: list[float] = []
    last = None
    try:
        duration = max(1.0, args.duration_seconds)
        while time.monotonic() - started < duration:
            try:
                read_started = time.perf_counter()
                captured = capture.capture_one()
                capture_latencies_ms.append((time.perf_counter() - read_started) * 1000)
            except Exception as exc:
                failures += 1
                print(f"local live capture failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                break
            if captured is None:
                failures += 1
                break
            frames += 1
            last = captured.frame
            if args.show:
                annotated = render_reference_overlay(last, polygon_config)
                if not np.any(last):
                    cv2.putText(
                        annotated,
                        "WARNING: CAMERA FRAME IS ALL BLACK",
                        (24, 52),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 0, 255),
                        3,
                        cv2.LINE_AA,
                    )
                cv2.imshow("CityResponder Phase A Camera ROI (capture only)", _display_sized(annotated))
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
        elapsed = max(time.monotonic() - started, 1e-6)
        summary: dict[str, Any] = {
            "mode": "LOCAL_CAMERA_CAPTURE_ONLY_NO_INFERENCE_NO_PUBLISH_NO_DISPATCH_NO_ACTUATORS",
            "configured_camera_index": config.camera_index,
            "backend_requested": config.capture_backend or "CAP_ANY",
            "fourcc_requested": config.capture_fourcc or "driver default",
            "resolution_requested": [config.frame_width, config.frame_height],
            "frames_read": frames,
            "read_failures": failures,
            "elapsed_seconds": round(elapsed, 3),
            "measured_capture_fps": round(frames / elapsed, 3),
            "capture_read_latency_ms_mean": round(float(np.mean(capture_latencies_ms)), 3)
            if capture_latencies_ms else None,
            "capture_read_latency_ms_p95": round(float(np.percentile(capture_latencies_ms, 95)), 3)
            if capture_latencies_ms else None,
            "gui_shown": bool(args.show),
        }
        if last is not None:
            summary["frame_stats"] = _frame_stats(last)
            if summary["frame_stats"]["mean_luma"] == 0 and summary["frame_stats"]["gray_variance"] == 0:
                summary["warning"] = "Last camera frame was all black; no annotated still was saved"
            else:
                annotated = render_reference_overlay(last, polygon_config)
                target = args.output_dir / "phase_a_live_capture_annotated.jpg"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(target), annotated):
                    raise OSError(f"Unable to write annotated capture: {target}")
                summary["annotated_frame"] = str(target.resolve())
        print(json.dumps(summary, indent=2))
        return 0 if frames > 0 else 1
    finally:
        capture.close()
        if args.show:
            cv2.destroyAllWindows()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    try:
        from app.vision.polygon_roi import load_polygon_roi_config

        draft_path = args.draft.resolve()
        polygon_config = load_polygon_roi_config(
            draft_path,
            expected_resolution=(args.width, args.height),
        )
        if args.mode == "test" and args.output_dir == DEFAULT_OUTPUT:
            args.output_dir = DEFAULT_TEST_OUTPUT
        args.output_dir = args.output_dir.resolve()
        if args.mode == "test":
            from scripts.road_vision_scenario_test import run_operator_test

            test_output_root = DEFAULT_TEST_OUTPUT.resolve()
            if not args.output_dir.is_relative_to(test_output_root):
                raise ValueError(
                    "TEST_ONLY outputs must stay under reports/debug/road_vision_tests; "
                    f"requested {args.output_dir}"
                )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            return run_operator_test(args, polygon_config, args.output_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        image_path = None
        if args.mode in {"render", "offline"}:
            with draft_path.open("r", encoding="utf-8") as stream:
                draft = json.load(stream)
            raw_image, image_path = _read_raw_reference(draft, args.image)
            annotated = render_reference_overlay(raw_image, polygon_config)
            annotated_path = args.output_dir / "phase_a_polygon_roi_annotated.jpg"
            if not cv2.imwrite(str(annotated_path), annotated):
                raise OSError(f"Unable to write reference annotation: {annotated_path}")
            if args.mode == "render":
                print(json.dumps({
                    "mode": "STATIC_REFERENCE_ROI_REVIEW_NO_INFERENCE",
                    "draft": str(draft_path),
                    "reference_image": str(image_path),
                    "annotated_image": str(annotated_path),
                    "draft_status": polygon_config.status,
                    "coordinate_system": "RAW_CAMERA",
                    "crop": {
                        "x": polygon_config.crop.x,
                        "y": polygon_config.crop.y,
                        "width": polygon_config.crop.width,
                        "height": polygon_config.crop.height,
                    },
                    "road_regions": [region.label for region in polygon_config.road_segments],
                    "junction_owner": polygon_config.junction_owner_region_id,
                    "road_to_edge_mappings": [],
                }, indent=2))
                return 0

        if args.mode == "live" and args.capture_only:
            return _run_capture_only_live(args, polygon_config)
        return _run_local_pipeline(args, draft_path, image_path)
    except Exception as exc:
        print(f"Phase A validation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
