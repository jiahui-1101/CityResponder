export type DemoRouteVisualState = "main" | "alternate" | "no_safe_route";

export type DemoRouteFields = {
  status: string;
  source_node_id: string;
  destination_node_id: string;
  no_safe_route: boolean;
  route_changed: boolean;
  previous_version: number | null;
  node_path: string[];
  edge_path: string[];
  reasons: string[];
};

const NO_ROUTE_STATUSES = new Set([
  "no_safe_route",
  "route_not_found",
  "not_found",
  "no_route",
  "no_path",
  "invalid_configuration",
  "unavailable",
]);

const ROUTED_STATUSES = new Set([
  "route_found",
  "main_route",
  "primary_route",
  "alternate_route",
  "route_alternate",
  "rerouted",
]);

const ALTERNATE_PATH_IDS = new Set(["ALTERNATE_ROUTE", "ALTERNATE", "STANDBY", "PE02", "PE07", "N6", "N7"]);

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** Select the fixed demo image from the route read model. No geometry is rendered here. */
export function selectDemoRouteVisualState(route: DemoRouteFields): DemoRouteVisualState {
  const status = normalize(route.status);
  if (route.no_safe_route || NO_ROUTE_STATUSES.has(status)) return "no_safe_route";

  const pathIds = [route.source_node_id, route.destination_node_id, ...route.node_path, ...route.edge_path]
    .map((value) => value.trim().toUpperCase());
  const pathSelectsAlternate = pathIds.some((id) => ALTERNATE_PATH_IDS.has(id) || /(^|[_-])(alternate|standby)([_-]|$)/i.test(id));
  const reasonSelectsAlternate = route.reasons.some((reason) => /\b(alternate|standby|rerout(?:e|ed|ing)?)\b/i.test(reason));
  const versionedReroute = route.route_changed && route.previous_version !== null;
  const statusSelectsAlternate = ["alternate_route", "route_alternate", "rerouted"].includes(status);

  if (pathSelectsAlternate || reasonSelectsAlternate || versionedReroute || statusSelectsAlternate) return "alternate";
  if (ROUTED_STATUSES.has(status)) return "main";
  return "no_safe_route";
}
