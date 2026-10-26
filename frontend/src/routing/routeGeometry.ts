export type RoutePoint = { x: number; y: number };
export type RoutePathIds = { nodeIds: string[]; edgeIds: string[] };
export type RouteGeometryData = {
  nodes: Record<string, { position: RoutePoint }>;
  edges: Record<string, { edge_id: string; from_node: string; to_node: string; points: RoutePoint[] }>;
};
export type RouteGeometryResult = { ok: true; points: RoutePoint[] } | { ok: false; reason: string };

const ENDPOINT_TOLERANCE_PX = 2;

function closeEnough(left: RoutePoint, right: RoutePoint): boolean {
  return Math.hypot(left.x - right.x, left.y - right.y) <= ENDPOINT_TOLERANCE_PX;
}

function validPoint(point: RoutePoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

/** Resolve backend-selected edge IDs to a connected, correctly oriented image path. */
export function resolveRouteGeometry(route: RoutePathIds, geometry: RouteGeometryData): RouteGeometryResult {
  const issues: string[] = [];
  if (route.nodeIds.length !== route.edgeIds.length + 1) issues.push(`The node/edge sequence is inconsistent (${route.nodeIds.length} nodes for ${route.edgeIds.length} edges).`);
  const unknownNodes = [...new Set(route.nodeIds.filter((nodeId) => !geometry.nodes[nodeId]))];
  const unknownEdges = [...new Set(route.edgeIds.filter((edgeId) => !geometry.edges[edgeId]))];
  if (unknownNodes.length) issues.push(`No approved image geometry exists for node ID(s): ${unknownNodes.join(", ")}.`);
  if (unknownEdges.length) issues.push(`No approved image geometry exists for edge ID(s): ${unknownEdges.join(", ")}.`);
  if (issues.length) return { ok: false, reason: issues.join(" ") };
  if (!route.nodeIds.length) return { ok: false, reason: "The backend route contains no node sequence." };

  if (!route.edgeIds.length) {
    return { ok: false, reason: "The backend route contains no edges to draw." };
  }

  const pathPoints: RoutePoint[] = [];
  for (const [index, edgeId] of route.edgeIds.entries()) {
    const edge = geometry.edges[edgeId];
    if (!edge) {
      return { ok: false, reason: `No approved image geometry exists for edge ID: ${edgeId}.` };
    }

    const fromNodeId = route.nodeIds[index];
    const toNodeId = route.nodeIds[index + 1];
    const forward = edge.from_node === fromNodeId && edge.to_node === toNodeId;
    const reverse = edge.from_node === toNodeId && edge.to_node === fromNodeId;
    if (!forward && !reverse) {
      return { ok: false, reason: `Edge ${edgeId} does not connect ${fromNodeId} → ${toNodeId} in the backend route sequence.` };
    }
    if (edge.points.length < 2 || edge.points.some((point) => !validPoint(point))) {
      return { ok: false, reason: `Edge ${edgeId} has missing or invalid image coordinates.` };
    }

    const segment = forward ? edge.points : [...edge.points].reverse();
    const fromPosition = geometry.nodes[fromNodeId].position;
    const toPosition = geometry.nodes[toNodeId].position;
    if (!closeEnough(segment[0], fromPosition) || !closeEnough(segment.at(-1)!, toPosition)) {
      return { ok: false, reason: `Edge ${edgeId} endpoints do not align with nodes ${fromNodeId} and ${toNodeId}.` };
    }
    if (pathPoints.length && !closeEnough(pathPoints.at(-1)!, segment[0])) {
      return { ok: false, reason: `Image geometry is discontinuous at node ${fromNodeId}.` };
    }
    pathPoints.push(...(pathPoints.length ? segment.slice(1) : segment));
  }

  return { ok: true, points: pathPoints };
}

export function routePointsToSvg(points: RoutePoint[]): string {
  return points.map(({ x, y }) => `${x},${y}`).join(" ");
}

export function edgePointsToSvg(edge: RouteGeometryData["edges"][string]): string {
  return routePointsToSvg(edge.points);
}
