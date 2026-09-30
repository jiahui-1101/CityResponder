import { useCallback, useEffect, useState } from "react";
import { incidentRequests, type EventRecord, type IncidentIndexItem, type IncidentProjection } from "../api/incidents";

export function useIncidents() {
  const [items, setItems] = useState<IncidentIndexItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => { setLoading(true); setError(null); try { setItems(await incidentRequests.list()); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load incidents"); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { items, loading, error, refresh };
}

export function useIncidentDetail(decisionId: string) {
  const [projection, setProjection] = useState<IncidentProjection | null>(null);
  const [history, setHistory] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => { setLoading(true); setError(null); const results = await Promise.allSettled([incidentRequests.projection(decisionId), incidentRequests.history(decisionId)]); const projectionResult = results[0]; const historyResult = results[1]; if (projectionResult.status === "fulfilled") setProjection(projectionResult.value); if (historyResult.status === "fulfilled") setHistory(historyResult.value); const failed = results.find((result) => result.status === "rejected"); if (failed) setError(failed.reason instanceof Error ? failed.reason.message : "Unable to load incident details"); setLoading(false); }, [decisionId]);
  useEffect(() => { void refresh(); }, [refresh]);
  return { projection, history, loading, error, refresh };
}
