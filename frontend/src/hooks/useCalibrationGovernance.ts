import { useCallback, useEffect, useState } from "react";
import { calibrationRequests, type CalibrationCandidateView, type CalibrationGovernance } from "../api/calibration";

export function useCalibrationGovernance() {
  const [governance, setGovernance] = useState<CalibrationGovernance | null>(null);
  const [candidates, setCandidates] = useState<CalibrationCandidateView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setError(null);
    const result = await Promise.allSettled([calibrationRequests.governance(), calibrationRequests.candidates()]);
    const failures: string[] = [];
    if (result[0].status === "fulfilled") setGovernance(result[0].value); else failures.push(result[0].reason instanceof Error ? result[0].reason.message : "Unable to load governance state");
    if (result[1].status === "fulfilled") setCandidates(result[1].value); else failures.push(result[1].reason instanceof Error ? result[1].reason.message : "Unable to load candidates");
    if (!failures.length) setLastRefreshedAt(new Date().toISOString());
    setError(failures.length ? failures.join(" · ") : null); setLoading(false);
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { governance, candidates, loading, error, lastRefreshedAt, refresh };
}
