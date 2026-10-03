"""Local human QA review for the CityResponder segmentation pilot dataset."""

from __future__ import annotations

import csv
import queue
import sys
import threading
from pathlib import Path

import cv2


CLASSES = ("road_obstacle", "pothole", "clear_road")
REASONS = {
    ord("1"): "TARGET_ABSENT",
    ord("2"): "WRONG_CLASS",
    ord("3"): "TOO_BLURRY",
    ord("4"): "TARGET_NOT_DISTINGUISHABLE",
    ord("5"): "UNANNOTATABLE",
    ord("6"): "ACCIDENTAL_TARGET_IN_CLEAR_ROAD",
    ord("7"): "TARGET_OUTSIDE_ROAD",
    ord("8"): "OTHER",
}


def metric(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var()), float(gray.mean())


def save_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "class", "session_id", "qa_status", "qa_reason"])
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    dataset = root / "datasets" / "cityresponder_segmentation_pilot"
    metadata_path = dataset / "metadata" / "captures.csv"
    manifest_path = dataset / "metadata" / "human_qa_manifest.csv"
    if not metadata_path.exists():
        print(f"Missing metadata: {metadata_path}")
        return 1
    metadata = list(csv.DictReader(metadata_path.open("r", newline="", encoding="utf-8")))
    existing = {}
    if manifest_path.exists():
        existing = {row["filename"]: row for row in csv.DictReader(manifest_path.open("r", newline="", encoding="utf-8"))}
    rows = []
    for row in metadata:
        old = existing.get(row["filename"], {})
        rows.append({"filename": row["filename"], "class": row["class"], "session_id": row["session_id"], "qa_status": old.get("qa_status", "PENDING"), "qa_reason": old.get("qa_reason", "")})
    save_manifest(manifest_path, rows)
    order = {name: i for i, name in enumerate(CLASSES)}
    rows.sort(key=lambda row: (order.get(row["class"], 99), row["session_id"], row["filename"]))
    pending = [i for i, row in enumerate(rows) if row["qa_status"] == "PENDING"]
    if not pending:
        print("HUMAN_QA_COMPLETE")
        return 0
    commands: queue.Queue[str] = queue.Queue()
    stop = threading.Event()

    def terminal_reader():
        while not stop.is_set():
            line = sys.stdin.readline()
            if not line:
                return
            commands.put(line.strip().lower())

    threading.Thread(target=terminal_reader, daemon=True).start()
    index = pending[0]
    window = "CityResponder Segmentation Human QA"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1100, 800)
    while True:
        row = rows[index]
        image_path = dataset / row["filename"]
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"UNREADABLE {row['filename']}")
            row["qa_status"], row["qa_reason"] = "REJECT", "OTHER"
            save_manifest(manifest_path, rows)
            index = next((i for i in range(index + 1, len(rows)) if rows[i]["qa_status"] == "PENDING"), -1)
            if index < 0:
                break
            continue
        blur, brightness = metric(image)
        display = image.copy()
        cv2.putText(display, f"{row['class']} | {row['session_id']} | {index + 1}/{len(rows)}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(display, f"blur={blur:.1f} brightness={brightness:.1f} duplicate_warning={next((m.get('duplicate_warning','') for m in metadata if m['filename']==row['filename']), '')}", (12, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(display, "K KEEP | R REJECT then 1-8 reason | N SKIP | Q EXIT", (12, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.imshow(window, display)
        key = cv2.waitKey(1) & 0xFF
        if key == 255:
            try:
                command = commands.get_nowait()
                if command in {"k", "keep"}: key = ord("k")
                elif command in {"n", "skip"}: key = ord("n")
                elif command in {"q", "quit", "exit"}: key = ord("q")
                elif command.startswith("r"):
                    key = ord("r")
                    if len(command) > 1 and command[-1] in "12345678":
                        commands.put(command[-1])
                elif command in "12345678": key = ord(command)
            except queue.Empty:
                pass
        if key in (ord("q"), ord("Q"), 27):
            break
        if key in (ord("k"), ord("K")):
            row["qa_status"], row["qa_reason"] = "KEEP", ""
            save_manifest(manifest_path, rows)
            index = next((i for i in range(index + 1, len(rows)) if rows[i]["qa_status"] == "PENDING"), -1)
            if index < 0: break
        elif key in (ord("n"), ord("N")):
            index = next((i for i in range(index + 1, len(rows)) if rows[i]["qa_status"] == "PENDING"), -1)
            if index < 0: break
        elif key in (ord("r"), ord("R")):
            print("REJECT reason: 1 TARGET_ABSENT, 2 WRONG_CLASS, 3 TOO_BLURRY, 4 TARGET_NOT_DISTINGUISHABLE, 5 UNANNOTATABLE, 6 ACCIDENTAL_TARGET_IN_CLEAR_ROAD, 7 TARGET_OUTSIDE_ROAD, 8 OTHER")
            reason_key = None
            while reason_key is None:
                reason_key = cv2.waitKey(50) & 0xFF
                if reason_key == 255:
                    try: reason_key = ord(commands.get_nowait()[-1])
                    except queue.Empty: reason_key = None
            if reason_key in REASONS:
                row["qa_status"], row["qa_reason"] = "REJECT", REASONS[reason_key]
                save_manifest(manifest_path, rows)
                index = next((i for i in range(index + 1, len(rows)) if rows[i]["qa_status"] == "PENDING"), -1)
                if index < 0: break
    stop.set()
    cv2.destroyAllWindows()
    print("HUMAN_QA_SUMMARY")
    for class_name in CLASSES:
        subset = [r for r in rows if r["class"] == class_name]
        print(f"{class_name}: KEEP={sum(r['qa_status']=='KEEP' for r in subset)} REJECT={sum(r['qa_status']=='REJECT' for r in subset)} PENDING={sum(r['qa_status']=='PENDING' for r in subset)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
