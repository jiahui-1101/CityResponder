"""Local manual YOLO bounding-box annotation for QA-approved images only."""

from __future__ import annotations

import argparse
import csv
import queue
import re
import sys
import threading
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


CLASS_IDS = {"fire": 0, "smoke": 1, "person": 2}
CLASS_ORDER = {"fire": 0, "smoke": 1, "person": 2}
MANIFEST_FIELDS = ["filename", "class", "session_id", "qa_status", "annotation_status", "box_count", "notes"]


def normalize_filename(value: str) -> str:
    return value.replace("\\", "/")


def session_number(value: str) -> int:
    match = re.search(r"_(\d+)$", value)
    return int(match.group(1)) if match else 0


def atomic_write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    x1, x2 = sorted((max(0, min(width - 1, x1)), max(0, min(width - 1, x2))))
    y1, y2 = sorted((max(0, min(height - 1, y1)), max(0, min(height - 1, y2))))
    return x1, y1, x2, y2


def valid_box(box: tuple[int, int, int, int], width: int, height: int) -> bool:
    x1, y1, x2, y2 = clamp_box(box, width, height)
    return x2 > x1 and y2 > y1


def read_yolo_boxes(label_path: Path, width: int, height: int) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        _, xc, yc, bw, bh = map(float, parts)
        box = (round((xc - bw / 2) * width), round((yc - bh / 2) * height), round((xc + bw / 2) * width), round((yc + bh / 2) * height))
        if valid_box(box, width, height):
            boxes.append(clamp_box(box, width, height))
    return boxes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    dataset_root = root / "datasets" / "cityresponder_detection_pilot"
    qa_manifest_path = dataset_root / "metadata" / "human_qa_manifest.csv"
    annotation_root = dataset_root / "annotations"
    labels_root = annotation_root / "labels"
    annotation_manifest_path = annotation_root / "annotation_manifest.csv"
    labels_root.mkdir(parents=True, exist_ok=True)

    with qa_manifest_path.open("r", newline="", encoding="utf-8") as handle:
        qa_rows = list(csv.DictReader(handle))
    approved = [row for row in qa_rows if row.get("qa_status") == "KEEP"]
    rejected = [row for row in qa_rows if row.get("qa_status") == "REJECT"]
    pending = [row for row in qa_rows if row.get("qa_status") == "PENDING"]
    if pending:
        print(f"HUMAN_QA_INCOMPLETE pending={len(pending)}")
        return 2

    annotation_rows: list[dict[str, str]] = []
    if annotation_manifest_path.exists():
        with annotation_manifest_path.open("r", newline="", encoding="utf-8") as handle:
            annotation_rows = list(csv.DictReader(handle))
    existing = {normalize_filename(row["filename"]): row for row in annotation_rows}

    def label_path(filename: str) -> Path:
        return labels_root / (Path(filename).stem + ".txt")

    # Keep only current QA-approved images in the active annotation manifest.
    active_rows: list[dict[str, str]] = []
    for row in approved:
        name = normalize_filename(row["filename"])
        old = existing.get(name, {})
        is_negative = row["class"] == "negative"
        status = old.get("annotation_status", "NEGATIVE_CONFIRMED" if is_negative else "PENDING")
        box_count = "0" if is_negative else old.get("box_count", "0")
        notes = old.get("notes", "")
        if is_negative:
            label_path(name).write_text("", encoding="utf-8")
            status = "NEGATIVE_CONFIRMED"
        active_rows.append({"filename": row["filename"], "class": row["class"], "session_id": row["session_id"], "qa_status": "KEEP", "annotation_status": status, "box_count": box_count, "notes": notes})
    atomic_write(annotation_manifest_path, active_rows, MANIFEST_FIELDS)

    positives = sorted(
        [row for row in active_rows if row["class"] in CLASS_IDS],
        key=lambda row: (CLASS_ORDER[row["class"]], session_number(row["session_id"]), normalize_filename(row["filename"])),
    )
    positive_names = {normalize_filename(row["filename"]) for row in positives}
    pending_positive = [row for row in positives if row["annotation_status"] == "PENDING"]
    print(f"QA KEEP images: {len(approved)} (positive={len(positives)}, negative={len(approved)-len(positives)})")
    print(f"QA REJECT excluded: {len(rejected)}")
    print("YOLO classes: 0=fire, 1=smoke, 2=person")
    print("LEFT-DRAG box | X remove last | R reset | ENTER save+next | A previous | D next | Q save+exit")
    print("Terminal fallback: type 'enter', 'a', 'd', 'x', 'r', or 'q' then Enter.")
    print(f"Annotation manifest: {annotation_manifest_path}")

    if not pending_positive:
        print("NO_PENDING_POSITIVE_ANNOTATIONS")
        return 0

    rows_by_name = {normalize_filename(row["filename"]): row for row in active_rows}
    image_by_name: dict[str, np.ndarray] = {}
    boxes_by_name: dict[str, list[tuple[int, int, int, int]]] = {}
    for row in positives:
        name = normalize_filename(row["filename"])
        image = cv2.imread(str(dataset_root / name))
        if image is None:
            rows_by_name[name]["annotation_status"] = "NEEDS_QA_REVIEW"
            rows_by_name[name]["notes"] = "source unreadable"
            continue
        image_by_name[name] = image
        boxes_by_name[name] = read_yolo_boxes(label_path(name), image.shape[1], image.shape[0])

    pending_names = [normalize_filename(row["filename"]) for row in positives if rows_by_name[normalize_filename(row["filename"])] ["annotation_status"] == "PENDING"]
    current_name = pending_names[0]
    window = "CityResponder YOLO Annotation"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 900)
    command_queue: queue.Queue[str] = queue.Queue()

    def read_terminal_commands() -> None:
        while True:
            line = sys.stdin.readline()
            if not line:
                return
            command = line.strip().lower()
            if command:
                command_queue.put(command)

    threading.Thread(target=read_terminal_commands, daemon=True).start()
    drag_start: tuple[int, int] | None = None
    drag_current: tuple[int, int] | None = None
    view_scale = 1.0
    view_offset = (0, 0)

    def mouse_callback(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal drag_start, drag_current
        image = image_by_name.get(current_name)
        if image is None:
            return
        ox, oy = view_offset
        ix = round((x - ox) / view_scale)
        iy = round((y - oy) / view_scale)
        if event == cv2.EVENT_LBUTTONDOWN:
            drag_start = (ix, iy)
            drag_current = (ix, iy)
        elif event == cv2.EVENT_MOUSEMOVE and drag_start is not None:
            drag_current = (ix, iy)
        elif event == cv2.EVENT_LBUTTONUP and drag_start is not None:
            box = clamp_box((drag_start[0], drag_start[1], ix, iy), image.shape[1], image.shape[0])
            if valid_box(box, image.shape[1], image.shape[0]):
                boxes_by_name[current_name].append(box)
            drag_start = None
            drag_current = None

    cv2.setMouseCallback(window, mouse_callback)

    def save_current() -> bool:
        row = rows_by_name[current_name]
        image = image_by_name[current_name]
        boxes = boxes_by_name[current_name]
        if not boxes:
            print("NO_BOXES_DRAWN: draw at least one box or use Q; image remains PENDING", flush=True)
            return False
        width, height = image.shape[1], image.shape[0]
        lines: list[str] = []
        for box in boxes:
            if not valid_box(box, width, height):
                print("INVALID_BOX_REJECTED", flush=True)
                return False
            x1, y1, x2, y2 = clamp_box(box, width, height)
            xc = ((x1 + x2) / 2) / width
            yc = ((y1 + y2) / 2) / height
            bw = (x2 - x1) / width
            bh = (y2 - y1) / height
            if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < bw <= 1 and 0 < bh <= 1):
                print("INVALID_NORMALIZED_BOX", flush=True)
                return False
            lines.append(f"{CLASS_IDS[row['class']]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
        path = label_path(current_name)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        row["annotation_status"] = "ANNOTATED"
        row["box_count"] = str(len(boxes))
        row["notes"] = ""
        atomic_write(annotation_manifest_path, active_rows, MANIFEST_FIELDS)
        print(f"ANNOTATED {current_name} boxes={len(boxes)}", flush=True)
        return True

    def move(delta: int) -> None:
        nonlocal current_name
        names = [normalize_filename(row["filename"]) for row in positives if rows_by_name[normalize_filename(row["filename"])] ["annotation_status"] == "PENDING"]
        if not names:
            current_name = ""
            return
        if current_name not in names:
            current_name = names[0]
            return
        current_name = names[(names.index(current_name) + delta) % len(names)]

    try:
        while current_name:
            image = image_by_name[current_name]
            row = rows_by_name[current_name]
            h, w = image.shape[:2]
            canvas = np.full((900, 1280, 3), 30, dtype=np.uint8)
            view_scale = min(1040 / w, 820 / h)
            shown = cv2.resize(image, (round(w * view_scale), round(h * view_scale)), interpolation=cv2.INTER_AREA)
            view_offset = (20, 50)
            canvas[view_offset[1] : view_offset[1] + shown.shape[0], view_offset[0] : view_offset[0] + shown.shape[1]] = shown
            for index, box in enumerate(boxes_by_name[current_name], 1):
                x1, y1, x2, y2 = box
                p1 = (view_offset[0] + round(x1 * view_scale), view_offset[1] + round(y1 * view_scale))
                p2 = (view_offset[0] + round(x2 * view_scale), view_offset[1] + round(y2 * view_scale))
                cv2.rectangle(canvas, p1, p2, (0, 220, 0), 2)
                cv2.putText(canvas, str(index), (p1[0], max(20, p1[1] - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2, cv2.LINE_AA)
            if drag_start and drag_current:
                p1 = (view_offset[0] + round(drag_start[0] * view_scale), view_offset[1] + round(drag_start[1] * view_scale))
                p2 = (view_offset[0] + round(drag_current[0] * view_scale), view_offset[1] + round(drag_current[1] * view_scale))
                cv2.rectangle(canvas, p1, p2, (0, 180, 255), 2)
            pending_count = sum(1 for item in positives if rows_by_name[normalize_filename(item["filename"])] ["annotation_status"] == "PENDING")
            panel = [
                f"{CLASS_ORDER[row['class']] + 1}/{len(positives)}  pending={pending_count}",
                f"class={row['class']} -> id {CLASS_IDS[row['class']]}",
                f"session={row['session_id']}",
                f"boxes={len(boxes_by_name[current_name])}",
                f"file={Path(current_name).name[:32]}",
                "",
                "LEFT-DRAG draw",
                "X remove last",
                "R reset",
                "ENTER save + next",
                "A previous | D next",
                "Q save + exit",
            ]
            for index, line in enumerate(panel):
                cv2.putText(canvas, line, (1080, 40 + index * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (235, 235, 235), 1, cv2.LINE_AA)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key == 255:
                try:
                    command = command_queue.get_nowait()
                    key = {"enter": 13, "save": 13, "a": ord("a"), "d": ord("d"), "x": ord("x"), "r": ord("r"), "q": ord("q"), "quit": ord("q")}.get(command, ord(command[0]))
                except queue.Empty:
                    pass
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("x"), ord("X")):
                if boxes_by_name[current_name]: boxes_by_name[current_name].pop()
            elif key in (ord("r"), ord("R")):
                boxes_by_name[current_name] = []
            elif key in (ord("a"), ord("A")):
                move(-1)
            elif key in (ord("d"), ord("D")):
                move(1)
            elif key in (13, 10):
                if save_current(): move(1)
    finally:
        cv2.destroyAllWindows()

    counts = Counter((row["class"], row["annotation_status"]) for row in active_rows)
    print("ANNOTATION_SUMMARY")
    for class_name in ("fire", "smoke", "person", "negative"):
        print(f"{class_name.upper()}: " + " ".join(f"{status}={counts[(class_name, status)]}" for status in ("ANNOTATED", "NEGATIVE_CONFIRMED", "PENDING", "NEEDS_QA_REVIEW")))
    print(f"TOTAL_PENDING={sum(value for (cls, status), value in counts.items() if status == 'PENDING')}")
    print("SPLIT_CREATED=NO")
    print("TRAINING_STARTED=NO")
    print("COMMIT_PUSH=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
