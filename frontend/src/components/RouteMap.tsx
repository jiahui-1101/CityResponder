import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import geometry from "../data/routeGeometry.json";

type RoutePath = { nodeIds: string[]; edgeIds: string[] };
type RouteMapProps = {
  selected?: RoutePath | null;
  alternative?: RoutePath | null;
  blockedEdgeIds?: string[];
  uncertainEdgeIds?: string[];
  noSafeRoute?: boolean;
  sourceMode?: "SIMULATED" | "PERSISTED";
  routeVersion?: number;
};

type Point = { x: number; y: number };
type Edge = { edge_id: string; from_node: string; to_node: string; points: Point[] };

const edges = geometry.edges as Record<string, Edge>;
const points = (edgeIds: string[]) => edgeIds.flatMap((id, index) => {
  const segment = edges[id]?.points ?? [];
  return index ? segment.slice(1) : segment;
});
const pathData = (edgeIds: string[]) => points(edgeIds).map((point) => `${point.x},${point.y}`).join(" ");

export function RouteMap({ selected, alternative, blockedEdgeIds = [], uncertainEdgeIds = [], noSafeRoute = false, sourceMode = "PERSISTED", routeVersion }: RouteMapProps) {
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">("loading");
  const requested = [...(selected?.edgeIds ?? []), ...(alternative?.edgeIds ?? []), ...blockedEdgeIds, ...uncertainEdgeIds];
  const missing = [...new Set(requested.filter((edgeId) => !edges[edgeId]))];
  const requestedNodes = [...(selected?.nodeIds ?? []), ...(alternative?.nodeIds ?? [])];
  const missingNodes = [...new Set(requestedNodes.filter((nodeId) => !(nodeId in geometry.nodes)))];
  const selectedSequenceMismatch = Boolean(selected && selected.nodeIds.length !== selected.edgeIds.length + 1);
  const alternativeSequenceMismatch = Boolean(alternative && alternative.nodeIds.length !== alternative.edgeIds.length + 1);
  const geometryUnavailable = Boolean(missing.length || missingNodes.length || selectedSequenceMismatch || alternativeSequenceMismatch);
  const selectedPoints = selected ? pathData(selected.edgeIds) : "";
  const alternativePoints = alternative ? pathData(alternative.edgeIds) : "";
  const origin = selected?.nodeIds[0] ? geometry.nodes[selected.nodeIds[0] as keyof typeof geometry.nodes]?.position : undefined;
  const destinationId = selected?.nodeIds.at(-1);
  const destination = destinationId ? geometry.nodes[destinationId as keyof typeof geometry.nodes]?.position : undefined;

  return <div className="route-map-shell">
    <div className="route-map-badges"><span>DRAFT GEOMETRY</span><span>{sourceMode}</span>{routeVersion ? <span>ROUTE v{routeVersion}</span> : null}</div>
    <div className="route-map-canvas" data-route-image-state={imageState} aria-busy={imageState === "loading"}>
      <img src={geometry.image_asset} alt="Overhead photograph of the physical CityResponder tabletop model" onLoad={() => setImageState("ready")} onError={() => setImageState("error")} />
      {imageState !== "error" ? <svg viewBox={`0 0 ${geometry.image_width} ${geometry.image_height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Actual selected route over the physical tabletop image">
        <defs><marker id="route-arrow" markerWidth="11" markerHeight="11" refX="7" refY="3.5" orient="auto"><polygon points="0 0, 7 3.5, 0 7" fill="#22d3ee" /></marker></defs>
        {Object.values(edges).map((edge) => <polyline key={edge.edge_id} points={pathData([edge.edge_id])} className="map-edge" />)}
        {alternativePoints && !geometryUnavailable ? <polyline points={alternativePoints} className="map-route-alternative" /> : null}
        {uncertainEdgeIds.filter((id) => edges[id]).map((id) => <polyline key={`uncertain-${id}`} points={pathData([id])} className="map-edge-uncertain" />)}
        {blockedEdgeIds.filter((id) => edges[id]).map((id) => <g key={`blocked-${id}`}><polyline points={pathData([id])} className="map-edge-blocked" /><text x={edges[id].points[Math.floor(edges[id].points.length / 2)].x} y={edges[id].points[Math.floor(edges[id].points.length / 2)].y - 16} className="map-edge-label">{id} BLOCKED</text></g>)}
        {selectedPoints && !noSafeRoute && !geometryUnavailable ? <><polyline points={selectedPoints} className="map-route-outline" /><polyline points={selectedPoints} className="map-route-selected" markerEnd="url(#route-arrow)" /></> : null}
        {origin && !geometryUnavailable ? <g><circle cx={origin.x} cy={origin.y} r="16" className="map-origin" /><text x={origin.x + 22} y={origin.y + 7} className="map-node-label">START {selected?.nodeIds[0]}</text></g> : null}
        {destination && !geometryUnavailable ? <g><circle cx={destination.x} cy={destination.y} r="18" className="map-destination" /><text x={destination.x + 24} y={destination.y + 7} className="map-node-label">DEST {destinationId}</text></g> : null}
      </svg> : null}
      {imageState === "loading" ? <div className="route-map-loading">Loading tabletop route image…</div> : null}
      {imageState === "error" ? <div className="route-map-alert"><AlertTriangle size={20} /><strong>ROUTE IMAGE UNAVAILABLE</strong><span>The physical tabletop asset could not be loaded. The path strip remains supporting detail only.</span></div> : null}
      {noSafeRoute ? <div className="route-map-alert"><AlertTriangle size={20} /><strong>NO SAFE ROUTE</strong><span>No invalid path is drawn.</span></div> : null}
    </div>
    {geometryUnavailable ? <div className="route-map-error"><AlertTriangle size={14} /><span><strong>Selected route geometry unavailable.</strong>{missing.length ? ` Unknown edges: ${missing.join(", ")}.` : ""}{missingNodes.length ? ` Unknown nodes: ${missingNodes.join(", ")}.` : ""}{selectedSequenceMismatch || alternativeSequenceMismatch ? " The node/edge sequence is inconsistent." : ""} No invented segment was drawn.</span></div> : null}
    <div className="route-map-legend"><span className="selected">Selected A* route</span><span className="alternative">Computed alternative</span><span className="blocked">Blocked</span><span className="uncertain">Uncertain</span></div>
    <p className="route-map-note">Image geometry {geometry.image_geometry_version} · {geometry.warnings[0]} · Configured costs use draft pixel-distance proxies.</p>
  </div>;
}
