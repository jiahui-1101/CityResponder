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
    let disposed = false;
    let running = false;
    const pending: { event: LiveEvent | null; count: number } = { event: null, count: 0 };
    const flush = async () => {
      timerRef.current = null;
      if (running || !pending.event) return;
      const next = pending.event;
      const coalescedEventCount = pending.count;
      pending.event = null;
      pending.count = 0;
      running = true;
      await measureRefresh(next, affectedPage, () => refreshRef.current(next), coalescedEventCount);
      running = false;
      if (!disposed && pending.event && timerRef.current === null) {
        timerRef.current = window.setTimeout(() => { void flush(); }, 0);
      }
    };
    const unsubscribe = subscribe(eventTypesRef.current, (event) => {
      pending.event = event;
      pending.count += 1;
      if (timerRef.current !== null) return;
      // One bounded batch per event burst keeps live updates comfortably below
      // one second without issuing a full REST refresh for every sensor event.
      timerRef.current = window.setTimeout(() => { void flush(); }, 750);
    });
    return () => {
      disposed = true;
      unsubscribe();
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [affectedPage, enabled, eventTypesKey, measureRefresh, subscribe]);
}
