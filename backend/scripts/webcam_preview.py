"""Show a safe, non-recording live preview of a webcam.

This utility is intentionally separate from inference and dataset capture. It
only opens one camera, displays the current stream, and exits on Q or Escape.
"""

from __future__ import annotations

import argparse
import time

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True, help="OpenCV camera index")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capture = cv2.VideoCapture(args.index, cv2.CAP_ANY)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not capture.isOpened():
        print(f"Unable to open camera index {args.index}")
        return 1

    window_name = "CityResponder Webcam Preview"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    started_at = time.perf_counter()
    valid_frames = 0
    failed_reads = 0
    last_report = started_at
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                failed_reads += 1
                key = cv2.waitKey(10) & 0xFF
                if key in (ord("q"), 27):
                    break
                continue

            valid_frames += 1
            height, width = frame.shape[:2]
            elapsed = max(time.perf_counter() - started_at, 1e-6)
            measured_fps = valid_frames / elapsed
            overlay = (
                f"index={args.index}  {width}x{height}  "
                f"FPS={measured_fps:.1f}  Q/Esc=quit"
            )
            cv2.putText(
                frame,
                overlay,
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, frame)

            now = time.perf_counter()
            if now - last_report >= 5.0:
                print(
                    f"preview: resolution={width}x{height} "
                    f"valid_frames={valid_frames} failed_reads={failed_reads} "
                    f"measured_fps={measured_fps:.2f}",
                    flush=True,
                )
                last_report = now

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    elapsed = max(time.perf_counter() - started_at, 1e-6)
    print(
        f"preview stopped: valid_frames={valid_frames} "
        f"failed_reads={failed_reads} measured_fps={valid_frames / elapsed:.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
