"""Interactive CityResponder road-segmentation pilot capture.

Only an explicit SPACE press saves a frame.  Dataset images are the native
1080x840 board crop; the preview is never written to the dataset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
NATIVE_WIDTH, NATIVE_HEIGHT = 1920, 1080
CROP_X, CROP_Y, CROP_W, CROP_H = 340, 80, 1080, 840
CLASSES = ("road_obstacle", "pothole", "clear_road")
CLASS_KEYS = {ord("o"): "road_obstacle", ord("h"): "pothole", ord("n"): "clear_road"}
METADATA_FIELDS = [
    "filename", "class", "session_id", "timestamp", "camera_index",
    "native_resolution", "crop_x", "crop_y", "crop_width", "crop_height",
    "saved_resolution", "sha256", "perceptual_hash", "duplicate_warning",
]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def perceptual_hash(image: np.ndarray) -> str:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    bits = (small >= float(small.mean())).flatten()
    return "".join("1" if bit else "0" for bit in bits)


def hash_distance(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))


def session_target(session_number: int) -> int:
    return 40 if session_number == 1 else 10


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="target_class", choices=CLASSES)
    parser.add_argument("--session", dest="target_session", type=int)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    dataset_root = root / "datasets" / "cityresponder_segmentation_pilot"
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

    counts: defaultdict[str, int] = defaultdict(int)
    session_counts: defaultdict[str, int] = defaultdict(int)
    highest: dict[str, int] = {name: 0 for name in CLASSES}
    for row in rows:
        class_name = row.get("class", "")
        if class_name not in CLASSES:
            continue
        counts[class_name] += 1
        session_id = row.get("session_id", "")
        session_counts[session_id] += 1
        prefix = f"{class_name}_session_"
        if session_id.startswith(prefix):
            try:
                highest[class_name] = max(highest[class_name], int(session_id.rsplit("_", 1)[-1]))
            except ValueError:
                pass

    sessions = {name: (highest[name] + 1 if highest[name] else 1) for name in CLASSES}
    current_class = args.target_class or "road_obstacle"
    if args.target_session is not None:
        sessions[current_class] = args.target_session

    print("CityResponder segmentation pilot capture")
    print("ROAD_OBSTACLE: place a raised object (toy car/block/barricade) on the road.")
    print("POTHOLE: place a flat irregular dark-gray/charcoal patch on the road; keep it visibly distinct from the black road.")
    print("CLEAR_ROAD: remove every obstacle and pothole target from the road.")
    print("Physically change the scene between deliberate captures; keep the webcam fixed.")
    print("O=ROAD_OBSTACLE | H=POTHOLE | N=CLEAR_ROAD | SPACE=save | R=next session | Q/Esc=save and exit")
    print("Terminal fallback: type O/H/N/R/SPACE/Q then Enter if the preview window does not receive keys.")
    print(f"Locked native={NATIVE_WIDTH}x{NATIVE_HEIGHT}, crop=({CROP_X},{CROP_Y},{CROP_W},{CROP_H}), saved={CROP_W}x{CROP_H}")
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

    window = "CityResponder Segmentation Pilot Capture"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 720)
    command_queue: queue.Queue[int] = queue.Queue()
    stop_input = threading.Event()

    def read_terminal_commands() -> None:
        while not stop_input.is_set():
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
    started = time.perf_counter()
    valid_frames = failed_reads = duplicate_warnings = corrupt_frames = 0
    previous_hash: str | None = None
    last_report = started

    def save_one(frame: np.ndarray) -> None:
        nonlocal previous_hash, duplicate_warnings, corrupt_frames
        crop = frame[CROP_Y:CROP_Y + CROP_H, CROP_X:CROP_X + CROP_W]
        if crop.shape[:2] != (CROP_H, CROP_W) or crop.size == 0 or not np.isfinite(crop).all():
            corrupt_frames += 1
            print("REJECTED_CORRUPT_OR_EMPTY_FRAME", flush=True)
            return
        session_id = f"{current_class}_session_{sessions[current_class]:03d}"
        target = session_target(sessions[current_class])
        if session_counts[session_id] >= target:
            print(f"SESSION TARGET COMPLETE class={current_class} session={session_id} target={target}; press R or choose another class", flush=True)
            return
        phash = perceptual_hash(crop)
        duplicate_warning = previous_hash is not None and hash_distance(previous_hash, phash) <= 4
        if duplicate_warning:
            duplicate_warnings += 1
            print("WARNING_NEAR_DUPLICATE_ADJACENT_FRAME", flush=True)
        previous_hash = phash
        number = session_counts[session_id] + 1
        filename = f"{session_id}_{number:04d}_{utc_stamp()}.jpg"
        output_path = raw_root / current_class / filename
        if not cv2.imwrite(str(output_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95]):
            corrupt_frames += 1
            print("REJECTED_WRITE_FAILURE", flush=True)
            return
        sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
        row = {
            "filename": str(output_path.relative_to(dataset_root)),
            "class": current_class,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_index": str(CAMERA_INDEX),
            "native_resolution": f"{NATIVE_WIDTH}x{NATIVE_HEIGHT}",
            "crop_x": str(CROP_X), "crop_y": str(CROP_Y),
            "crop_width": str(CROP_W), "crop_height": str(CROP_H),
            "saved_resolution": f"{CROP_W}x{CROP_H}",
            "sha256": sha, "perceptual_hash": phash,
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
        if session_counts[session_id] == target:
            print(f"SESSION TARGET COMPLETE class={current_class} session={session_id} target={target}", flush=True)

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
            session_id = f"{current_class}_session_{sessions[current_class]:03d}"
            target = session_target(sessions[current_class])
            display = frame.copy()
            cv2.rectangle(display, (CROP_X, CROP_Y), (CROP_X + CROP_W, CROP_Y + CROP_H), (0, 215, 255), 2)
            cv2.putText(display, f"CLASS: {current_class}  SESSION: {session_id}  SESSION COUNT: {session_counts[session_id]}/{target}  TOTAL: {counts[current_class]}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display, f"FPS: {fps:.1f}  NATIVE: {NATIVE_WIDTH}x{NATIVE_HEIGHT}  CROP: {CROP_W}x{CROP_H}", (12, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(display, "O obstacle | H pothole | N clear | SPACE save | R next session | Q quit", (12, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF
            if key == 255:
                try:
                    key = command_queue.get_nowait()
                except queue.Empty:
                    pass
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in CLASS_KEYS:
                current_class = CLASS_KEYS[key]
                previous_hash = None
                print(f"SELECTED class={current_class} session={sessions[current_class]:03d}", flush=True)
            elif key in (ord("r"), ord("R")):
                sessions[current_class] += 1
                previous_hash = None
                print(f"NEW_SESSION class={current_class} session={sessions[current_class]:03d} target={session_target(sessions[current_class])}", flush=True)
            elif key == 32:
                save_one(frame)
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
        stop_input.set()
        capture.release()
        cv2.destroyAllWindows()

    print("CAPTURE_SUMMARY")
    for class_name in CLASSES:
        class_sessions = sorted({row["session_id"] for row in rows if row.get("class") == class_name})
        print(f"{class_name}: images={counts[class_name]} sessions={len(class_sessions)} ids={class_sessions}")
    print(f"TOTAL={sum(counts.values())} valid_frames={valid_frames} failed_reads={failed_reads} duplicate_warnings={duplicate_warnings} corrupt_frames={corrupt_frames}")
    print("POLYGON_ANNOTATION_STARTED=NO")
    print("SEGMENTATION_TRAINING_STARTED=NO")
    print("COMMIT_PUSH=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
