"""Create deterministic review images from actual Phase 3 route IDs and draft geometry."""

from __future__ import annotations

import json
from pathlib import Path

import cv2

from app.simulation.route_visualization import load_route_image_geometry, map_route_to_image


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "reports" / "debug" / "camera_alignment" / "road_graph_phase_b1_final_review_draft.json"
IMAGE = ROOT / "reports" / "debug" / "camera_alignment" / "camera_alignment_20261025T084211_819245Z_index0_raw.jpg"
RESULTS = ROOT / "reports" / "phase3" / "simulation_results.json"
OUTPUT = ROOT / "reports" / "phase35_route_visuals"


def draw_polyline(image, points, color, width, dashed=False):
    pixels=[(round(point.x),round(point.y)) for point in points]
    if not dashed: cv2.polylines(image,[__import__("numpy").array(pixels)],False,color,width,cv2.LINE_AA); return
    for index in range(len(pixels)-1):
        if index % 2 == 0: cv2.line(image,pixels[index],pixels[index+1],color,width,cv2.LINE_AA)


def main() -> int:
    geometry=load_route_image_geometry(GRAPH,image_asset=str(IMAGE))
    report=json.loads(RESULTS.read_text(encoding="utf-8"))
    by_id={item["scenario_id"]:item for item in report["scenarios"]}
    scenes=[("01_normal_route","B"),("02_primary_blocked","C"),("03_rerouted_alternative","K"),("04_no_safe_route","G"),("05_sensor_conflict","E")]
    OUTPUT.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for name,sid in scenes:
        image=cv2.imread(str(IMAGE)); plan=by_id[sid]["response_plan"]
        for edge_id,state in plan["road_states"].items():
            edge=geometry.edges.get(edge_id)
            if edge: draw_polyline(image,edge.points,(0,0,255) if state=="BLOCKED" else (0,180,255),18,state=="UNCERTAIN")
        alternative=plan.get("alternative_route")
        if alternative:
            overlay=map_route_to_image(geometry,alternative["node_path"],alternative["edge_path"]); draw_polyline(image,overlay.selected_points,(220,220,220),10,True)
        selected=plan.get("selected_route")
        if selected:
            overlay=map_route_to_image(geometry,selected["node_path"],selected["edge_path"])
            draw_polyline(image,overlay.selected_points,(10,10,10),24); draw_polyline(image,overlay.selected_points,(255,220,30),13)
            cv2.circle(image,(round(overlay.origin.x),round(overlay.origin.y)),18,(60,210,60),-1,cv2.LINE_AA)
            cv2.circle(image,(round(overlay.destination.x),round(overlay.destination.y)),20,(0,120,255),-1,cv2.LINE_AA)
        title=f"SCENE {sid}: {by_id[sid]['name']} | SIMULATED | DRAFT GEOMETRY"
        cv2.rectangle(image,(0,0),(1920,55),(15,18,22),-1); cv2.putText(image,title,(20,37),cv2.FONT_HERSHEY_SIMPLEX,.85,(255,255,255),2,cv2.LINE_AA)
        if by_id[sid]["actual"].get("no_safe_route"):
            cv2.putText(image,"NO SAFE ROUTE - NO PATH DRAWN",(630,555),cv2.FONT_HERSHEY_SIMPLEX,1.15,(0,0,255),4,cv2.LINE_AA)
        output=OUTPUT/f"{name}.jpg"; cv2.imwrite(str(output),image,[cv2.IMWRITE_JPEG_QUALITY,92]); outputs.append(str(output))
    (OUTPUT/"manifest.json").write_text(json.dumps({"geometry_version":geometry.image_geometry_version,"source_image":str(IMAGE),"outputs":outputs,"physical_verification":False},indent=2)+"\n",encoding="utf-8")
    print("\n".join(outputs)); return 0


if __name__=="__main__": raise SystemExit(main())
