import { useCallback, useEffect, useState } from "react";
import { lifecycleRequests, type ResponseLifecycle } from "../api/lifecycle";

export function useIncidentLifecycle(incidentId: string | null) {
  const [lifecycle, setLifecycle] = useState<ResponseLifecycle | null>(null);
  const [loading, setLoading] = useState(Boolean(incidentId));
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    if (!incidentId) { setLifecycle(null); setLoading(false); return; }
    setError(null);
    try { setLifecycle(await lifecycleRequests.get(incidentId)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load response lifecycle"); }
    finally { setLoading(false); }
  }, [incidentId]);
  useEffect(() => { setLoading(Boolean(incidentId)); void refresh(); }, [incidentId, refresh]);
  return { lifecycle, loading, error, refresh };
}
