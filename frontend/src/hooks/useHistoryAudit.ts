import { useCallback, useEffect, useState } from "react";
import { emptyEventFilters, listEvents, type EventFilters, type EventRecord } from "../api/events";

const PAGE_SIZE = 20;
export function useHistoryAudit() {
  const [filters, setFilters] = useState<EventFilters>(emptyEventFilters);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const refresh = useCallback(async (nextFilters = filters) => {
    setLoading(true); setError(null); setSkip(0);
    try { const result = await listEvents(nextFilters, 0, PAGE_SIZE); setEvents(result); setHasMore(result.length === PAGE_SIZE); setLastRefreshedAt(new Date().toISOString()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load audit history"); }
    finally { setLoading(false); }
  }, [filters]);
  const applyFilters = useCallback((nextFilters: EventFilters) => { setFilters(nextFilters); void refresh(nextFilters); }, [refresh]);
  const clearFilters = useCallback(() => applyFilters(emptyEventFilters()), [applyFilters]);
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    const nextSkip = skip + PAGE_SIZE; setLoadingMore(true);
    try { const result = await listEvents(filters, nextSkip, PAGE_SIZE); setEvents((current) => [...current, ...result]); setSkip(nextSkip); setHasMore(result.length === PAGE_SIZE); setLastRefreshedAt(new Date().toISOString()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load more audit history"); }
    finally { setLoadingMore(false); }
  }, [filters, hasMore, loadingMore, skip]);
  useEffect(() => { void refresh(emptyEventFilters()); }, []);
  return { filters, events, skip, hasMore, loading, loadingMore, error, lastRefreshedAt, refresh, applyFilters, clearFilters, loadMore };
}
