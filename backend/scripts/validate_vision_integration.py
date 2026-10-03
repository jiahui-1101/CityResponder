"""Real shared-camera smoke test and benchmark for the frozen vision models."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from time import perf_counter, sleep

from app.mqtt.client import mqtt_client
from app.vision.pipeline import IntegratedVisionPipeline, VisionIntegrationError


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean_ms": None, "median_ms": None, "p95_ms": None}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[p95_index],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../reports/validation/vision/vision_integration_benchmark.json"),
    )
    parser.add_argument("--publish-one", action="store_true")
    args = parser.parse_args()
    if args.frames < 100:
        raise ValueError("integration benchmark requires at least 100 valid frames")

    pipeline = IntegratedVisionPipeline()
    mqtt_ready = False
    if args.publish_one:
        mqtt_client.start()
        mqtt_ready = mqtt_client.wait_until_connected(5.0)
        if not mqtt_ready:
            raise RuntimeError("MQTT broker unavailable; no vision evidence was published")

    failures: list[str] = []
    totals: list[float] = []
    captures: list[float] = []
    crops: list[float] = []
    detections: list[float] = []
    segmentations: list[float] = []
    postprocessing: list[float] = []
    serialization: list[float] = []
    class_counts: Counter[str] = Counter()
    normal_frames = 0
    published = False
    actual_resolution: tuple[int, int] | None = None

    try:
        for _ in range(10):
            pipeline.capture.capture_one()
        # Load and warm both frozen models before timing steady-state integration.
        # This frame is real but is excluded from the requested 100-frame sample.
        pipeline.process_one(publish=False)
        benchmark_started = perf_counter()
        while len(totals) < args.frames and len(failures) < 20:
            try:
                processed = pipeline.process_one(publish=False)
            except VisionIntegrationError as exc:
                failures.append(str(exc))
                continue
            result = processed.result
            actual_resolution = (result.raw_frame.width, result.raw_frame.height)
            serialized_at = perf_counter()
            result.model_dump_json()
            serialization.append((perf_counter() - serialized_at) * 1000)
            totals.append(result.total_duration_ms + serialization[-1])
            captures.append(result.capture_duration_ms)
            crops.append(result.crop_duration_ms)
            detections.append(result.detection_duration_ms)
            segmentations.append(result.segmentation_duration_ms)
            postprocessing.append(result.postprocessing_duration_ms)
            for item in result.detections:
                class_counts[item.class_name.lower()] += 1
            for item in result.segmentations:
                class_counts[item.class_name.lower()] += 1
            if not result.detections and not result.segmentations:
                normal_frames += 1
            if args.publish_one and not published:
                pipeline.publisher.publish_detection(processed.detection_result)
                for evidence in processed.road_evidence:
                    pipeline.publisher.publish_road(evidence)
                published = True
        elapsed = perf_counter() - benchmark_started
        if len(totals) < args.frames:
            raise RuntimeError(
                f"Only {len(totals)} valid frames were processed; failures={len(failures)}"
            )
        if published:
            sleep(1.0)
    finally:
        pipeline.close()
        if args.publish_one:
            mqtt_client.stop()

    report = {
        "prototype_scope": "controlled tabletop integration",
        "frames": len(totals),
        "failed_reads_or_frames": len(failures),
        "failures": failures,
        "actual_native_resolution": (
            f"{actual_resolution[0]}x{actual_resolution[1]}" if actual_resolution else None
        ),
        "raw_board_crop": {"x": 340, "y": 80, "width": 1080, "height": 840},
        "elapsed_seconds": elapsed,
        "average_end_to_end_fps": len(totals) / elapsed,
        "end_to_end": _summary(totals),
        "capture": _summary(captures),
        "crop": _summary(crops),
        "detection": _summary(detections),
        "segmentation": _summary(segmentations),
        "postprocessing": _summary(postprocessing),
        "serialization": _summary(serialization),
        "observed_class_instances": dict(sorted(class_counts.items())),
        "normal_clear_frames": normal_frames,
        "normal_scene_observed": normal_frames > 0,
        "fire_or_person_observed": bool(class_counts["fire"] or class_counts["person"]),
        "road_obstacle_or_pothole_observed": bool(
            class_counts["road_obstacle"] or class_counts["pothole"]
        ),
        "mqtt_publish_requested": args.publish_one,
        "mqtt_connected": mqtt_ready,
        "mqtt_evidence_published": published,
        "continuous_video_stored": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
