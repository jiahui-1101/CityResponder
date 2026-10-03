"""Interactive CityResponder detection-only pilot capture.

Images are deliberately saved only after an explicit SPACE or B key press.
The saved dataset image is always the locked native 1080x840 board crop; the
preview may be resized by the display window but is never written as data.
"""

from __future__ import annotations

import csv
import hashlib
import argparse
import queue
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


CAMERA_INDEX = 1
NATIVE_WIDTH = 1920
NATIVE_HEIGHT = 1080
CROP_X, CROP_Y, CROP_W, CROP_H = 340, 80, 1080, 840
CLASSES = ("fire", "smoke", "person", "negative")
SESSION_TARGET = 10
KEY_TO_CLASS = {ord("f"): "fire", ord("s"): "smoke", ord("p"): "person", ord("n"): "negative"}
METADATA_FIELDS = [
    "filename",
    "class",
    "session_id",
    "timestamp",
    "camera_index",
    "native_resolution",
    "crop_x",
    "crop_y",
    "crop_width",
    "crop_height",
    "saved_resolution",
    "image_hash",
    "duplicate_warning",
]


def average_hash(image: np.ndarray) -> np.ndarray:
    """Return a compact perceptual average hash for duplicate warnings."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    return resized >= resized.mean()


def hash_distance(left: np.ndarray, right: np.ndarray) -> int:
    return int(np.count_nonzero(left != right))


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="target_class", choices=CLASSES, help="Start on one class")
    parser.add_argument("--session", dest="target_session", type=int, help="Use an explicit session number for the selected class")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    dataset_root = root / "datasets" / "cityresponder_detection_pilot"
    raw_root = dataset_root / "raw"
    metadata_root = dataset_root / "metadata"
    metadata_path = metadata_root / "captures.csv"
    for class_name in CLASSES:
        (raw_root / class_name).mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    if metadata_path.exists():
        with metadata_path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

    counts = defaultdict(int)
    session_counts = defaultdict(int)
    sessions: dict[str, int] = {class_name: 1 for class_name in CLASSES}
    previous_hash: np.ndarray | None = None
    for row in rows:
        class_name = row.get("class", "")
        if class_name in CLASSES:
            counts[class_name] += 1
            session_id = row.get("session_id", "")
            if session_id.startswith(f"{class_name}_session_"):
                try:
                    session_number = int(session_id.rsplit("_", 1)[-1])
                    sessions[class_name] = max(sessions[class_name], session_number)
                    session_counts[session_id] += 1
                except ValueError:
                    pass

    # Start new captures at the next unused session number for each class.
    for class_name in CLASSES:
        sessions[class_name] += 1

    print("CityResponder detection pilot capture")
    print("Safety: use prepared fire/smoke visuals only; no flame, smoke, aerosol, or hazardous stimulus.")
    print("Keep the webcam fixed. FIRE: F | SMOKE: S | PERSON: P | NEGATIVE: N")
    print("SPACE saves one image | B is disabled for controlled sessions | R starts the next session | Q/Esc exits")
    print("Terminal fallback: type F/S/P/N/R/SPACE/Q then Enter if the preview window does not receive keys.")
    print(f"Locked native={NATIVE_WIDTH}x{NATIVE_HEIGHT}, crop=({CROP_X},{CROP_Y},{CROP_W},{CROP_H})")
    print(f"Dataset root: {dataset_root}")

    capture = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_ANY)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, NATIVE_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, NATIVE_HEIGHT)
    if not capture.isOpened():
        print(f"Unable to open camera index {CAMERA_INDEX}")
        return 1

    ok, first_frame = capture.read()
    actual = (int(first_frame.shape[1]), int(first_frame.shape[0])) if ok and first_frame is not None else None
    if actual != (NATIVE_WIDTH, NATIVE_HEIGHT):
        capture.release()
        print(f"CAMERA_NATIVE_RESOLUTION_MISMATCH actual={actual} expected={(NATIVE_WIDTH, NATIVE_HEIGHT)}")
        return 1

    current_class = args.target_class or "negative"
    if args.target_class and args.target_session is not None:
        sessions[args.target_class] = args.target_session
    window = "CityResponder Detection Pilot Capture"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 720)
    started = time.perf_counter()
    valid_frames = 0
    failed_reads = 0
    duplicate_warnings = 0
    corrupt_frames = 0
    last_report = started
    command_queue: queue.Queue[int] = queue.Queue()

    def read_terminal_commands() -> None:
        while True:
            line = sys.stdin.readline()
            if not line:
                return
            command = line.strip().lower()
            if command in {"space", "save"}:
                command_queue.put(32)
            elif command in {"esc", "escape"}:
                command_queue.put(27)
            else:
                for character in command:
                    command_queue.put(ord(character))

    threading.Thread(target=read_terminal_commands, daemon=True).start()

    def save_one(frame: np.ndarray) -> None:
        nonlocal previous_hash, duplicate_warnings, corrupt_frames
        crop = frame[CROP_Y : CROP_Y + CROP_H, CROP_X : CROP_X + CROP_W]
        if crop.shape[:2] != (CROP_H, CROP_W) or crop.size == 0 or not np.isfinite(crop).all():
            corrupt_frames += 1
            print("REJECTED_CORRUPT_OR_EMPTY_FRAME", flush=True)
            return
        current_hash = average_hash(crop)
        duplicate_warning = previous_hash is not None and hash_distance(previous_hash, current_hash) <= 12
        if duplicate_warning:
            duplicate_warnings += 1
            print("WARNING_NEAR_DUPLICATE_SAVED", flush=True)
        previous_hash = current_hash
        session_id = f"{current_class}_session_{sessions[current_class]:03d}"
        current_session_count = session_counts[session_id]
        if current_session_count >= SESSION_TARGET:
            print(f"SESSION TARGET COMPLETE class={current_class} session={session_id} target={SESSION_TARGET}; press R or select another class", flush=True)
            return
        sequence = current_session_count + 1
        filename = f"{session_id}_{sequence:04d}_{utc_stamp()}.jpg"
        output_path = raw_root / current_class / filename
        if not cv2.imwrite(str(output_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95]):
            corrupt_frames += 1
            print("REJECTED_WRITE_FAILURE", flush=True)
            return
        file_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
        row = {
            "filename": str(output_path.relative_to(dataset_root)),
            "class": current_class,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_index": str(CAMERA_INDEX),
            "native_resolution": f"{NATIVE_WIDTH}x{NATIVE_HEIGHT}",
            "crop_x": str(CROP_X),
            "crop_y": str(CROP_Y),
            "crop_width": str(CROP_W),
            "crop_height": str(CROP_H),
            "saved_resolution": f"{CROP_W}x{CROP_H}",
            "image_hash": file_hash,
            "duplicate_warning": "YES" if duplicate_warning else "NO",
        }
        rows.append(row)
        counts[current_class] += 1
        session_counts[session_id] += 1
        with metadata_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"SAVED class={current_class} session={session_id} file={filename}", flush=True)
        if session_counts[session_id] == SESSION_TARGET:
            print(f"SESSION TARGET COMPLETE class={current_class} session={session_id} target={SESSION_TARGET}", flush=True)

    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                failed_reads += 1
                key = cv2.waitKey(10) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                continue
            valid_frames += 1
            elapsed = max(time.perf_counter() - started, 1e-6)
            fps = valid_frames / elapsed
            display = frame.copy()
            cv2.rectangle(display, (CROP_X, CROP_Y), (CROP_X + CROP_W, CROP_Y + CROP_H), (0, 215, 255), 2)
            session_id = f"{current_class}_session_{sessions[current_class]:03d}"
            text = f"class={current_class} session={sessions[current_class]:03d} session_count={session_counts[session_id]}/{SESSION_TARGET} native={NATIVE_WIDTH}x{NATIVE_HEIGHT} crop={CROP_W}x{CROP_H} FPS={fps:.1f}"
            cv2.putText(display, text, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display, "F fire | S smoke | P person | N negative | SPACE save | B burst | R new session | Q quit", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF
            if key == 255:
                try:
                    key = command_queue.get_nowait()
                except queue.Empty:
                    pass
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in KEY_TO_CLASS:
                current_class = KEY_TO_CLASS[key]
                print(f"SELECTED class={current_class} session={sessions[current_class]:03d}", flush=True)
            elif key in (ord("r"), ord("R")):
                sessions[current_class] += 1
                print(f"NEW_SESSION class={current_class} session={sessions[current_class]:03d}", flush=True)
            elif key == 32:
                save_one(frame)
            elif key in (ord("b"), ord("B")):
                print("BURST_DISABLED_FOR_CONTROLLED_SESSION_CAPTURE; use SPACE after scene changes", flush=True)
            now = time.perf_counter()
            if now - last_report >= 10.0:
                print(f"capture: valid={valid_frames} failed={failed_reads} counts={dict(counts)}", flush=True)
                last_report = now
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    elapsed = max(time.perf_counter() - started, 1e-6)
    print("CAPTURE_SUMMARY")
    for class_name in CLASSES:
        class_sessions = sorted({row["session_id"] for row in rows if row.get("class") == class_name})
        print(f"{class_name.upper()}: images={counts[class_name]} sessions={len(class_sessions)}")
    print(f"TOTAL_IMAGES: {sum(counts.values())}")
    print(f"DUPLICATE_WARNINGS: {duplicate_warnings}")
    print(f"FAILED_READS: {failed_reads}")
    print(f"CORRUPT_FRAMES: {corrupt_frames}")
    print(f"CAMERA_MOVED: NO")
    print(f"IMAGE_RESOLUTION: {CROP_W}x{CROP_H}")
    print(f"AVERAGE_CAPTURE_FPS: {valid_frames / elapsed:.3f}")
    print("READY_FOR_HUMAN_DATASET_REVIEW: YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
