"""Manual YOLO-seg polygon annotation UI for QA-KEEP positive images.

Multiple polygons of the source class are supported per image. Existing
label files are loaded and are never overwritten until the user explicitly
saves or resets the current image.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np


CLASS_ID = {"road_obstacle": 0, "pothole": 1}
FIELDS = ["filename", "class", "session_id", "qa_status", "annotation_status", "polygon_count", "notes"]


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def polygon_area(points: list[tuple[int, int]], width: int, height: int) -> float:
    normalized = [(x / width, y / height) for x, y in points]
    return abs(sum(normalized[i][0] * normalized[(i + 1) % len(normalized)][1]
                   - normalized[(i + 1) % len(normalized)][0] * normalized[i][1]
                   for i in range(len(normalized))) / 2.0)


def load_polygons(label_path: Path, width: int, height: int) -> list[list[tuple[int, int]]]:
    """Load existing normalized YOLO polygons without altering their values."""

    polygons: list[list[tuple[int, int]]] = []
    if not label_path.exists():
        return polygons
    for line in label_path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 7 or (len(fields) - 1) % 2:
            continue
        try:
            values = [float(value) for value in fields[1:]]
            points = [(round(values[i] * width), round(values[i + 1] * height)) for i in range(0, len(values), 2)]
        except ValueError:
            continue
        if len(points) >= 3:
            polygons.append(points)
    return polygons


def save_polygons(label_path: Path, class_name: str, polygons: list[list[tuple[int, int]]], width: int, height: int) -> None:
    rows = []
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        coordinates = " ".join(f"{x / width:.6f} {y / height:.6f}" for x, y in polygon)
        rows.append(f"{CLASS_ID[class_name]} {coordinates}")
    label_path.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    dataset = root / "datasets" / "cityresponder_segmentation_pilot"
    qa_path = dataset / "metadata" / "human_qa_manifest.csv"
    metadata_path = dataset / "metadata" / "captures.csv"
    labels_root = dataset / "annotations" / "labels"
    annotation_path = dataset / "annotations" / "annotation_manifest.csv"
    labels_root.mkdir(parents=True, exist_ok=True)
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    if not qa_path.exists() or not metadata_path.exists():
        print("QA manifest and captures metadata are required")
        return 1

    qa = list(csv.DictReader(qa_path.open("r", newline="", encoding="utf-8")))
    old = {}
    if annotation_path.exists():
        old = {row["filename"]: row for row in csv.DictReader(annotation_path.open("r", newline="", encoding="utf-8"))}

    manifest: list[dict[str, str]] = []
    for row in qa:
        if row["qa_status"] != "KEEP":
            continue
        prior = old.get(row["filename"], {})
        if row["class"] in CLASS_ID:
            manifest.append({
                "filename": row["filename"], "class": row["class"], "session_id": row["session_id"],
                "qa_status": "KEEP", "annotation_status": prior.get("annotation_status", "PENDING"),
                "polygon_count": prior.get("polygon_count", "0"), "notes": prior.get("notes", ""),
            })
        elif row["class"] == "clear_road":
            label_path = labels_root / (Path(row["filename"]).stem + ".txt")
            if not label_path.exists():
                label_path.write_text("", encoding="utf-8")
            manifest.append({
                "filename": row["filename"], "class": row["class"], "session_id": row["session_id"],
                "qa_status": "KEEP", "annotation_status": "NEGATIVE_CONFIRMED", "polygon_count": "0",
                "notes": "QA KEEP clear-road image; empty YOLO-seg label",
            })
    write_manifest(annotation_path, manifest)

    positive_rows = [row for row in manifest if row["class"] in CLASS_ID]
    unfinished = [i for i, row in enumerate(positive_rows) if row["annotation_status"] != "ANNOTATED"]
    if not unfinished:
        print("NO_UNFINISHED_POSITIVE_POLYGONS")
        return 0

    index = unfinished[0]
    current_polygon: list[tuple[int, int]] = []
    completed_polygons: list[list[tuple[int, int]]] = []
    reset_armed = False
    window = "CityResponder Segmentation Polygon Annotation"

    def mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            current_polygon.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1100, 800)
    cv2.setMouseCallback(window, mouse)

    def next_index(start: int) -> int:
        return next((i for i in range(start, len(positive_rows)) if positive_rows[i]["annotation_status"] != "ANNOTATED"), len(positive_rows))

    while 0 <= index < len(positive_rows):
        row = positive_rows[index]
        image_path = dataset / row["filename"]
        image = cv2.imread(str(image_path))
        if image is None:
            row["annotation_status"], row["notes"] = "NEEDS_QA_REVIEW", "Image could not be read"
            write_manifest(annotation_path, manifest)
            index = next_index(index + 1)
            continue
        height, width = image.shape[:2]
        label_path = labels_root / (Path(row["filename"]).stem + ".txt")
        completed_polygons = load_polygons(label_path, width, height) if row["annotation_status"] == "ANNOTATED" else []
        current_polygon = []
        reset_armed = False

        while True:
            canvas = image.copy()
            for polygon in completed_polygons:
                cv2.polylines(canvas, [np.asarray(polygon, dtype=np.int32)], True, (0, 220, 0), 2)
                for point in polygon:
                    cv2.circle(canvas, point, 4, (0, 180, 0), -1)
            if len(current_polygon) > 1:
                cv2.polylines(canvas, [np.asarray(current_polygon, dtype=np.int32)], False, (0, 255, 255), 2)
            for point in current_polygon:
                cv2.circle(canvas, point, 5, (0, 255, 255), -1)
            cv2.putText(canvas, f"CLASS: {row['class']}  SESSION: {row['session_id']}  IMAGE: {index + 1}/{len(positive_rows)}", (10, 26), cv2.FONT_HERSHEY_SIMPLEX, .62, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(canvas, f"POLYGONS SAVED: {len(completed_polygons)}  CURRENT POLYGON POINTS: {len(current_polygon)}", (10, 53), cv2.FONT_HERSHEY_SIMPLEX, .56, (0, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, "CLICK add | ENTER finish current | M new polygon | X undo point | BACKSPACE delete polygon | R reset twice | A/D prev/next | Q exit", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, .43, (255, 255, 0), 1, cv2.LINE_AA)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                write_manifest(annotation_path, manifest)
                cv2.destroyAllWindows()
                return 0
            if key in (ord("x"), ord("X")):
                if current_polygon:
                    current_polygon.pop()
                else:
                    print("NO_UNFINISHED_POINT_TO_REMOVE", flush=True)
            elif key == 8:
                if completed_polygons:
                    completed_polygons.pop()
                    save_polygons(label_path, row["class"], completed_polygons, width, height)
                    row["polygon_count"] = str(len(completed_polygons))
                    row["annotation_status"] = "ANNOTATED" if completed_polygons else "PENDING"
                    write_manifest(annotation_path, manifest)
                else:
                    print("NO_COMPLETED_POLYGON_TO_DELETE", flush=True)
            elif key in (ord("r"), ord("R")):
                if reset_armed:
                    current_polygon = []
                    completed_polygons = []
                    label_path.write_text("", encoding="utf-8")
                    row["polygon_count"], row["annotation_status"] = "0", "PENDING"
                    write_manifest(annotation_path, manifest)
                    reset_armed = False
                    print("ALL_POLYGONS_RESET", flush=True)
                else:
                    reset_armed = True
                    print("RESET_ARMED_PRESS_R_AGAIN_TO_CONFIRM", flush=True)
            elif key in (ord("m"), ord("M")):
                if current_polygon:
                    print("FINISH_CURRENT_POLYGON_WITH_ENTER_BEFORE_STARTING_NEW", flush=True)
                else:
                    print("NEW_POLYGON_READY", flush=True)
            elif key in (13, 10):
                reset_armed = False
                if len(current_polygon) < 3:
                    print("POLYGON_REQUIRES_AT_LEAST_3_POINTS", flush=True)
                    continue
                if polygon_area(current_polygon, width, height) <= 1e-8:
                    print("INVALID_ZERO_AREA_POLYGON", flush=True)
                    continue
                if not all(0 <= x < width and 0 <= y < height for x, y in current_polygon):
                    print("INVALID_OUT_OF_BOUNDS_POLYGON", flush=True)
                    continue
                completed_polygons.append(current_polygon[:])
                current_polygon = []
                save_polygons(label_path, row["class"], completed_polygons, width, height)
                row["annotation_status"], row["polygon_count"] = "ANNOTATED", str(len(completed_polygons))
                write_manifest(annotation_path, manifest)
                print(f"POLYGON_SAVED count={len(completed_polygons)} REMAINING_ON_IMAGE", flush=True)
            elif key in (ord("a"), ord("A")):
                if current_polygon:
                    print("SAVE_OR_CLEAR_CURRENT_POLYGON_BEFORE_MOVING", flush=True)
                else:
                    index = max(0, index - 1)
                    break
            elif key in (ord("d"), ord("D")):
                if current_polygon:
                    print("FINISH_CURRENT_POLYGON_WITH_ENTER_BEFORE_D", flush=True)
                elif not completed_polygons:
                    print("ANNOTATE_AT_LEAST_ONE_POLYGON_BEFORE_D", flush=True)
                else:
                    index = next_index(index + 1)
                    break
            else:
                reset_armed = False
        if index >= len(positive_rows):
            break

    cv2.destroyAllWindows()
    write_manifest(annotation_path, manifest)
    print("POLYGON_ANNOTATION_TOOL_EXITED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
