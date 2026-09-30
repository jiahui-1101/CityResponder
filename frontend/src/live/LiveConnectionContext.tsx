import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getApiBaseUrl, getStoredAccessToken } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export type LiveConnectionStatus = "connecting" | "connected" | "disconnected" | "error";
export type LiveEvent = {
  eventId?: string;
  eventType: string;
  topic?: string;
  entityType?: string;
  entityId?: string;
  payload: unknown;
  receivedAt: string;
  receivedPerformanceMs: number;
  broadcastAt?: string;
  backendTimestamp?: string;
};
export type LiveLatencySample = {
  eventId?: string;
  eventType: string;
  backendEventAt?: string;
  broadcastAt?: string;
  wsReceivedAt: string;
  refreshStartedAt: string;
  refreshCompletedAt: string;
  affectedPage: string;
  refreshOutcome: "success" | "refresh_failed" | "invalid_timing";
  coalescedEventCount: number;
  websocketToRefreshStartMs: number | null;
  refreshDurationMs: number | null;
  websocketToRefreshCompleteMs: number | null;
  backendEventToWsMs: number | null;
  backendEventToRefreshCompleteMs: number | null;
  crossClockValid: boolean;
};
type LiveHandler = (event: LiveEvent) => void;
type LiveContextValue = {
  status: LiveConnectionStatus;
  lastMessageAt: string | null;
  lastBackendEventAt: string | null;
  subscribe: (eventTypes: string[] | "*", handler: LiveHandler) => () => void;
  measureRefresh: (event: LiveEvent, affectedPage: string, refresh: () => unknown, coalescedEventCount: number) => void;
  samples: LiveLatencySample[];
  clearSamples: () => void;
};

const LiveConnectionContext = createContext<LiveContextValue | null>(null);
const MAX_BACKOFF_MS = 8000;
const validTimestamp = (value: unknown) => typeof value === "string" && !Number.isNaN(Date.parse(value)) ? value : undefined;

function toLiveEvent(value: unknown): LiveEvent | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.event_type !== "string" || !("payload" in record)) return null;
  const payload = record.payload;
  const payloadRecord = payload && typeof payload === "object" ? payload as Record<string, unknown> : undefined;
  const backendTimestamp = validTimestamp(record.backend_event_at) ?? validTimestamp(record.timestamp) ?? validTimestamp(payloadRecord?.timestamp) ?? validTimestamp(payloadRecord?.action_timestamp) ?? validTimestamp(payloadRecord?.evaluated_at) ?? validTimestamp(payloadRecord?.created_at);
  return {
    eventId: typeof record.event_id === "string" || typeof record.event_id === "number" ? String(record.event_id) : undefined,
    eventType: record.event_type,
    topic: typeof record.topic === "string" ? record.topic : undefined,
    entityType: typeof record.entity_type === "string" ? record.entity_type : undefined,
    entityId: typeof record.entity_id === "string" || typeof record.entity_id === "number" ? String(record.entity_id) : undefined,
    payload,
    receivedAt: new Date().toISOString(),
    receivedPerformanceMs: performance.now(),
    broadcastAt: validTimestamp(record.broadcast_at),
    backendTimestamp,
  };
}

export function LiveConnectionProvider({ children }: { children: ReactNode }) {
  const { authenticated, logout } = useAuth();
  const [status, setStatus] = useState<LiveConnectionStatus>("disconnected");
  const [lastMessageAt, setLastMessageAt] = useState<string | null>(null);
  const [lastBackendEventAt, setLastBackendEventAt] = useState<string | null>(null);
  const [samples, setSamples] = useState<LiveLatencySample[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const stoppedRef = useRef(true);
  const attemptRef = useRef(0);
  const handlersRef = useRef(new Map<string, Set<LiveHandler>>());
  const samplesRef = useRef<LiveLatencySample[]>([]);

  const subscribe = useCallback((eventTypes: string[] | "*", handler: LiveHandler) => {
    const keys = eventTypes === "*" ? ["*"] : eventTypes;
    keys.forEach((key) => {
      const handlers = handlersRef.current.get(key) ?? new Set<LiveHandler>();
      handlers.add(handler);
      handlersRef.current.set(key, handlers);
    });
    return () => keys.forEach((key) => handlersRef.current.get(key)?.delete(handler));
  }, []);

  const measureRefresh = useCallback(async (event: LiveEvent, affectedPage: string, refresh: () => unknown, coalescedEventCount: number) => {
    const refreshStartedAt = new Date().toISOString();
    const startedPerformanceMs = performance.now();
    let refreshOutcome: LiveLatencySample["refreshOutcome"] = "success";
    try { await refresh(); } catch { refreshOutcome = "refresh_failed"; }
    const refreshCompletedAt = new Date().toISOString();
    const completedPerformanceMs = performance.now();
    const websocketToRefreshStartMs = startedPerformanceMs - event.receivedPerformanceMs;
    const websocketToRefreshCompleteMs = completedPerformanceMs - event.receivedPerformanceMs;
    const backendMs = event.backendTimestamp ? Date.parse(event.backendTimestamp) : NaN;
    const receivedMs = Date.parse(event.receivedAt);
    const completedMs = Date.parse(refreshCompletedAt);
    const backendEventToWsMs = Number.isFinite(backendMs) && Number.isFinite(receivedMs) && receivedMs >= backendMs ? receivedMs - backendMs : null;
    const backendEventToRefreshCompleteMs = Number.isFinite(backendMs) && Number.isFinite(completedMs) && completedMs >= backendMs ? completedMs - backendMs : null;
    const crossClockValid = !event.backendTimestamp || (backendEventToWsMs !== null && backendEventToRefreshCompleteMs !== null);
    if (!crossClockValid && refreshOutcome === "success") refreshOutcome = "invalid_timing";
    const sample: LiveLatencySample = { eventId: event.eventId, eventType: event.eventType, backendEventAt: event.backendTimestamp, broadcastAt: event.broadcastAt, wsReceivedAt: event.receivedAt, refreshStartedAt, refreshCompletedAt, affectedPage, refreshOutcome, coalescedEventCount, websocketToRefreshStartMs: event.eventId && websocketToRefreshStartMs >= 0 ? websocketToRefreshStartMs : null, refreshDurationMs: Math.max(0, completedPerformanceMs - startedPerformanceMs), websocketToRefreshCompleteMs: event.eventId && websocketToRefreshCompleteMs >= 0 ? websocketToRefreshCompleteMs : null, backendEventToWsMs, backendEventToRefreshCompleteMs, crossClockValid };
    samplesRef.current = [...samplesRef.current, sample].slice(-100);
    setSamples(samplesRef.current);
  }, []);
  const clearSamples = useCallback(() => { samplesRef.current = []; setSamples([]); }, []);

  useEffect(() => {
    if (!authenticated) {
      stoppedRef.current = true;
      if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      socketRef.current?.close();
      socketRef.current = null;
      setStatus("disconnected");
      return;
    }

    stoppedRef.current = false;
    attemptRef.current = 0;
    const connect = () => {
      if (stoppedRef.current) return;
      const token = getStoredAccessToken();
      if (!token) { setStatus("disconnected"); return; }
      const url = new URL(getApiBaseUrl());
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = "/ws/live";
      url.search = `token=${encodeURIComponent(token)}`;
      setStatus("connecting");
      const socket = new WebSocket(url.toString());
      socketRef.current = socket;
      socket.onopen = () => { attemptRef.current = 0; setStatus("connected"); };
      socket.onmessage = (message) => {
        try {
          const event = toLiveEvent(JSON.parse(message.data as string));
          if (!event) return;
          setLastMessageAt(event.receivedAt);
          if (event.backendTimestamp) setLastBackendEventAt(event.backendTimestamp);
          [...(handlersRef.current.get(event.eventType) ?? []), ...(handlersRef.current.get("*") ?? [])].forEach((handler) => handler(event));
        } catch {
          // Malformed live data is ignored; REST remains the authoritative state source.
        }
      };
      socket.onerror = () => setStatus("error");
      socket.onclose = (event) => {
        socketRef.current = null;
        if (stoppedRef.current) return;
        if (event.code === 1008) { stoppedRef.current = true; setStatus("error"); logout(); return; }
        setStatus("disconnected");
        const delay = Math.min(500 * (2 ** attemptRef.current), MAX_BACKOFF_MS);
        attemptRef.current += 1;
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      stoppedRef.current = true;
      if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [authenticated, logout]);

  const value = useMemo(() => ({ status, lastMessageAt, lastBackendEventAt, subscribe, measureRefresh, samples, clearSamples }), [clearSamples, lastBackendEventAt, lastMessageAt, measureRefresh, samples, status, subscribe]);
  return <LiveConnectionContext.Provider value={value}>{children}</LiveConnectionContext.Provider>;
}

export function useLiveConnection() {
  const context = useContext(LiveConnectionContext);
  if (!context) throw new Error("useLiveConnection must be used inside LiveConnectionProvider");
  return context;
}
