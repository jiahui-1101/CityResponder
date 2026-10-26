"""Show a non-recording, full-frame camera preview for physical alignment.

This utility opens one camera directly through OpenCV. It does not import the
vision pipeline, load inference models, publish events, or change ROI settings.
Snapshots are written only when the user presses S.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import platform
import sys
from threading import Event, Lock, Thread
import time
from typing import Any

import cv2
import numpy as np


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("cityresponder.camera_alignment")
WINDOW_NAME = "CityResponder - Camera Alignment"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = PROJECT_ROOT / "reports" / "debug" / "camera_alignment"
BACKENDS = {
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "any": cv2.CAP_ANY,
}


@dataclass
class CameraSession:
    capture: cv2.VideoCapture
    first_frame: Any
    backend_name: str
    fourcc: str
    reported_fps: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, help="OpenCV camera index to preview")
    parser.add_argument(
        "--camera-label",
        default="Camera",
        help="Friendly label shown in the preview and snapshot metadata",
    )
    parser.add_argument("--width", type=int, default=1920, help="Requested capture width")
    parser.add_argument("--height", type=int, default=1080, help="Requested capture height")
    parser.add_argument(
        "--backend",
        choices=("auto", "dshow", "msmf", "any"),
        default="auto",
        help="Preferred capture backend; auto prefers DirectShow on Windows",
    )
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="Probe camera indices and print those that return a frame",
    )
    parser.add_argument(
        "--max-index",
        type=int,
        default=5,
        help="Highest index to probe with --list-cameras (inclusive)",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help="Directory for snapshots saved by pressing S",
    )
    parser.add_argument(
        "--display-width",
        type=int,
        default=1280,
        help="Initial display canvas width; capture remains at native size",
    )
    parser.add_argument(
        "--display-height",
        type=int,
        default=720,
        help="Initial display canvas height; capture remains at native size",
    )
    return parser.parse_args()


def backend_order(preferred: str) -> list[tuple[str, int]]:
    if preferred == "auto":
        names = ["dshow", "msmf", "any"] if platform.system() == "Windows" else ["any"]
    else:
        names = [preferred]
    return [(name, BACKENDS[name]) for name in names]


def decode_fourcc(value: float) -> str:
    """Decode OpenCV's packed FOURCC value into its four printable characters."""

    code = int(round(value))
    characters = [chr((code >> (8 * index)) & 0xFF) for index in range(4)]
    text = "".join(characters).rstrip("\x00")
    if not text or any(ord(character) < 32 or ord(character) > 126 for character in text):
        return f"unknown (0x{code:08x})"
    return text


def open_camera(index: int, width: int, height: int, preferred: str) -> CameraSession:
    failures: list[str] = []
    for backend_name, backend_id in backend_order(preferred):
        capture = cv2.VideoCapture(index, backend_id)
        if not capture.isOpened():
            failures.append(f"{backend_name}: did not open")
            capture.release()
            continue

        # Match the known-good standalone test: request MJPG before the size.
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, frame = capture.read()
        if ok and frame is not None:
            actual_fourcc = decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
            reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
            try:
                actual_backend = capture.getBackendName().upper()
            except cv2.error:
                actual_backend = backend_name.upper()
            return CameraSession(
                capture=capture,
                first_frame=frame,
                backend_name=actual_backend,
                fourcc=actual_fourcc,
                reported_fps=reported_fps,
            )

        failures.append(f"{backend_name}: opened but returned no frame")
        capture.release()

    details = "; ".join(failures) or "no capture backends available"
    raise RuntimeError(f"Unable to read from camera index {index} ({details})")


def list_cameras(args: argparse.Namespace) -> int:
    print(
        f"Probing OpenCV indices 0..{args.max_index} at requested "
        f"{args.width}x{args.height} using {args.backend} backend preference."
    )
    found = 0
    for index in range(max(0, args.max_index) + 1):
        try:
            session = open_camera(index, args.width, args.height, args.backend)
        except RuntimeError:
            print(f"index={index}: no readable camera")
            continue
        try:
            height, width = session.first_frame.shape[:2]
            fps = session.reported_fps if session.reported_fps > 0 else None
            print(
                f"index={index}: readable via {session.backend_name}, "
                f"actual={width}x{height}, fourcc={session.fourcc}, "
                f"device_fps={fps if fps is not None else 'unreported'}"
            )
            found += 1
        finally:
            session.capture.release()
    if not found:
        print("No readable camera indices found.")
        return 1
    print("Choose an index explicitly and confirm its live image before physical adjustment.")
    return 0


def configured_roi_rectangles() -> tuple[list[tuple[str, int, int, int, int, tuple[int, int, int]]], str | None]:
    """Read current configured ROIs without validation, writes, or inference."""

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    try:
        from app.vision.config import get_vision_config
        from app.vision.roi import get_configured_rois

        rois = get_configured_rois(get_vision_config())
    except Exception as exc:  # ROI display is optional; preview remains usable.
        return [], f"ROI overlay unavailable: {exc}"

    colors = {
        "board": (0, 220, 255),
        "building_a": (255, 220, 0),
        "road": (0, 230, 80),
        "hazard_zone": (255, 0, 220),
    }
    rectangles: list[tuple[str, int, int, int, int, tuple[int, int, int]]] = []
    board_rois = rois.get("board", [])
    for roi in board_rois:
        rectangles.append(
            (
                f"board crop: {roi.name} (raw)",
                roi.x,
                roi.y,
                roi.width,
                roi.height,
                colors["board"],
            )
        )

    # In the production pipeline, building/road/hazard ROIs are expressed in
    # the board-crop coordinate system. Offset them back into raw-frame pixels
    # solely for this read-only visualization.
    board_x = board_rois[0].x if board_rois else 0
    board_y = board_rois[0].y if board_rois else 0
    suffix = " (board coords)" if board_rois else " (unoffset; no board crop)"
    for group in ("building_a", "road", "hazard_zone"):
        for roi in rois.get(group, []):
            rectangles.append(
                (
                    f"{group}: {roi.name}{suffix}",
                    roi.x + board_x,
                    roi.y + board_y,
                    roi.width,
                    roi.height,
                    colors[group],
                )
            )
    return rectangles, None


def scale_roi_rectangles(
    rectangles: list[tuple[str, int, int, int, int, tuple[int, int, int]]],
    scale_x: float,
    scale_y: float,
    offset_x: int = 0,
    offset_y: int = 0,
) -> list[tuple[str, int, int, int, int, tuple[int, int, int]]]:
    """Map read-only raw-frame ROI coordinates into the preview canvas."""

    return [
        (
            label,
            round(x * scale_x) + offset_x,
            round(y * scale_y) + offset_y,
            round(width * scale_x),
            round(height * scale_y),
            color,
        )
        for label, x, y, width, height, color in rectangles
    ]


def draw_guides(
    frame: Any,
    *,
    grid_enabled: bool,
    margins_enabled: bool,
    roi_enabled: bool,
    roi_rectangles: list[tuple[str, int, int, int, int, tuple[int, int, int]]],
    index: int,
    camera_label: str,
    backend_name: str,
    requested: tuple[int, int],
    measured_fps: float,
    mean_luma: float,
    pixel_variance: float,
    reported_fps: float,
    roi_error: str | None,
    status_message: str | None = None,
    source_resolution: tuple[int, int] | None = None,
    copy_frame: bool = True,
) -> Any:
    """Draw guides, optionally modifying a disposable display canvas in place."""

    output = frame.copy() if copy_frame else frame
    height, width = output.shape[:2]
    center_x, center_y = width // 2, height // 2

    if grid_enabled:
        for x in (width // 3, (2 * width) // 3):
            cv2.line(output, (x, 0), (x, height - 1), (255, 180, 0), 1, cv2.LINE_AA)
        for y in (height // 3, (2 * height) // 3):
            cv2.line(output, (0, y), (width - 1, y), (255, 180, 0), 1, cv2.LINE_AA)

    # Crosshair remains visible whether or not the optional grid is enabled.
    crosshair_half = max(14, min(width, height) // 50)
    cv2.line(
        output,
        (center_x - crosshair_half, center_y),
        (center_x + crosshair_half, center_y),
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.line(
        output,
        (center_x, center_y - crosshair_half),
        (center_x, center_y + crosshair_half),
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    if margins_enabled:
        for percent, color in ((0.05, (0, 255, 0)), (0.10, (0, 170, 255))):
            x = round(width * percent)
            y = round(height * percent)
            cv2.rectangle(
                output,
                (x, y),
                (width - x - 1, height - y - 1),
                color,
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                output,
                f"{round(percent * 100)}%",
                (x + 8, min(height - 8, y + 24)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )

    if roi_enabled:
        for label, x, y, roi_width, roi_height, color in roi_rectangles:
            cv2.rectangle(
                output,
                (x, y),
                (x + roi_width, y + roi_height),
                color,
                2,
                cv2.LINE_AA,
            )
            label_y = min(max(y - 8, 22), height - 8)
            cv2.putText(
                output,
                label,
                (max(4, x + 4), label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )

    actual_width, actual_height = source_resolution or (width, height)
    reported = f"{reported_fps:.1f}" if math.isfinite(reported_fps) and reported_fps > 0 else "n/a"
    line_one = (
        f"{camera_label} | index {index} | {backend_name} | "
        f"requested {requested[0]}x{requested[1]} / actual {actual_width}x{actual_height}"
    )
    line_two = (
        f"measured {measured_fps:.1f} FPS (device {reported}) | "
        f"luma {mean_luma:.0f}/255 var {pixel_variance:.0f} | "
        f"G grid {'ON' if grid_enabled else 'OFF'} | "
        f"M margins {'ON' if margins_enabled else 'OFF'} | "
        f"O ROIs {'ON' if roi_enabled else 'OFF'} | S snapshot | Q/Esc quit"
    )
    panel_height = min(height, 68)
    cv2.rectangle(output, (0, 0), (width - 1, panel_height), (18, 18, 18), -1)
    font_scale = 0.48 if width >= 1000 else 0.40
    line_height = max(16, int(26 * font_scale / 0.58))
    cv2.putText(
        output,
        line_one,
        (12, min(panel_height - 4, line_height)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (245, 245, 245),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        line_two,
        (12, min(panel_height - 4, line_height * 2)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (0, 255, 180),
        1,
        cv2.LINE_AA,
    )
    if roi_enabled and roi_error:
        cv2.putText(
            output,
            roi_error,
            (12, min(height - 8, panel_height + 22)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    if status_message:
        cv2.putText(
            output,
            status_message,
            (12, min(height - 8, panel_height + (48 if roi_enabled and roi_error else 28))),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return output


def describe_frame(frame: Any) -> tuple[Any, float, float]:
    """Ensure an OpenCV displayable BGR8 frame and measure sampled luminance."""

    if frame is None or not hasattr(frame, "shape"):
        raise ValueError("Camera returned no image array")
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"Expected a BGR image with 3 channels; got shape {frame.shape}")
    if frame.dtype != np.uint8:
        raise ValueError(f"Expected uint8 camera pixels; got dtype {frame.dtype}")

    gray_sample = cv2.cvtColor(frame[::8, ::8], cv2.COLOR_BGR2GRAY)
    mean, stddev = cv2.meanStdDev(gray_sample)
    mean_luma = float(mean[0, 0])
    pixel_variance = float(stddev[0, 0] ** 2)
    return frame, mean_luma, pixel_variance


def is_exit_key(key: int) -> bool:
    """Recognize both letter cases and Escape from OpenCV waitKey output."""

    return key in (ord("q"), ord("Q"), 27)


def draw_capture_warning(
    frame: Any,
    message: str,
    headline: str = "CAMERA READ FAILED - showing last good frame",
) -> Any:
    """Mark the last good image, or a neutral canvas, when reads are failing."""

    if frame is None:
        warning = np.zeros((360, 640, 3), dtype=np.uint8)
    else:
        warning = frame.copy()
    height, width = warning.shape[:2]
    panel_height = min(height, 86)
    cv2.rectangle(warning, (0, 0), (width - 1, panel_height), (25, 25, 150), -1)
    cv2.putText(
        warning,
        headline,
        (14, min(32, panel_height - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        warning,
        message,
        (14, min(64, panel_height - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 230, 180),
        1,
        cv2.LINE_AA,
    )
    return warning


def fit_frame_for_display(frame: Any, target_width: int, target_height: int) -> Any:
    """Scale the full image into a letterboxed canvas, preserving aspect ratio."""

    if target_width <= 0 or target_height <= 0:
        return frame
    source_height, source_width = frame.shape[:2]
    scale = min(target_width / source_width, target_height / source_height)
    display_width = max(1, round(source_width * scale))
    display_height = max(1, round(source_height * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (display_width, display_height), interpolation=interpolation)
    if display_width == target_width and display_height == target_height:
        return resized
    canvas = np.zeros((target_height, target_width, 3), dtype=frame.dtype)
    left = (target_width - display_width) // 2
    top = (target_height - display_height) // 2
    canvas[top : top + display_height, left : left + display_width] = resized
    return canvas


def save_snapshot(
    raw_frame: Any,
    annotated_frame: Any,
    snapshot_dir: Path,
    metadata: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Save one raw frame, one full-resolution guide image, and its metadata."""

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    stem = f"camera_alignment_{timestamp}_index{metadata['camera_index']}"
    raw_path = snapshot_dir / f"{stem}_raw.jpg"
    annotated_path = snapshot_dir / f"{stem}_annotated.jpg"
    metadata_path = snapshot_dir / f"{stem}_metadata.json"
    options = [cv2.IMWRITE_JPEG_QUALITY, 95]
    if not cv2.imwrite(str(raw_path), raw_frame, options):
        raise OSError(f"Could not write raw snapshot: {raw_path}")
    if not cv2.imwrite(str(annotated_path), annotated_frame, options):
        raw_path.unlink(missing_ok=True)
        raise OSError(f"Could not write annotated snapshot: {annotated_path}")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return raw_path, annotated_path, metadata_path


@dataclass(frozen=True)
class CaptureSnapshot:
    frame: Any
    sequence: int
    successful_reads: int
    total_failures: int
    consecutive_failures: int
    last_success_time: float
    measured_fps: float
    average_read_ms: float
    last_read_ms: float


class CaptureReader:
    """Read frames off the GUI thread so a slow driver cannot freeze HighGUI."""

    def __init__(self, capture: cv2.VideoCapture, first_frame: Any) -> None:
        self.capture = capture
        self._lock = Lock()
        self._stop = Event()
        self._frame = first_frame
        self._sequence = 1
        self._successful_reads = 1
        self._total_failures = 0
        self._consecutive_failures = 0
        self._last_success_time = time.perf_counter()
        self._last_read_ms = 0.0
        self._read_times_ms: deque[float] = deque(maxlen=60)
        self._frame_times: deque[float] = deque(maxlen=60)
        self._frame_times.append(self._last_success_time)
        self._thread = Thread(target=self._run, name="cityresponder-camera-reader", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        last_failure_log = 0.0
        while not self._stop.is_set():
            started = time.perf_counter()
            error_message: str | None = None
            try:
                ok, frame = self.capture.read()
            except Exception as exc:
                ok, frame = False, None
                error_message = str(exc)
            finished = time.perf_counter()
            read_ms = (finished - started) * 1000

            with self._lock:
                self._last_read_ms = read_ms
                self._read_times_ms.append(read_ms)
                if ok and frame is not None:
                    self._frame = frame
                    self._sequence += 1
                    self._successful_reads += 1
                    self._consecutive_failures = 0
                    self._last_success_time = finished
                    self._frame_times.append(finished)
                else:
                    self._total_failures += 1
                    self._consecutive_failures += 1
                    consecutive = self._consecutive_failures

            if not ok or frame is None:
                if finished - last_failure_log >= 2.0 or last_failure_log == 0.0:
                    LOGGER.warning(
                        "camera read failed; consecutive=%d%s (retrying after 50 ms)",
                        consecutive,
                        f" error={error_message}" if error_message else "",
                    )
                    last_failure_log = finished
                self._stop.wait(0.05)

    def snapshot(self) -> CaptureSnapshot:
        now = time.perf_counter()
        with self._lock:
            frame_times = tuple(self._frame_times)
            measured_fps = (
                (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
                if len(frame_times) > 1 and frame_times[-1] > frame_times[0]
                else 0.0
            )
            if now - self._last_success_time > 2.0:
                measured_fps = 0.0
            average_read_ms = (
                sum(self._read_times_ms) / len(self._read_times_ms)
                if self._read_times_ms
                else 0.0
            )
            return CaptureSnapshot(
                frame=self._frame,
                sequence=self._sequence,
                successful_reads=self._successful_reads,
                total_failures=self._total_failures,
                consecutive_failures=self._consecutive_failures,
                last_success_time=self._last_success_time,
                measured_fps=measured_fps,
                average_read_ms=average_read_ms,
                last_read_ms=self._last_read_ms,
            )

    def stop(self) -> bool:
        """Stop reads, release the device, and report whether the reader joined."""

        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=0.25)
        self.capture.release()
        if self._thread.ident is not None:
            self._thread.join(timeout=2.0)
        return not self._thread.is_alive()


def main() -> int:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        print("Requested capture dimensions must be positive.", file=sys.stderr)
        return 2
    if args.display_width <= 0 or args.display_height <= 0:
        print("Display dimensions must be positive.", file=sys.stderr)
        return 2
    if args.list_cameras:
        return list_cameras(args)
    if args.index is None:
        print("Choose a camera explicitly with --index, or use --list-cameras first.", file=sys.stderr)
        return 2

    try:
        session = open_camera(args.index, args.width, args.height, args.backend)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    capture = session.capture
    try:
        first_frame, mean_luma, pixel_variance = describe_frame(session.first_frame)
    except ValueError as exc:
        capture.release()
        LOGGER.error("Camera index %s returned an unsupported frame: %s", args.index, exc)
        return 1

    actual_height, actual_width = first_frame.shape[:2]
    frame_shape = tuple(int(value) for value in first_frame.shape)
    LOGGER.info(
        "camera opened camera_index=%d backend=%s requested_fourcc=MJPG actual_fourcc=%s "
        "requested_resolution=%dx%d actual_resolution=%dx%d device_fps=%s "
        "frame_shape=%s dtype=%s channels=BGR",
        args.index,
        session.backend_name,
        session.fourcc,
        args.width,
        args.height,
        actual_width,
        actual_height,
        f"{session.reported_fps:.2f}" if session.reported_fps > 0 else "unreported",
        frame_shape,
        first_frame.dtype,
    )
    LOGGER.info(
        "first read success=true luma_mean=%.2f pixel_variance=%.2f",
        mean_luma,
        pixel_variance,
    )
    LOGGER.info(
        "preview display=%dx%d (capture remains %dx%d); HighGUI stays on the main thread",
        args.display_width,
        args.display_height,
        actual_width,
        actual_height,
    )

    roi_rectangles: list[tuple[str, int, int, int, int, tuple[int, int, int]]] = []
    roi_error: str | None = None
    roi_loaded = False
    grid_enabled = False
    margins_enabled = False
    roi_enabled = False
    warning_headline: str | None = None
    warning_message: str | None = None
    user_status: str | None = None
    user_status_until = 0.0
    current_luma = mean_luma
    current_variance = pixel_variance
    current_frame_usable = not (mean_luma < 3.0 and pixel_variance < 2.0)
    current_frame_reason = "near_black" if not current_frame_usable else ""
    latest_raw = first_frame if current_frame_usable else None
    good_frames = 1 if current_frame_usable else 0
    near_black_frames = 0 if current_frame_usable else 1
    last_processed_sequence = 1
    last_report = time.perf_counter()
    last_window_poll = last_report
    render_times_ms: deque[float] = deque(maxlen=60)
    wait_times_ms: deque[float] = deque(maxlen=60)
    reader: CaptureReader | None = None
    stopped_by = "unknown"
    reader_stopped = True

    preview_scale = min(
        args.display_width / actual_width,
        args.display_height / actual_height,
    )
    preview_width = max(1, round(actual_width * preview_scale))
    preview_height = max(1, round(actual_height * preview_scale))
    preview_left = (args.display_width - preview_width) // 2
    preview_top = (args.display_height - preview_height) // 2

    def ensure_rois_loaded() -> None:
        nonlocal roi_rectangles, roi_error, roi_loaded
        if not roi_loaded:
            roi_rectangles, roi_error = configured_roi_rectangles()
            roi_loaded = True

    def render_preview(
        measured_fps: float,
        status_message: str | None,
        warning: tuple[str, str] | None,
    ) -> None:
        nonlocal warning_headline, warning_message
        if latest_raw is None:
            canvas = np.zeros((args.display_height, args.display_width, 3), dtype=np.uint8)
        else:
            canvas = fit_frame_for_display(
                latest_raw,
                args.display_width,
                args.display_height,
            )

        display_rois = scale_roi_rectangles(
            roi_rectangles if roi_enabled else [],
            preview_scale,
            preview_scale,
            preview_left,
            preview_top,
        )
        display = draw_guides(
            canvas,
            grid_enabled=grid_enabled,
            margins_enabled=margins_enabled,
            roi_enabled=roi_enabled,
            roi_rectangles=display_rois,
            index=args.index,
            camera_label=args.camera_label,
            backend_name=session.backend_name,
            requested=(args.width, args.height),
            measured_fps=measured_fps,
            mean_luma=current_luma,
            pixel_variance=current_variance,
            reported_fps=session.reported_fps,
            roi_error=roi_error,
            status_message=status_message,
            source_resolution=(actual_width, actual_height),
            copy_frame=False,
        )
        if warning is not None:
            headline, message = warning
            display = draw_capture_warning(display, message, headline=headline)
        cv2.imshow(WINDOW_NAME, display)
        warning_headline = warning[0] if warning else None
        warning_message = warning[1] if warning else None

    initial_warning = None
    if not current_frame_usable:
        initial_warning = (
            "CAMERA RETURNED AN ALL-BLACK FRAME",
            "Waiting for a visible frame; check the camera and USB connection.",
        )

    try:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(WINDOW_NAME, args.display_width, args.display_height)
        reader = CaptureReader(capture, first_frame)
        reader.start()
        render_preview(0.0, None, initial_warning)

        while True:
            loop_started = time.perf_counter()
            sample = reader.snapshot()
            now = loop_started
            redraw_needed = False

            if sample.sequence != last_processed_sequence:
                last_processed_sequence = sample.sequence
                try:
                    frame, frame_luma, frame_variance = describe_frame(sample.frame)
                except ValueError as exc:
                    current_frame_usable = False
                    current_frame_reason = "invalid"
                    current_luma = 0.0
                    current_variance = 0.0
                    warning = (
                        "CAMERA FRAME FORMAT ERROR",
                        str(exc),
                    )
                    LOGGER.warning("camera returned an unusable frame: %s", exc)
                else:
                    current_luma = frame_luma
                    current_variance = frame_variance
                    if frame_luma < 3.0 and frame_variance < 2.0:
                        current_frame_usable = False
                        current_frame_reason = "near_black"
                        near_black_frames += 1
                        warning = (
                            "CAMERA RETURNED AN ALL-BLACK FRAME",
                            f"luma={frame_luma:.2f}, variance={frame_variance:.2f}; holding last visible frame.",
                        )
                        if near_black_frames == 1 or near_black_frames % 100 == 0:
                            LOGGER.warning(
                                "all-black frame detected luma_mean=%.2f pixel_variance=%.2f count=%d",
                                frame_luma,
                                frame_variance,
                                near_black_frames,
                            )
                    else:
                        current_frame_usable = True
                        current_frame_reason = ""
                        latest_raw = frame
                        good_frames += 1
                        warning = None
                        redraw_needed = True

            sample_age = max(0.0, now - sample.last_success_time)
            if sample.consecutive_failures:
                current_frame_usable = False
                current_frame_reason = "read_failure"
                warning = (
                    "CAMERA READ FAILED - retrying",
                    f"{sample.consecutive_failures} consecutive failures; showing the last visible frame.",
                )
            elif sample_age > 1.5:
                current_frame_usable = False
                current_frame_reason = "stale"
                warning = (
                    "CAMERA FRAME STALE - waiting for camera",
                    f"No successful frame for {sample_age:.1f} seconds; showing the last visible frame.",
                )
            elif current_frame_reason == "near_black":
                warning = (
                    "CAMERA RETURNED AN ALL-BLACK FRAME",
                    f"luma={current_luma:.2f}, variance={current_variance:.2f}; holding last visible frame.",
                )
            elif current_frame_reason == "invalid":
                warning = (
                    "CAMERA FRAME FORMAT ERROR",
                    "The latest camera image could not be displayed.",
                )
            elif warning_headline is not None:
                warning = None
            else:
                warning = None

            if warning != (
                (warning_headline, warning_message)
                if warning_headline is not None
                else None
            ):
                redraw_needed = True

            status_message = (
                user_status
                if user_status is not None and now <= user_status_until
                else None
            )
            if user_status is not None and now > user_status_until:
                user_status = None
                redraw_needed = True

            if sample_age >= 30.0:
                LOGGER.error(
                    "stopping after %.1f seconds without a successful camera frame",
                    sample_age,
                )
                stopped_by = "camera_timeout"
                break

            if redraw_needed:
                render_started = time.perf_counter()
                render_preview(sample.measured_fps, status_message, warning)
                render_times_ms.append((time.perf_counter() - render_started) * 1000)

            wait_started = time.perf_counter()
            key = cv2.waitKey(1) & 0xFF
            wait_times_ms.append((time.perf_counter() - wait_started) * 1000)

            if is_exit_key(key):
                stopped_by = "escape" if key == 27 else "q"
                LOGGER.info("exit key received: %s", "Escape" if key == 27 else "Q")
                break

            if key in (ord("g"), ord("G")):
                grid_enabled = not grid_enabled
                user_status = f"Grid {'ON' if grid_enabled else 'OFF'}"
                user_status_until = now + 2.5
                LOGGER.info("grid=%s", "ON" if grid_enabled else "OFF")
                redraw_needed = True
            elif key in (ord("m"), ord("M")):
                margins_enabled = not margins_enabled
                user_status = f"Safe margins {'ON' if margins_enabled else 'OFF'}"
                user_status_until = now + 2.5
                LOGGER.info("safe margins=%s", "ON" if margins_enabled else "OFF")
                redraw_needed = True
            elif key in (ord("o"), ord("O")):
                roi_enabled = not roi_enabled
                if roi_enabled:
                    ensure_rois_loaded()
                user_status = "Configured ROI overlay is read-only"
                user_status_until = now + 2.5
                LOGGER.info("read-only ROI overlay=%s", "ON" if roi_enabled else "OFF")
                redraw_needed = True
            elif key in (ord("s"), ord("S")):
                if (
                    not current_frame_usable
                    or latest_raw is None
                    or sample_age > 1.5
                    or sample.consecutive_failures
                ):
                    user_status = "Snapshot refused: no fresh non-black camera frame"
                    LOGGER.warning("snapshot refused because the current camera frame is not valid")
                else:
                    if roi_enabled:
                        ensure_rois_loaded()
                    annotated = draw_guides(
                        latest_raw,
                        grid_enabled=grid_enabled,
                        margins_enabled=margins_enabled,
                        roi_enabled=roi_enabled,
                        roi_rectangles=roi_rectangles,
                        index=args.index,
                        camera_label=args.camera_label,
                        backend_name=session.backend_name,
                        requested=(args.width, args.height),
                        measured_fps=sample.measured_fps,
                        mean_luma=current_luma,
                        pixel_variance=current_variance,
                        reported_fps=session.reported_fps,
                        roi_error=roi_error,
                        source_resolution=(actual_width, actual_height),
                    )
                    metadata = {
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                        "camera_index": args.index,
                        "camera_label": args.camera_label,
                        "capture_backend": session.backend_name,
                        "fourcc": session.fourcc,
                        "requested_resolution": {"width": args.width, "height": args.height},
                        "actual_resolution": {"width": actual_width, "height": actual_height},
                        "frame_shape": list(latest_raw.shape),
                        "frame_dtype": str(latest_raw.dtype),
                        "pixel_format": "BGR uint8",
                        "mean_luma": round(current_luma, 3),
                        "grayscale_pixel_variance": round(current_variance, 3),
                        "device_reported_fps": (
                            session.reported_fps
                            if math.isfinite(session.reported_fps) and session.reported_fps > 0
                            else None
                        ),
                        "measured_fps": round(sample.measured_fps, 3),
                        "coordinate_system": "RAW_CAMERA",
                        "display_resolution": {
                            "width": args.display_width,
                            "height": args.display_height,
                        },
                        "display_transform": "aspect-ratio-preserving scale with letterbox; no crop",
                        "guides": {
                            "crosshair": True,
                            "grid": grid_enabled,
                            "safe_margins": margins_enabled,
                            "configured_rois": roi_enabled,
                        },
                        "roi_overlay_read_only": True,
                    }
                    try:
                        paths = save_snapshot(latest_raw, annotated, args.snapshot_dir, metadata)
                        user_status = "Reference snapshot saved (raw + annotated)"
                        LOGGER.info("snapshot saved: %s", " | ".join(str(path) for path in paths))
                    except OSError as exc:
                        user_status = f"Snapshot failed: {exc}"
                        LOGGER.exception("snapshot failed")
                user_status_until = now + 2.5
                redraw_needed = True

            if redraw_needed:
                render_started = time.perf_counter()
                # Refresh status and controls after processing a key.
                latest_sample = reader.snapshot()
                latest_age = max(0.0, time.perf_counter() - latest_sample.last_success_time)
                if latest_sample.consecutive_failures:
                    post_warning = (
                        "CAMERA READ FAILED - retrying",
                        f"{latest_sample.consecutive_failures} consecutive failures; showing the last visible frame.",
                    )
                elif latest_age > 1.5:
                    post_warning = (
                        "CAMERA FRAME STALE - waiting for camera",
                        f"No successful frame for {latest_age:.1f} seconds; showing the last visible frame.",
                    )
                elif current_frame_reason == "near_black":
                    post_warning = (
                        "CAMERA RETURNED AN ALL-BLACK FRAME",
                        f"luma={current_luma:.2f}, variance={current_variance:.2f}; holding last visible frame.",
                    )
                else:
                    post_warning = None
                render_preview(latest_sample.measured_fps, user_status, post_warning)
                render_times_ms.append((time.perf_counter() - render_started) * 1000)

            if now - last_report >= 5.0:
                current_sample = reader.snapshot()
                LOGGER.info(
                    "stream camera_index=%d backend=%s fourcc=%s actual=%dx%d "
                    "successful_reads=%d read_failures=%d consecutive_failures=%d "
                    "fps=%.2f luma_mean=%.2f pixel_variance=%.2f "
                    "read_ms_avg=%.2f read_ms_last=%.2f render_ms_avg=%.2f waitKey_ms_avg=%.2f",
                    args.index,
                    session.backend_name,
                    session.fourcc,
                    actual_width,
                    actual_height,
                    current_sample.successful_reads,
                    current_sample.total_failures,
                    current_sample.consecutive_failures,
                    current_sample.measured_fps,
                    current_luma,
                    current_variance,
                    current_sample.average_read_ms,
                    current_sample.last_read_ms,
                    sum(render_times_ms) / len(render_times_ms) if render_times_ms else 0.0,
                    sum(wait_times_ms) / len(wait_times_ms) if wait_times_ms else 0.0,
                )
                last_report = now

            if now - last_window_poll >= 1.0:
                try:
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        stopped_by = "window_closed"
                        LOGGER.info("preview window was closed")
                        break
                except cv2.error as exc:
                    LOGGER.debug("window visibility poll failed: %s", exc)
                last_window_poll = now

            # waitKey services the GUI; this short yield also avoids a busy loop
            # while capture continues independently on its worker thread.
            time.sleep(0.002)
    finally:
        if reader is not None:
            reader_stopped = reader.stop()
        else:
            capture.release()
        cv2.destroyAllWindows()
        final_sample = reader.snapshot() if reader is not None and reader_stopped else None
        LOGGER.info(
            "cleanup complete camera_released=true reader_stopped=%s good_frames=%d "
            "near_black_frames=%d read_failures=%d exit=%s",
            reader_stopped,
            good_frames,
            near_black_frames,
            final_sample.total_failures if final_sample is not None else 0,
            stopped_by,
        )

    return 0 if good_frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
