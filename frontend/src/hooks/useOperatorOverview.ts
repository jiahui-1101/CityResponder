import { useCallback, useEffect, useRef, useState } from "react";
import { overviewRequests, type ActuatorStatus, type EventRecord, type PerceptionFreshness, type SensorState, type SystemHealth, type VisionSnapshot } from "../api/overview";
import type { LiveEvent } from "../live/LiveConnectionContext";

type SectionState<T> = { data: T | null; loading: boolean; error: string | null };
export type OverviewData = { health: SectionState<SystemHealth>; sensors: SectionState<SensorState[]>; actuators: SectionState<ActuatorStatus>; freshness: SectionState<PerceptionFreshness>; snapshot: SectionState<VisionSnapshot>; events: SectionState<EventRecord[]> };

const initial = <T,>(): SectionState<T> => ({ data: null, loading: true, error: null });
const initialData = (): OverviewData => ({ health: initial(), sensors: initial(), actuators: initial(), freshness: initial(), snapshot: initial(), events: initial() });

export function useOperatorOverview() {
  const [data, setData] = useState<OverviewData>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const activeRefreshes = useRef(0);
  const sectionVersions = useRef<Record<keyof OverviewData, number>>({ health: 0, sensors: 0, actuators: 0, freshness: 0, snapshot: 0, events: 0 });

  const refreshSections = useCallback(async (selected: (keyof OverviewData)[]) => {
    const unique = [...new Set(selected)];
    activeRefreshes.current += 1;
    setRefreshing(true);
    setData((current) => ({
      ...current,
      ...Object.fromEntries(unique.map((key) => [key, {
        ...current[key],
        loading: current[key].data === null,
        error: null,
      }])),
    }) as OverviewData);
    const requests = { health: overviewRequests.health, sensors: overviewRequests.sensors, actuators: overviewRequests.actuators, freshness: overviewRequests.freshness, snapshot: overviewRequests.snapshot, events: overviewRequests.events } as const;
    let updated = false;
    await Promise.all(unique.map(async (key) => {
      const version = sectionVersions.current[key] + 1;
      sectionVersions.current[key] = version;
      const request = requests[key];
      try {
        const result = await request();
        if (sectionVersions.current[key] !== version) return;
        updated = true;
        setData((current) => ({
          ...current,
          [key]: { data: result, loading: false, error: null },
        }) as OverviewData);
      } catch (caught) {
        if (sectionVersions.current[key] !== version) return;
        setData((current) => ({
          ...current,
          [key]: {
            data: current[key].data,
            loading: false,
            error: caught instanceof Error ? caught.message : "Unable to load this section",
          },
        }) as OverviewData);
      }
    }));
    if (updated) setLastRefreshedAt(new Date().toISOString());
    activeRefreshes.current -= 1;
    if (activeRefreshes.current === 0) setRefreshing(false);
  }, []);

  const refresh = useCallback(() => refreshSections(["health", "sensors", "actuators", "freshness", "snapshot", "events"]), [refreshSections]);

  const applySensorEvent = useCallback((event: LiveEvent) => {
    if (!event.payload || typeof event.payload !== "object") return;
    const payload = event.payload as Record<string, unknown>;
    const sensorType = payload.sensor_type;
    if (!(["MQ2", "DHT22", "BUTTON", "IR_A", "IR_B"] as unknown[]).includes(sensorType)) return;
    const sensor_type = sensorType as SensorState["sensor_type"];
    const timestamp = typeof payload.timestamp === "string" ? payload.timestamp : event.backendTimestamp ?? event.receivedAt;
    const nextSensor: SensorState = {
      sensor_type,
      value: payload.value,
      timestamp,
      node_id: typeof payload.node_id === "string" ? payload.node_id : event.entityId ?? null,
      unit: typeof payload.unit === "string" ? payload.unit : null,
      available: true,
    };
    const freshnessKey = ({ MQ2: "mq2", DHT22: "dht22", BUTTON: "button", IR_A: "ir_a", IR_B: "ir_b" } as const)[sensor_type];
    sectionVersions.current.sensors += 1;
    sectionVersions.current.freshness += 1;
    sectionVersions.current.snapshot += 1;
    sectionVersions.current.health += 1;
    setData((current) => {
      const sensors = current.sensors.data ? [...current.sensors.data] : [];
      const index = sensors.findIndex((item) => item.sensor_type === sensor_type);
      if (index >= 0) sensors[index] = nextSensor;
      else sensors.push(nextSensor);
      const freshness = current.freshness.data ? {
        ...current.freshness.data,
        [freshnessKey]: {
          source_type: "sensor",
          source_id: nextSensor.node_id,
          available: true,
          stale: false,
          age_seconds: 0,
          timestamp,
        },
      } : null;
      const health = current.health.data ? {
        ...current.health.data,
        sensor_activity: {
          status: "available",
          last_seen: timestamp,
          detail: `Latest sensor event: ${sensor_type}`,
        },
      } : null;
      const snapshot = current.snapshot.data ? {
        ...current.snapshot.data,
        sensors,
        freshness: freshness ?? current.snapshot.data.freshness,
        warnings: current.snapshot.data.warnings.filter((warning) => warning !== `${sensor_type} is stale`),
        unavailable_inputs: current.snapshot.data.unavailable_inputs.filter((item) => item !== `sensor:${sensor_type}`),
      } : null;
      return {
        ...current,
        sensors: { data: sensors, loading: false, error: null },
        freshness: freshness ? { data: freshness, loading: false, error: null } : current.freshness,
        snapshot: snapshot ? { data: snapshot, loading: false, error: null } : current.snapshot,
        health: health ? { data: health, loading: false, error: null } : current.health,
      };
    });
    setLastRefreshedAt(new Date().toISOString());
  }, []);

  const applyVisionEvent = useCallback((event: LiveEvent) => {
    if (!event.payload || typeof event.payload !== "object") return;
    const payload = event.payload as Record<string, unknown>;
    const frame = payload.frame && typeof payload.frame === "object" ? payload.frame as Record<string, unknown> : null;
    const timestamp = typeof frame?.timestamp === "string" ? frame.timestamp : typeof payload.processing_timestamp === "string" ? payload.processing_timestamp : event.backendTimestamp ?? event.receivedAt;
    sectionVersions.current.freshness += 1;
    sectionVersions.current.snapshot += 1;
    setData((current) => {
      if (event.eventType === "vision_detection") {
        const detectionFreshness = {
          source_type: "vision_detection",
          source_id: typeof frame?.frame_id === "string" ? frame.frame_id : event.entityId ?? null,
          available: true,
          stale: false,
          age_seconds: 0,
          timestamp,
        };
        const freshness = current.freshness.data ? { ...current.freshness.data, detection: detectionFreshness } : null;
        const snapshot = current.snapshot.data ? {
          ...current.snapshot.data,
          generated_at: timestamp,
          detection: payload,
          person_in_hazard: typeof payload.person_in_hazard === "boolean" ? payload.person_in_hazard : null,
          freshness: freshness ?? current.snapshot.data.freshness,
        } : null;
        return {
          ...current,
          freshness: freshness ? { data: freshness, loading: false, error: null } : current.freshness,
          snapshot: snapshot ? { data: snapshot, loading: false, error: null } : current.snapshot,
        };
      }
      if (event.eventType === "vision_road_evidence") {
        const roadName = typeof payload.road_roi_name === "string" ? payload.road_roi_name : event.entityId ?? "unknown";
        const roadFreshness = {
          source_type: "vision_road_evidence",
          source_id: roadName,
          available: true,
          stale: false,
          age_seconds: 0,
          timestamp,
        };
        const freshness = current.freshness.data ? {
          ...current.freshness.data,
          road_evidence: [
            ...current.freshness.data.road_evidence.filter((item) => item.source_id !== roadName),
            roadFreshness,
          ],
        } : null;
        const snapshot = current.snapshot.data ? {
          ...current.snapshot.data,
          generated_at: timestamp,
          road_evidence: [
            ...current.snapshot.data.road_evidence.filter((item) => item.road_roi_name !== roadName),
            payload,
          ],
          freshness: freshness ?? current.snapshot.data.freshness,
        } : null;
        return {
          ...current,
          freshness: freshness ? { data: freshness, loading: false, error: null } : current.freshness,
          snapshot: snapshot ? { data: snapshot, loading: false, error: null } : current.snapshot,
        };
      }
      return current;
    });
    setLastRefreshedAt(new Date().toISOString());
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { ...data, refreshing, lastRefreshedAt, refresh, refreshSections, applySensorEvent, applyVisionEvent };
}
