"""Measure fixed-camera frame stability without recording frames."""

from __future__ import annotations

import argparse
import json
import time

import cv2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.index, cv2.CAP_ANY)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    opened = bool(capture.isOpened())
    dimensions: list[tuple[int, int]] = []
    valid_frames = 0
    failed_reads = 0
    started_at = time.perf_counter()
    if opened:
        while time.perf_counter() - started_at < args.seconds:
            ok, frame = capture.read()
            if ok and frame is not None:
                valid_frames += 1
                dimensions.append((int(frame.shape[1]), int(frame.shape[0])))
            else:
                failed_reads += 1
    elapsed = time.perf_counter() - started_at if opened else 0.0
    reported_fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    print(
        json.dumps(
            {
                "index": args.index,
                "requested": [args.width, args.height],
                "opened": opened,
                "elapsed_seconds": round(elapsed, 3),
                "valid_frames": valid_frames,
                "failed_reads": failed_reads,
                "unique_dimensions": sorted(set(dimensions)),
                "measured_fps": round(valid_frames / elapsed, 3) if elapsed else None,
                "reported_fps": reported_fps,
                "disconnects": failed_reads > 0,
            },
            indent=2,
        )
    )
    return 0 if opened and valid_frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
