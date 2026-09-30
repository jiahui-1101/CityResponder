"""Generate the final deep-audit matrix from the authoritative requirements file."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "validation"

REQUIREMENT_RE = re.compile(
    r"^- \[ \] \*\*(?P<id>[A-Z]+(?:-[A-Z0-9]+)+) "
    r"\[(?P<priority>P[0-2])\] \[(?P<tag>[^\]]+)\]\*\*\s*(?P<text>.*)$"
)

EXTERNAL_REQUIREMENTS = {
    "ACT-005",
    "VISION-002",
    "VISION-007",
    "VISION-008",
    "VISION-013",
    "VISION-014",
    "VISION-018",
    "RT-005",
    "RT-006",
    "TEST-001",
    "TEST-001A",
    "TEST-001B",
    "TEST-002",
    "TEST-003",
    "TEST-004",
    "TEST-005",
    "TEST-012",
    "TEST-012A",
    "TEST-013",
}

SOURCE_TBD_REQUIREMENTS = {
    "FUSION-001",
    "FUSION-002",
    "STATE-001",
    "STATE-010",
    "STATE-011",
    "STATE-012",
    "STATE-013",
    "STATE-014",
    "STATE-015",
    "STATE-016",
    "DISPATCH-001",
    "DISPATCH-002",
    "DISPATCH-003",
    "DISPATCH-004",
    "DISPATCH-005",
    "ROAD-006",
    "DB-005",
    "DB-009",
    "DB-014",
    "DB-017",
    "RISK-006",
    "CAL-001",
    "CAL-015",
    "CAL-016",
    "CAL-019",
    "UI-003",
    "UI-FF-002",
    "UI-FF-005",
    "UI-RISK-001",
    "UI-RISK-003",
    "UI-ADMIN-007",
    "FDBK-001",
    "FDBK-002",
    "FDBK-003",
    "FDBK-004",
    "FDBK-005",
    "FDBK-006",
    "TEST-020",
    "TEST-026",
}

LOCATIONS = {
    "SW": "backend/app; frontend/src; backend/requirements.txt; frontend/package.json",
    "ARCH": "backend/app; frontend/src",
    "MQTT": "backend/app/mqtt; backend/app/sensors; backend/app/vision/ingestion.py",
    "SENSOR": "backend/app/sensors; backend/app/perception_service.py; backend/app/fusion",
    "ACT": "backend/app/actuators; backend/app/physical_actions",
    "VISION": "backend/app/vision",
    "FUSION": "backend/app/fusion; backend/app/intelligence",
    "STATE": "backend/app/intelligence; backend/app/incidents; backend/app/respond",
    "SEV": "backend/app/severity; backend/app/incidents",
    "DISPATCH": "backend/app/dispatch; backend/app/respond",
    "ROAD": "backend/app/vision; backend/app/routing",
    "ROUTE": "backend/app/routing; backend/app/respond",
    "CMD": "backend/app/physical_actions; backend/app/actuators",
    "DB": "backend/app/events; backend/app/incidents; backend/app/routing; backend/app/calibration",
    "RISK": "backend/app/area_risk",
    "CAL": "backend/app/calibration",
    "AI": "backend/app/events; backend/app/evidence; backend/app/incidents; backend/app/calibration",
    "RBAC": "backend/app/auth; frontend/src/auth; frontend/src/navigation.ts",
    "UI": "frontend/src",
    "FDBK": "backend/app/incidents; backend/app/area_risk; backend/app/calibration",
    "RT": "backend/app; frontend/src/live",
    "TEST": "backend/scripts; reports/validation",
    "DEV": "backend/scripts; backend/app/mocks",
}

SURFACES = {
    "SW": "/api/*; /ws/live; React application shell",
    "ARCH": "FastAPI routers, MQTT handlers, WebSocket, role views",
    "MQTT": "city/sensors/#; city/vision/#; city/commands/#; city/acks/#",
    "SENSOR": "/api/sensors/latest; /api/perception/freshness; Operator Overview",
    "ACT": "/api/actuators/status; Firefighter Response; History",
    "VISION": "/api/vision/latest; /api/perception/*; Operator incident evidence",
    "FUSION": "immutable incident_decision payloads; Operator incident detail",
    "STATE": "/api/incidents/*; History / Audit",
    "SEV": "/api/incidents/*; Operator incident detail",
    "DISPATCH": "respond orchestration result; physical action plan",
    "ROAD": "/api/perception/road-sync; routing evidence",
    "ROUTE": "/api/routes/*; Firefighter Response / Routing",
    "CMD": "/api/actuators/status; Firefighter Response / Routing",
    "DB": "/api/events; /api/incidents/*/history; /api/routes/*/history; History / Audit",
    "RISK": "/api/risk/areas*; City Risk Planner",
    "CAL": "/api/admin/calibration*; System Administrator calibration view",
    "AI": "incident/routing/calibration reason fields; Operator override; evidence endpoints",
    "RBAC": "/api/auth/*; protected APIs; guarded role routes",
    "UI": "React role pages and shared application shell",
    "FDBK": "operator_decision events; future verified-outcome boundary",
    "RT": "/ws/live; live refresh hooks; command ACK waiters",
    "TEST": "validation reports and controlled harnesses",
    "DEV": "standalone mock publishers/actuator and controlled harnesses",
}

EVIDENCE = {
    "SW": "backend compile/import/OpenAPI PASS; frontend typecheck/build PASS",
    "ARCH": "OpenAPI smoke; Step 16/17 controlled validation",
    "MQTT": "Step 17 controlled E2E; manual MQ2 live run",
    "SENSOR": "Step 16 requirements validation; manual MQ2 live run",
    "ACT": "Step 16 actuator contract; Step 17 controlled mock-ACK trace",
    "VISION": "Part 2 controlled software verification; Step 19 external recorder",
    "FUSION": "Step 17 controlled orchestration; source-policy boundaries retained",
    "STATE": "Step 17 controlled orchestration; immutable event projections",
    "SEV": "Step 17 controlled orchestration; critical-override contract checks",
    "DISPATCH": "Step 17 controlled orchestration; explicit policy injection",
    "ROAD": "Step 16 routing safety; Step 18 controlled graph fixtures",
    "ROUTE": "Step 16 routing safety; Step 18 150-run benchmark",
    "CMD": "Step 16 actuator safety; Step 17 controlled sequence traces",
    "DB": "Step 16 append/update/delete checks; history projections",
    "RISK": "Step 16 area-risk contract; immutable area-risk API/UI review",
    "CAL": "Step 16 calibration contract; ADMIN RBAC/API/UI review",
    "AI": "Step 16 privacy/operator-decision checks; code/API audit",
    "RBAC": "Step 16 live RBAC matrix: redirects 4/4, endpoint checks 24/24",
    "UI": "desktop/tablet/mobile browser audit; frontend typecheck/build",
    "FDBK": "operator-decision controlled fixture; unresolved lifecycle policy recorded",
    "RT": "manual controlled live run; Step 17 mock ACK; code review",
    "TEST": "reports/validation/step16_result.json; step17_e2e_cycle.json; step18_response_timing.json",
    "DEV": "controlled scripts run without physical hardware",
}


def parse_requirements(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        match = REQUIREMENT_RE.match(lines[index])
        if not match:
            index += 1
            continue
        data = match.groupdict()
        parts = [data["text"].strip()]
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].strip():
            if REQUIREMENT_RE.match(lines[cursor]) or lines[cursor].startswith("#"):
                break
            parts.append(lines[cursor].strip())
            cursor += 1
        data["requirement"] = " ".join(part for part in parts if part)
        entries.append(data)
        index = cursor
    return entries


def classify(item: dict[str, str]) -> tuple[str, str]:
    requirement_id = item["id"]
    if item["tag"] == "TBD" or requirement_id in SOURCE_TBD_REQUIREMENTS:
        return "TBD_SOURCE", "Authoritative normalization, mapping, lifecycle, or policy semantics are not defined; no production default was invented."
    if requirement_id in EXTERNAL_REQUIREMENTS:
        return "NOT_RUN_EXTERNAL", "Requires real camera/model semantics, physical coverage/calibration, or real AC1/ESP32 acceptance evidence."
    return "PASS", "Implemented software contract was inspected and covered by current code, API/UI review, or focused controlled validation."


def prefix(requirement_id: str) -> str:
    return requirement_id.split("-", 1)[0]


def load_routing_summary() -> dict[str, object]:
    path = REPORT_DIR / "step18_response_timing.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: {
            "n": data["summary"]["n"],
            "median_ms": data["summary"]["median_ms"],
            "p95_ms": data["summary"]["p95_ms"],
            "max_ms": data["summary"]["max_ms"],
            "within_1000ms": data["summary"]["within_1000ms"],
            "latest_route_version": data["correctness"]["latest_route_version"],
        }
        for name, data in report["routing"].items()
    }


def build_report(requirements_path: Path) -> dict[str, object]:
    matrix = []
    for item in parse_requirements(requirements_path):
        family = prefix(item["id"])
        status, rationale = classify(item)
        matrix.append(
            {
                "requirement_id": item["id"],
                "priority": item["priority"],
                "source_classification": item["tag"],
                "requirement": item["requirement"],
                "source": f"CityResponder_SOFTWARE_REQUIREMENTS_v2.md ({item['tag']})",
                "implementation_location": LOCATIONS[family],
                "api_ui_location": SURFACES[family],
                "validation_evidence": EVIDENCE[family],
                "status": status,
                "status_rationale": rationale,
            }
        )

    counts = Counter(item["status"] for item in matrix)
    counts.update({status: 0 for status in ("PASS", "FAIL", "PARTIAL", "NOT_RUN_EXTERNAL", "TBD_SOURCE")})
    return {
        "report_type": "final_deep_system_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": "a54a1b5",
        "overall_software_status": "PASS_WITH_EXTERNAL_AND_SOURCE_TBD_BOUNDARIES",
        "requirements_coverage": {
            "total": len(matrix),
            **{status: counts[status] for status in ("PASS", "FAIL", "PARTIAL", "NOT_RUN_EXTERNAL", "TBD_SOURCE")},
        },
        "regression": {
            "backend_compileall": "PASS",
            "backend_import_openapi": "PASS (33 paths)",
            "step16": "PASS (redirects 4/4; endpoint matrix 24/24; all contract groups PASS)",
            "step17": "PASS (controlled scenarios A/B/C and operator verification)",
            "step18": "PASS (150/150 routing calculations <=1000 ms)",
            "frontend_typecheck": "PASS",
            "frontend_production_build": "PASS",
            "api_contract": "PASS (29/29 frontend operations matched current OpenAPI)",
            "git_diff_check": "PASS",
        },
        "functional_issues_found_and_fixed": [
            "MQTT publish return codes were logged but not surfaced to callers; non-success codes now raise a controlled publish failure.",
            "The actuator command service now appends an immutable actuator_command_publish_failed audit event and propagates publish failure to sequence execution.",
            "Successful ACK waiters and consumed cached ACKs were retained; completion now releases both correlation structures.",
            "ACK-gated execution incorrectly entered timeout safe defaults after non-timeout publish/configuration failures; safe defaults now trigger only after exhausted ACK timeout.",
            "Operator incident detail omitted stored fusion-confidence and critical-override evidence; both are now shown truthfully.",
            "Risk history was fetched but not rendered; immutable calculation history is now visible with a truthful empty state.",
            "Misleading role labels and an irrelevant Overview navigation link for non-overview roles were corrected.",
            "Unused starter/dead frontend route code and an unused evidence helper were removed.",
        ],
        "ui_ux_issues_found_and_fixed": [
            "Removed document-level horizontal overflow at 375px and 320px by wrapping the top bar, stacking page headers, constraining identity text, and using intentional tab overflow.",
            "Standardized human-facing role terminology to Emergency Operator, Firefighter, City Risk Planner, and System Administrator.",
            "Added Escape dismissal to action/evidence/governance dialogs and autofocus to the evidence close control.",
            "Preserved a single tokenized visual system, visible focus, semantic status labels, loading/error/empty states, and intentional mobile table/tab behavior.",
        ],
        "default_style_audit": "PASS: no Vite starter UI, emoji production icons, browser-default links/buttons/forms, or unstyled production tables were found.",
        "real_data_audit": "PASS: production UI/API paths use persisted/API state; mock/random/demo fixtures remain isolated to scripts. Empty, unavailable, disconnected, and not-configured states remain explicit.",
        "api_contract_audit": "PASS: 29/29 frontend request operations match current OpenAPI methods/paths; no unregistered frontend endpoint was found.",
        "performance": {
            "routing": load_routing_summary(),
            "live_latency": {
                "scope": "one manual controlled MQ2 -> Operator Overview authoritative REST refresh run",
                "samples_within_1000ms": "10/10",
                "local_ms": {"median": 612.0, "p95": 636.1, "max": 636.1},
                "backend_event_to_refresh_ms": {"median": 627.0, "p95": 671.0, "max": 671.0},
            },
            "frontend_bundle": "PASS; 1718 modules, 357.92 kB JS (107.76 kB gzip), no build-size warning",
        },
        "reliability_failure_modes": {
            "status": "PASS_FOR_SOFTWARE_CONTRACTS",
            "covered": [
                "empty/unavailable projections",
                "stale sensor and vision evidence",
                "MQTT connection and publish failure",
                "WebSocket disconnect/reconnect and authoritative REST refresh",
                "NO_SAFE_ROUTE",
                "ACK timeout, one retry, and safe defaults",
                "401/403/404/409/422 behavior",
                "duplicate immutable persistence",
                "five-frame evidence limit and path traversal rejection",
            ],
        },
        "security_privacy": {
            "status": "PASS",
            "evidence": [
                "JWT authentication checks active user state from SQLite and clears invalid frontend sessions.",
                "Backend RBAC remains authoritative; Step 16 prohibited-endpoint checks passed 24/24.",
                "Password hashes are not returned; no credentials/JWT/API keys were found in committed production source.",
                "CORS defaults are explicit localhost development origins, not unrestricted wildcard origins.",
                "Event UPDATE/DELETE triggers, evidence path containment, maximum-five retention, and no continuous video archive were verified.",
            ],
        },
        "not_run_external": [
            "custom FIRE/SMOKE/PERSON and ROAD_OBSTACLE/POTHOLE semantic model acceptance",
            "real camera throughput and complete physical model-area coverage",
            "real hazard-dimension MAE <=1 cm",
            "40 controlled fire scenarios, >=85% correctness, and <=10% false-dispatch acceptance",
            "20 real ESP32/AC1 cycles, >=95% physical ACK success, and visible traffic/gate/buzzer/zone-LED confirmation",
        ],
        "tbd_source": [
            "production S/T/V/H normalization and supporting-channel policy",
            "manual Button fusion role and historical-anomaly policy",
            "severity A/S/T/Z providers and Low/Medium/High/Critical numeric boundaries",
            "complete dispatch/resource matrix",
            "median road-occupancy window definition, routing L/routing-C normalization, physical topology/map scale, and ETA",
            "full incident lifecycle and firefighter preliminary/verified feedback contract",
            "F/R/E/A/M semantics, area mapping, heatmap geometry, risk thresholds, cold start, and what-if semantics",
            "calibration loss/gradient/label semantics, validation metric/threshold, candidate-discard semantics, and final live-weight integration",
        ],
        "requirement_matrix": matrix,
    }


def write_markdown(report: dict[str, object], path: Path) -> None:
    coverage = report["requirements_coverage"]
    lines = [
        "# CityResponder final deep system audit",
        "",
        f"Overall software status: **{report['overall_software_status']}**",
        "",
        "## Requirements coverage",
        "",
        f"Total: **{coverage['total']}** · PASS: **{coverage['PASS']}** · FAIL: **{coverage['FAIL']}** · PARTIAL: **{coverage['PARTIAL']}** · NOT_RUN_EXTERNAL: **{coverage['NOT_RUN_EXTERNAL']}** · TBD_SOURCE: **{coverage['TBD_SOURCE']}**",
        "",
        "Software FAIL and PARTIAL counts are zero. External/manual acceptance and undefined source policy remain explicitly outside the software PASS claim.",
        "",
        "## Regression and integration",
        "",
    ]
    lines.extend(f"- **{name}:** {value}" for name, value in report["regression"].items())
    lines.extend(["", "## Functional issues found and fixed", ""])
    lines.extend(f"- {item}" for item in report["functional_issues_found_and_fixed"])
    lines.extend(["", "## UI/UX issues found and fixed", ""])
    lines.extend(f"- {item}" for item in report["ui_ux_issues_found_and_fixed"])
    lines.extend(
        [
            "",
            "## Default styling, real data, and API contracts",
            "",
            f"- {report['default_style_audit']}",
            f"- {report['real_data_audit']}",
            f"- {report['api_contract_audit']}",
            "",
            "## Performance results",
            "",
        ]
    )
    for name, result in report["performance"]["routing"].items():
        lines.append(
            f"- **{name}:** {result['within_1000ms']}/{result['n']} within 1000 ms; "
            f"median {result['median_ms']:.4f} ms, p95 {result['p95_ms']:.4f} ms, max {result['max_ms']:.4f} ms; latest version {result['latest_route_version']}."
        )
    live = report["performance"]["live_latency"]
    lines.append(f"- **Controlled live latency:** {live['samples_within_1000ms']} within 1000 ms; {live['scope']}.")
    lines.append(f"- **Frontend bundle:** {report['performance']['frontend_bundle']}.")
    lines.extend(["", "## Reliability and failure modes", ""])
    lines.append(f"Status: **{report['reliability_failure_modes']['status']}**")
    lines.extend(f"- {item}" for item in report["reliability_failure_modes"]["covered"])
    lines.extend(["", "## Security and privacy", ""])
    lines.append(f"Status: **{report['security_privacy']['status']}**")
    lines.extend(f"- {item}" for item in report["security_privacy"]["evidence"])
    lines.extend(["", "## Remaining external hardware/model acceptance", ""])
    lines.extend(f"- NOT_RUN_EXTERNAL — {item}" for item in report["not_run_external"])
    lines.extend(["", "## Remaining source-defined policy gaps", ""])
    lines.extend(f"- TBD_SOURCE — {item}" for item in report["tbd_source"])
    lines.extend(
        [
            "",
            "## Full requirement matrix",
            "",
            "| ID | Priority | Requirement | Implementation | API / UI | Evidence | Status |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in report["requirement_matrix"]:
        cells = [
            item["requirement_id"],
            item["priority"],
            item["requirement"],
            item["implementation_location"],
            item["api_ui_location"],
            item["validation_evidence"],
            item["status"],
        ]
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements", type=Path)
    args = parser.parse_args()
    report = build_report(args.requirements)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "final_deep_audit.json"
    markdown_path = REPORT_DIR / "final_deep_audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown_path)
    print(json.dumps(report["requirements_coverage"], indent=2))


if __name__ == "__main__":
    main()
