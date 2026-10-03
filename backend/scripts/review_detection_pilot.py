"""Interactive local human QA review for the CityResponder pilot dataset.

The reviewer never edits source images. It only updates qa_status/qa_reason in
the existing human_qa_manifest.csv after an explicit human decision.
"""

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


CLASS_ORDER = {"fire": 0, "smoke": 1, "person": 2, "negative": 3}
REASONS = {
    "1": "TARGET_ABSENT",
    "2": "WRONG_CLASS",
    "3": "TOO_BLURRY",
    "4": "TOO_DARK",
    "5": "TOO_BRIGHT",
    "6": "UNANNOTATABLE",
    "7": "ACCIDENTAL_POSITIVE_IN_NEGATIVE",
    "8": "OTHER",
}
FIELDS = ["filename", "class", "session_id", "qa_status", "qa_reason"]


def session_number(session_id: str) -> int:
    match = re.search(r"_(\d+)$", session_id)
    return int(match.group(1)) if match else 0


def normalize_filename(value: str) -> str:
    return value.replace("\\", "/")


def atomic_write(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        temporary.replace(path)
    except PermissionError:
        # OneDrive can briefly deny an atomic replace while syncing. Preserve
        # the review decision by falling back to a direct rewrite.
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        try:
            temporary.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    dataset_root = root / "datasets" / "cityresponder_detection_pilot"
    manifest_path = dataset_root / "metadata" / "human_qa_manifest.csv"
    flags_path = root / "reports" / "validation" / "vision" / "detection_pilot_qa_final" / "qa_flags.csv"

    with manifest_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with flags_path.open("r", newline="", encoding="utf-8") as handle:
        flags = {normalize_filename(row["filename"]): row for row in csv.DictReader(handle)}

    ordered = sorted(
        rows,
        key=lambda row: (
            CLASS_ORDER.get(row.get("class", ""), 99),
            session_number(row.get("session_id", "")),
            normalize_filename(row.get("filename", "")),
        ),
    )
    row_by_name = {normalize_filename(row["filename"]): row for row in rows}
    pending_names = [normalize_filename(row["filename"]) for row in ordered if row.get("qa_status") == "PENDING"]

    print("CityResponder Human QA Review")
    print("Review order: FIRE -> SMOKE -> PERSON -> NEGATIVE; session and capture order preserved.")
    print("K/KEEP: keep image | R/REJECT: choose a reason | N/SKIP: leave PENDING | Q/QUIT: save and exit")
    print("Reject reasons: 1 TARGET_ABSENT, 2 WRONG_CLASS, 3 TOO_BLURRY, 4 TOO_DARK, 5 TOO_BRIGHT, 6 UNANNOTATABLE, 7 ACCIDENTAL_POSITIVE_IN_NEGATIVE, 8 OTHER")
    print("Images are never deleted or moved. Decisions are saved after every action.")
    print(f"Manifest: {manifest_path}")

    if not pending_names:
        print("HUMAN_QA_ALREADY_COMPLETE")
        return 0

    current_index = 0
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

    window = "CityResponder Human QA Review"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 820)

    def next_pending(after_name: str | None = None) -> str | None:
        names = [normalize_filename(row["filename"]) for row in ordered if row.get("qa_status") == "PENDING"]
        if not names:
            return None
        if after_name in names:
            return names[(names.index(after_name) + 1) % len(names)]
        return names[0]

    current_name = pending_names[0]
    rejection_mode = False
    quit_requested = False

    try:
        while current_name and not quit_requested:
            row = row_by_name[current_name]
            source_path = dataset_root / Path(current_name)
            image = cv2.imread(str(source_path))
            if image is None:
                print(f"UNREADABLE_SOURCE_REVIEW_BLOCKED {current_name}")
                row["qa_status"] = "PENDING"
                row["qa_reason"] = ""
                current_name = next_pending(current_name)
                continue

            flag = flags.get(current_name, {})
            try:
                blur = float(flag.get("blur_metric", "nan"))
                brightness = float(flag.get("brightness_metric", "nan"))
            except ValueError:
                blur = float("nan")
                brightness = float("nan")
            review_reason = flag.get("review_reason", "")
            near = flag.get("near_duplicate_flag", "NO") == "YES"
            blur_candidate = "low_blur_metric" in review_reason
            position = next(i for i, item in enumerate(ordered, 1) if normalize_filename(item["filename"]) == current_name)
            canvas = np.full((820, 1280, 3), 28, dtype=np.uint8)
            max_w, max_h = 900, 700
            scale = min(max_w / image.shape[1], max_h / image.shape[0])
            shown = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            canvas[60 : 60 + shown.shape[0], 20 : 20 + shown.shape[1]] = shown
            panel_x = 950
            lines = [
                f"{position}/{len(ordered)}  {row['class'].upper()}",
                f"session: {row['session_id']}",
                f"file: {Path(current_name).name[:30]}",
                f"blur: {blur:.2f}" if np.isfinite(blur) else "blur: unavailable",
                f"brightness: {brightness:.2f}" if np.isfinite(brightness) else "brightness: unavailable",
                f"near duplicate: {'YES' if near else 'NO'}",
                f"BLUR CANDIDATE: {'YES' if blur_candidate else 'NO'}",
                "class consistency: HUMAN",
                "",
                "K  KEEP",
                "R  REJECT -> reason",
                "N  SKIP (remain PENDING)",
                "Q  SAVE & QUIT",
            ]
            if rejection_mode:
                lines += ["", "REJECT REASON", "1 TARGET_ABSENT", "2 WRONG_CLASS", "3 TOO_BLURRY", "4 TOO_DARK", "5 TOO_BRIGHT", "6 UNANNOTATABLE", "7 ACCIDENTAL_POSITIVE_IN_NEGATIVE", "8 OTHER"]
            for index, line in enumerate(lines):
                color = (0, 200, 255) if ("YES" in line or "REJECT" in line) else (235, 235, 235)
                cv2.putText(canvas, line, (panel_x, 38 + index * 27), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key == 255:
                try:
                    command = command_queue.get_nowait()
                    if command in {"keep", "k"}: key = ord("k")
                    elif command in {"reject", "r"}: key = ord("r")
                    elif command in {"skip", "n"}: key = ord("n")
                    elif command in {"quit", "q", "exit"}: key = ord("q")
                    elif command.isdigit(): key = ord(command[0])
                except queue.Empty:
                    pass
            if key in (ord("q"), ord("Q"), 27):
                quit_requested = True
                break
            if rejection_mode:
                reason = REASONS.get(chr(key))
                if reason:
                    row["qa_status"] = "REJECT"
                    row["qa_reason"] = reason
                    atomic_write(manifest_path, rows)
                    print(f"REJECT {current_name} reason={reason}", flush=True)
                    rejection_mode = False
                    current_name = next_pending(current_name)
                elif key in (ord("r"), ord("R")):
                    rejection_mode = False
                continue
            if key in (ord("k"), ord("K")):
                row["qa_status"] = "KEEP"
                row["qa_reason"] = ""
                atomic_write(manifest_path, rows)
                print(f"KEEP {current_name}", flush=True)
                current_name = next_pending(current_name)
            elif key in (ord("r"), ord("R")):
                rejection_mode = True
                print("Choose rejection reason 1-8", flush=True)
            elif key in (ord("n"), ord("N")):
                current_name = next_pending(current_name)
    finally:
        cv2.destroyAllWindows()

    counts = Counter((row.get("class"), row.get("qa_status")) for row in rows)
    print("HUMAN_QA_SUMMARY")
    for class_name in ("fire", "smoke", "person", "negative"):
        print(f"{class_name.upper()}: KEEP={counts[(class_name, 'KEEP')]} REJECT={counts[(class_name, 'REJECT')]} PENDING={counts[(class_name, 'PENDING')]}")
    print(f"TOTAL_KEEP={sum(value for (cls, status), value in counts.items() if status == 'KEEP')}")
    print(f"TOTAL_REJECT={sum(value for (cls, status), value in counts.items() if status == 'REJECT')}")
    print(f"TOTAL_PENDING={sum(value for (cls, status), value in counts.items() if status == 'PENDING')}")
    print("HUMAN_QA_COMPLETE=YES" if not any(row.get("qa_status") == "PENDING" for row in rows) else "HUMAN_QA_COMPLETE=NO")
    print("ANNOTATION_STARTED=NO")
    print("SPLIT_CREATED=NO")
    print("TRAINING_STARTED=NO")
    print("COMMIT_PUSH=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
