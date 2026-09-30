import { useEffect, useRef } from "react";
import { useLiveConnection, type LiveEvent } from "./LiveConnectionContext";

export function useLiveRefresh(eventTypes: string[], refresh: (event: LiveEvent) => unknown, enabled = true, affectedPage = "dashboard") {
  const { subscribe, measureRefresh } = useLiveConnection();
  const refreshRef = useRef(refresh);
  const eventTypesRef = useRef(eventTypes);
  const timerRef = useRef<number | null>(null);
  refreshRef.current = refresh;
  eventTypesRef.current = eventTypes;
  const eventTypesKey = eventTypes.join("\u0000");
  useEffect(() => {
    if (!enabled) return;
    const pending: { event: LiveEvent | null; count: number } = { event: null, count: 0 };
    const unsubscribe = subscribe(eventTypesRef.current, (event) => {
      pending.event = event;
      pending.count += 1;
      if (timerRef.current !== null) return;
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        const next = pending.event;
        const coalescedEventCount = pending.count;
        pending.event = null;
        pending.count = 0;
        if (next) void measureRefresh(next, affectedPage, () => refreshRef.current(next), coalescedEventCount);
      }, 200);
    });
    return () => { unsubscribe(); if (timerRef.current !== null) window.clearTimeout(timerRef.current); timerRef.current = null; };
  }, [affectedPage, enabled, eventTypesKey, measureRefresh, subscribe]);
}
