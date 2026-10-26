"""Run isolated Phase 3 scenarios without modifying project fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.simulation.runner import Phase3SimulationRunner
from app.simulation.route_visualization import RouteImageGeometry


def _default_output_dir(project: Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return project / "reports" / "phase3" / f"run-{run_id}"


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="new, empty output path (defaults to a unique reports/phase3 run directory)",
    )
    args = parser.parse_args()
    output = (args.output_dir or _default_output_dir(project)).resolve()
    # Never unlink or overwrite a previous simulation database or report.
    output.mkdir(parents=True, exist_ok=False)
    database=output/"simulation_audit.db"
    runner=Phase3SimulationRunner(database)
    try:
        report=runner.run_all(); report["append_only_verified"]=runner.verify_append_only()
    finally: runner.close()
    geometry_path = project / "frontend" / "src" / "data" / "routeGeometry.json"
    geometry = RouteImageGeometry.model_validate(
        json.loads(geometry_path.read_text(encoding="utf-8"))
    )
    image_path = project / "frontend" / "public" / "assets" / Path(geometry.image_asset).name
    if not image_path.is_file():
        raise FileNotFoundError(f"Packaged route image asset is missing: {image_path}")
    report["route_geometry"]={
        "graph_version":geometry.graph_version,
        "image_geometry_version":geometry.image_geometry_version,
        "status":geometry.status,
        "warnings":geometry.warnings,
    }
    (output/"simulation_results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output/"routeGeometry.json").write_text(
        geometry.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"]))
    return 0 if report["summary"]["failed"]==0 and report["append_only_verified"] else 1


if __name__=="__main__": raise SystemExit(main())
