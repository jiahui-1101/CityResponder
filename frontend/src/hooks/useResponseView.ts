import { useCallback, useEffect, useState } from "react";
import { routeRequests, type ActuatorStatus, type RouteEvent, type RouteIndexItem } from "../api/routes";

export function useResponseView() {
  const [routes, setRoutes] = useState<RouteIndexItem[]>([]);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [history, setHistory] = useState<RouteEvent[]>([]);
  const [actuators, setActuators] = useState<ActuatorStatus | null>(null);
  const [events, setEvents] = useState<RouteEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const refresh = useCallback(async (routeId = selectedRouteId) => {
    setErrors([]);
    const [routeResult, actuatorResult, eventResult] = await Promise.allSettled([routeRequests.list(), routeRequests.actuators(), routeRequests.events()]);
    const nextErrors: string[] = [];
    let nextRoutes = routes;
    if (routeResult.status === "fulfilled") { nextRoutes = routeResult.value; setRoutes(nextRoutes); }
    else nextErrors.push(routeResult.reason instanceof Error ? routeResult.reason.message : "Unable to load routes");
    if (actuatorResult.status === "fulfilled") setActuators(actuatorResult.value); else nextErrors.push(actuatorResult.reason instanceof Error ? actuatorResult.reason.message : "Unable to load actuator status");
    if (eventResult.status === "fulfilled") setEvents(eventResult.value.filter((event) => ["route_version", "actuator_command", "actuator_ack", "traffic_command_invalidated"].includes(event.event_type))); else nextErrors.push(eventResult.reason instanceof Error ? eventResult.reason.message : "Unable to load response activity");
    const effectiveRouteId = routeId ?? nextRoutes[0]?.route_id ?? null;
    if (effectiveRouteId) { setSelectedRouteId(effectiveRouteId); const historyResult = await Promise.allSettled([routeRequests.history(effectiveRouteId)]); if (historyResult[0].status === "fulfilled") setHistory(historyResult[0].value); else nextErrors.push(historyResult[0].reason instanceof Error ? historyResult[0].reason.message : "Unable to load route history"); }
    else { setHistory([]); setSelectedRouteId(null); }
    setErrors(nextErrors); if (routeResult.status === "fulfilled" || actuatorResult.status === "fulfilled" || eventResult.status === "fulfilled") setLastRefreshedAt(new Date().toISOString()); setLoading(false);
  }, [routes, selectedRouteId]);

  const refreshRoutes = useCallback(async () => {
    const result = await Promise.allSettled([routeRequests.list(), selectedRouteId ? routeRequests.history(selectedRouteId) : Promise.resolve([] as RouteEvent[])]);
    if (result[0].status === "fulfilled") { setRoutes(result[0].value); if (!selectedRouteId && result[0].value[0]) setSelectedRouteId(result[0].value[0].route_id); }
    if (result[1].status === "fulfilled") setHistory(result[1].value);
    setLastRefreshedAt(new Date().toISOString());
    const failed = result.find((item) => item.status === "rejected");
    if (failed) setErrors((current) => [...current, failed.reason instanceof Error ? failed.reason.message : "Unable to refresh route state"]);
  }, [selectedRouteId]);

  const refreshActuatorActivity = useCallback(async () => {
    const result = await Promise.allSettled([routeRequests.actuators(), routeRequests.events()]);
    if (result[0].status === "fulfilled") setActuators(result[0].value);
    if (result[1].status === "fulfilled") setEvents(result[1].value.filter((event) => ["route_version", "actuator_command", "actuator_ack", "traffic_command_invalidated"].includes(event.event_type)));
    setLastRefreshedAt(new Date().toISOString());
    const failed = result.find((item) => item.status === "rejected");
    if (failed) setErrors((current) => [...current, failed.reason instanceof Error ? failed.reason.message : "Unable to refresh response activity"]);
  }, []);

  useEffect(() => { void refresh(); }, []); // initial REST snapshot only; no polling/live channel
  const selectRoute = useCallback((routeId: string) => { setSelectedRouteId(routeId); void routeRequests.history(routeId).then(setHistory).catch((error: unknown) => setErrors((current) => [...current, error instanceof Error ? error.message : "Unable to load route history"])); }, []);
  return { routes, selectedRouteId, history, actuators, events, loading, errors, lastRefreshedAt, refresh, refreshRoutes, refreshActuatorActivity, selectRoute };
}
