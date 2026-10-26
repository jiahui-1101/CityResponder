import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import geometry from "../data/routeGeometry.json";
import { edgePointsToSvg, resolveRouteGeometry, routePointsToSvg, type RouteGeometryData, type RoutePathIds } from "../routing/routeGeometry";

type RoutePath = RoutePathIds;
type RouteMapProps = {
  selected?: RoutePath | null;
  alternative?: RoutePath | null;
  blockedEdgeIds?: string[];
  uncertainEdgeIds?: string[];
  noSafeRoute?: boolean;
  sourceMode?: "SIMULATED" | "PERSISTED";
  routeVersion?: number;
};

const routeGeometry = geometry as RouteGeometryData;
const edges = routeGeometry.edges;

export function RouteMap({ selected, alternative, blockedEdgeIds, uncertainEdgeIds, noSafeRoute = false, sourceMode = "PERSISTED", routeVersion }: RouteMapProps) {
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">("loading");
  const hasRoadState = blockedEdgeIds !== undefined || uncertainEdgeIds !== undefined;
  const blockedIds = blockedEdgeIds ?? [];
  const uncertainIds = uncertainEdgeIds ?? [];
  const selectedResult = selected && !noSafeRoute ? resolveRouteGeometry(selected, routeGeometry) : null;
  const selectedBlockedConflict = Boolean(selected && selected.edgeIds.some((id) => blockedIds.includes(id)));
  const selectedError = noSafeRoute ? null : selectedBlockedConflict
    ? `The backend-selected sequence includes an edge also marked blocked: ${selected?.edgeIds.filter((id) => blockedIds.includes(id)).join(", ")}.`
    : selectedResult && !selectedResult.ok ? selectedResult.reason : null;
  const alternativeResult = alternative && !noSafeRoute ? resolveRouteGeometry(alternative, routeGeometry) : null;
  const alternativeBlockedConflict = Boolean(alternative && alternative.edgeIds.some((id) => blockedIds.includes(id)));
  const alternativePoints = alternativeResult?.ok && !alternativeBlockedConflict ? routePointsToSvg(alternativeResult.points) : "";
  const selectedPoints = selectedResult?.ok && !selectedError ? routePointsToSvg(selectedResult.points) : "";
  const originId = selected?.nodeIds[0];
  const origin = originId ? routeGeometry.nodes[originId]?.position : undefined;
  const destinationId = selected?.nodeIds.at(-1);
  const destination = destinationId ? routeGeometry.nodes[destinationId]?.position : undefined;
  const missingBlocked = [...new Set([...blockedIds, ...uncertainIds].filter((edgeId) => !edges[edgeId]))];

  return <div className="route-map-shell">
    <div className="route-map-badges"><span>DRAFT GEOMETRY</span><span>{sourceMode}</span>{routeVersion !== undefined ? <span>ROUTE v{routeVersion}</span> : null}</div>
    <div className="route-map-canvas" data-route-image-state={imageState} aria-busy={imageState === "loading"}>
      <img src={geometry.image_asset} alt="Overhead photograph of the physical CityResponder tabletop model" onLoad={() => setImageState("ready")} onError={() => setImageState("error")} />
      {imageState !== "error" ? <svg viewBox={`0 0 ${geometry.image_width} ${geometry.image_height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Actual selected route over the physical tabletop image">
        <defs><marker id="route-arrow" markerWidth="2" markerHeight="2" refX="1.7" refY="1" orient="auto"><polygon points="0 0, 2 1, 0 2" fill="#22d3ee" /></marker></defs>
        {Object.values(edges).map((edge) => <polyline key={edge.edge_id} points={edgePointsToSvg(edge)} className="map-edge" />)}
        {alternativePoints && !noSafeRoute ? <polyline points={alternativePoints} className="map-route-alternative" data-alternative-edge-sequence={alternative?.edgeIds.join(",")} /> : null}
        {uncertainIds.filter((id) => edges[id]).map((id) => <polyline key={`uncertain-${id}`} points={edgePointsToSvg(edges[id])} className="map-edge-uncertain" />)}
        {blockedIds.filter((id) => edges[id]).map((id) => { const points = edges[id].points; const labelPoint = points[Math.floor(points.length / 2)]; return <g key={`blocked-${id}`}><polyline points={edgePointsToSvg(edges[id])} className="map-edge-blocked" /><text x={labelPoint.x} y={labelPoint.y - 16} className="map-edge-label">{id} BLOCKED</text></g>; })}
        {selectedPoints && !noSafeRoute ? <><polyline points={selectedPoints} className="map-route-outline" data-route-node-sequence={selected?.nodeIds.join(",")} data-route-edge-sequence={selected?.edgeIds.join(",")} /><polyline points={selectedPoints} className="map-route-selected" markerEnd="url(#route-arrow)" /></> : null}
        {selectedPoints && origin && originId ? <g><circle cx={origin.x} cy={origin.y} r="16" className="map-origin" /><text x={origin.x + 22} y={origin.y + 7} className="map-node-label">START {originId}</text></g> : null}
        {selectedPoints && destination && destinationId ? <g><circle cx={destination.x} cy={destination.y} r="18" className="map-destination" /><text x={destination.x + 24} y={destination.y + 7} className="map-node-label">DEST {destinationId}</text></g> : null}
      </svg> : null}
      {imageState === "loading" ? <div className="route-map-loading">Loading tabletop route image…</div> : null}
      {imageState === "error" ? <div className="route-map-alert"><AlertTriangle size={20} /><strong>ROUTE IMAGE UNAVAILABLE</strong><span>The physical tabletop asset could not be loaded. The path strip remains supporting detail only.</span></div> : null}
      {noSafeRoute ? <div className="route-map-alert"><AlertTriangle size={20} /><strong>NO SAFE ROUTE</strong><span>No invalid path is drawn.</span></div> : null}
    </div>
    {selectedError ? <div className="route-map-error" role="status"><AlertTriangle size={14} /><span><strong>Selected route geometry unavailable.</strong> {selectedError} No invented segment was drawn.</span></div> : null}
    {alternative && (alternativeBlockedConflict || (alternativeResult !== null && !alternativeResult.ok)) ? <div className="route-map-error" role="status"><AlertTriangle size={14} /><span><strong>Alternative geometry unavailable.</strong> {alternativeBlockedConflict ? "It contains an edge also marked blocked." : !alternativeResult?.ok ? alternativeResult?.reason : ""} The selected route remains independently validated.</span></div> : null}
    {missingBlocked.length ? <div className="route-map-error" role="status"><AlertTriangle size={14} /><span><strong>Some road-state markers have no draft geometry:</strong> {missingBlocked.join(", ")}.</span></div> : null}
    <div className="route-map-legend"><span className="selected">Selected route</span>{alternative ? <span className="alternative">Alternative route</span> : null}{hasRoadState ? <><span className="blocked">Blocked</span><span className="uncertain">Uncertain</span></> : null}</div>
    {!hasRoadState ? <p className="route-map-note">Blocked/uncertain edge IDs are not included in the persisted route API, so map markers are unavailable.</p> : null}
    <p className="route-map-note">Image geometry {geometry.image_geometry_version} · {geometry.warnings[0]} · Configured costs use draft pixel-distance proxies.</p>
  </div>;
}
