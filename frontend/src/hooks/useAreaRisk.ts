import { useCallback, useEffect, useState } from "react";
import { riskRequests, type AreaRiskResult } from "../api/risk";

export function useAreaRisk() {
  const [areas, setAreas] = useState<AreaRiskResult[]>([]);
  const [selectedAreaId, setSelectedAreaId] = useState<string | null>(null);
  const [history, setHistory] = useState<AreaRiskResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const refresh = useCallback(async (areaId = selectedAreaId) => {
    setError(null);
    try {
      const nextAreas = await riskRequests.areas();
      setAreas(nextAreas);
      const effectiveId = areaId ?? nextAreas[0]?.area_id ?? null;
      setSelectedAreaId(effectiveId);
      if (effectiveId) setHistory(await riskRequests.history(effectiveId)); else setHistory([]);
      setLastRefreshedAt(new Date().toISOString());
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load area risk"); }
    finally { setLoading(false); }
  }, [selectedAreaId]);

  useEffect(() => { void refresh(); }, []);
  const selectArea = useCallback((areaId: string) => { setSelectedAreaId(areaId); void riskRequests.history(areaId).then(setHistory).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load area risk history")); }, []);
  return { areas, selectedAreaId, selected: areas.find((area) => area.area_id === selectedAreaId) ?? null, history, loading, error, lastRefreshedAt, refresh, selectArea };
}
