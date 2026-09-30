import { useCallback, useEffect, useState } from "react";
import { overviewRequests, type ActuatorStatus, type EventRecord, type PerceptionFreshness, type SensorState, type SystemHealth, type VisionSnapshot } from "../api/overview";

type SectionState<T> = { data: T | null; loading: boolean; error: string | null };
export type OverviewData = { health: SectionState<SystemHealth>; sensors: SectionState<SensorState[]>; actuators: SectionState<ActuatorStatus>; freshness: SectionState<PerceptionFreshness>; snapshot: SectionState<VisionSnapshot>; events: SectionState<EventRecord[]> };

const initial = <T,>(): SectionState<T> => ({ data: null, loading: true, error: null });
const initialData = (): OverviewData => ({ health: initial(), sensors: initial(), actuators: initial(), freshness: initial(), snapshot: initial(), events: initial() });

export function useOperatorOverview() {
  const [data, setData] = useState<OverviewData>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const refreshSections = useCallback(async (selected: (keyof OverviewData)[]) => {
    setRefreshing(true);
    setData((current) => ({ ...current, ...Object.fromEntries(selected.map((key) => [key, { ...current[key], loading: true, error: null }])) }) as OverviewData);
    const requests = { health: overviewRequests.health, sensors: overviewRequests.sensors, actuators: overviewRequests.actuators, freshness: overviewRequests.freshness, snapshot: overviewRequests.snapshot, events: overviewRequests.events } as const;
    const results = await Promise.all(selected.map(async (key) => {
      const request = requests[key];
      try { return { key, data: await request(), error: null }; }
      catch (caught) { return { key, data: null, error: caught instanceof Error ? caught.message : "Unable to load this section" }; }
    }));
    setData((current) => {
      const next = { ...current } as OverviewData;
      for (const result of results) next[result.key as keyof OverviewData] = { data: result.data as never, loading: false, error: result.error } as never;
      return next;
    });
    if (results.some((result) => result.data !== null)) setLastRefreshedAt(new Date().toISOString());
    setRefreshing(false);
  }, []);

  const refresh = useCallback(() => refreshSections(["health", "sensors", "actuators", "freshness", "snapshot", "events"]), [refreshSections]);

  useEffect(() => { void refresh(); }, [refresh]);
  return { ...data, refreshing, lastRefreshedAt, refresh, refreshSections };
}
