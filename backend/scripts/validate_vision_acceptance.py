"""Build acceptance evidence from real vision observations and AC1 cycles.

This is a recorder/aggregator, not a detector benchmark and not a source of
synthetic detections or hardware results. Empty templates intentionally remain
NOT_RUN until real evidence is supplied.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any


TARGETS = {
    "object_inference_per_second": 5.0,
    "segmentation_inference_per_second": 2.0,
    "fire_verification_scenarios": 40,
    "verification_correctness": 0.85,
    "false_dispatch_rate": 0.10,
    "dimension_mae_cm": 1.0,
    "hardware_cycles": 20,
    "physical_ack_success_rate": 0.95,
    "building_a_roi_min_width_px": 280,
    "building_a_roi_min_height_px": 180,
    "road_min_width_px": 120,
}


def _status(value: bool | None) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "NOT_RUN"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _vision_summary(data: dict[str, Any]) -> dict[str, Any]:
    observations = data.get("observations", [])
    performance = data.get("performance", {})
    dimensions = [item["absolute_error_cm"] for item in observations if item.get("absolute_error_cm") is not None]
    fire_scenarios = [item for item in observations if item.get("ground_truth_fire") is not None and item.get("actual_system_outcome") is not None]
    correct = [item for item in fire_scenarios if item.get("expected_confirmation_outcome") == item.get("actual_system_outcome")]
    non_fire = [item for item in fire_scenarios if item.get("ground_truth_fire") is False]
    false_dispatch = [item for item in non_fire if item.get("false_dispatch") is True]
    detection_rates = performance.get("object_inference_per_second", [])
    segmentation_rates = performance.get("segmentation_inference_per_second", [])
    roi = data.get("coverage", {})
    return {
        "model_availability": data.get("model_availability", "NOT_RUN"),
        "inference_throughput": {
            "object": {"status": _status(None if not detection_rates else median(detection_rates) >= TARGETS["object_inference_per_second"]), "n": len(detection_rates), "median_inference_per_second": median(detection_rates) if detection_rates else None, "target": TARGETS["object_inference_per_second"]},
            "segmentation": {"status": _status(None if not segmentation_rates else median(segmentation_rates) >= TARGETS["segmentation_inference_per_second"]), "n": len(segmentation_rates), "median_inference_per_second": median(segmentation_rates) if segmentation_rates else None, "target": TARGETS["segmentation_inference_per_second"]},
        },
        "fire_verification": {"status": _status(len(fire_scenarios) >= TARGETS["fire_verification_scenarios"] and len(correct) / len(fire_scenarios) >= TARGETS["verification_correctness"] if fire_scenarios else None), "total_scenarios": len(fire_scenarios), "required_scenarios": TARGETS["fire_verification_scenarios"], "correct_outcomes": len(correct), "correctness": len(correct) / len(fire_scenarios) if fire_scenarios else None, "target": TARGETS["verification_correctness"]},
        "false_dispatch": {"status": _status(len(non_fire) > 0 and len(false_dispatch) / len(non_fire) <= TARGETS["false_dispatch_rate"] if non_fire else None), "non_fire_scenarios": len(non_fire), "false_dispatch_count": len(false_dispatch), "rate": len(false_dispatch) / len(non_fire) if non_fire else None, "target": TARGETS["false_dispatch_rate"]},
        "dimension_mae": {"status": _status(None if not dimensions else sum(dimensions) / len(dimensions) <= TARGETS["dimension_mae_cm"]), "n": len(dimensions), "mae_cm": sum(dimensions) / len(dimensions) if dimensions else None, "target_cm": TARGETS["dimension_mae_cm"]},
        "camera_coverage": {"status": _status(roi.get("full_model_area_verified")), "full_model_area_verified": roi.get("full_model_area_verified"), "building_a": roi.get("building_a"), "road_width_px": roi.get("road_width_px"), "notes": roi.get("notes", [])},
    }


def _hardware_summary(data: dict[str, Any]) -> dict[str, Any]:
    cycles = data.get("cycles", [])
    completed = [item for item in cycles if item.get("final_result") == "completed"]
    ack_success = [item for item in cycles if item.get("ack_received") is True and item.get("physical_behavior_confirmed") is True]
    return {
        "real_esp32_connected": data.get("real_esp32_connected", "NOT_RUN"),
        "cycle_status": _status(None if not cycles else len(cycles) >= TARGETS["hardware_cycles"]),
        "completed_cycles": len(completed), "required_cycles": TARGETS["hardware_cycles"],
        "ack_success": {"status": _status(len(cycles) >= TARGETS["hardware_cycles"] and len(ack_success) / len(cycles) >= TARGETS["physical_ack_success_rate"] if cycles else None), "cycles": len(cycles), "ack_success_cycles": len(ack_success), "success_rate": len(ack_success) / len(cycles) if cycles else None, "target": TARGETS["physical_ack_success_rate"]},
        "timeout_count": sum(item.get("ack_received") is False for item in cycles),
        "retry_count": sum(bool(item.get("retry_occurred")) for item in cycles),
        "safe_default_count": sum(bool(item.get("safe_default_occurred")) for item in cycles),
        "physical_confirmation_count": sum(bool(item.get("physical_behavior_confirmed")) for item in cycles),
        "distinguishes_publish_ack_physical": True,
    }


def build_acceptance(vision: dict[str, Any], hardware: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_type": "vision_and_physical_hardware_acceptance",
        "evidence_mode": "real_observations_only",
        "vision": _vision_summary(vision),
        "physical": _hardware_summary(hardware),
        "software_evidence": {"step16": "REFERENCE_ONLY", "step17": "REFERENCE_ONLY", "step18": "REFERENCE_ONLY"},
        "status_policy": ["PASS", "FAIL", "BLOCKED_EXTERNAL", "TBD_SOURCE", "NOT_RUN"],
        "tbd_source": ["production S/T/V/H normalization", "severity normalization/boundaries", "F/R/E/A/M semantics", "area mapping", "calibration gradient/loss/gate", "production topology"],
        "limitations": ["No synthetic detections or hardware cycles are counted.", "Mock ACKs are not hardware ACK evidence.", "This is not a 40-scenario fire accuracy benchmark unless 40 real records are supplied."],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision", type=Path, required=True)
    parser.add_argument("--hardware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_acceptance(_read(args.vision), _read(args.hardware))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
