import { useEffect, useRef, useState } from "react";
import { API_BASE_URL, getStoredAccessToken } from "../api/client";

export type LiveVisionState = {
  imageUrl: string | null;
  frameId: string | null;
  timestamp: string | null;
  detectionModel: string;
  segmentationModel: string;
  detectionCount: number;
  segmentationCount: number;
  loading: boolean;
  updating: boolean;
  error: string | null;
  phase: "initializing" | "live" | "stale" | "reconnecting" | "unavailable";
};

const initialState: LiveVisionState = {
  imageUrl: null,
  frameId: null,
  timestamp: null,
  detectionModel: "unknown",
  segmentationModel: "unknown",
  detectionCount: 0,
  segmentationCount: 0,
  loading: true,
  updating: false,
  error: null,
  phase: "initializing",
};

export function useLiveVisionFrame(enabled = true) {
  const [state, setState] = useState<LiveVisionState>(initialState);
  const currentUrl = useRef<string | null>(null);
  const etag = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let timer: number | null = null;
    const controller = new AbortController();

    const load = async () => {
      setState((current) => ({ ...current, updating: current.imageUrl !== null }));
      let nextDelayMs = 1000;
      try {
        const token = getStoredAccessToken();
        const response = await fetch(`${API_BASE_URL}/api/vision/live-frame`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(etag.current ? { "If-None-Match": etag.current } : {}),
          },
          cache: "no-store",
          signal: controller.signal,
        });
        if (response.status === 304) {
          setState((current) => ({
            ...current,
            updating: false,
            phase: current.timestamp && Date.now() - Date.parse(current.timestamp) > 1500 ? "stale" : "live",
          }));
          return;
        }
        if (!response.ok) {
          let detail = "Live vision unavailable";
          try {
            const body = await response.json() as { detail?: string };
            if (body.detail) detail = body.detail;
          } catch { /* retain the controlled fallback */ }
          if (response.status === 503 && detail.toLowerCase().includes("warming")) {
            nextDelayMs = 2000;
            setState((current) => ({ ...current, loading: current.imageUrl === null, updating: false, error: null, phase: "initializing" }));
            return;
          }
          throw new Error(`${response.status}: ${detail}`);
        }
        const blob = await response.blob();
        if (stopped) return;
        const nextUrl = URL.createObjectURL(blob);
        const previousUrl = currentUrl.current;
        currentUrl.current = nextUrl;
        etag.current = response.headers.get("ETag");
        setState({
          imageUrl: nextUrl,
          frameId: response.headers.get("X-CityResponder-Frame-Id"),
          timestamp: response.headers.get("X-CityResponder-Frame-Timestamp"),
          detectionModel: response.headers.get("X-CityResponder-Detection-Model") ?? "unknown",
          segmentationModel: response.headers.get("X-CityResponder-Segmentation-Model") ?? "unknown",
          detectionCount: Number(response.headers.get("X-CityResponder-Detection-Count") ?? 0),
          segmentationCount: Number(response.headers.get("X-CityResponder-Segmentation-Count") ?? 0),
          loading: false,
          updating: false,
          error: null,
          phase: "live",
        });
        if (previousUrl) URL.revokeObjectURL(previousUrl);
      } catch (caught) {
        if (stopped || controller.signal.aborted) return;
        setState((current) => ({
          ...current,
          loading: false,
          updating: false,
          error: caught instanceof Error ? caught.message : "Live vision unavailable",
          phase: current.imageUrl ? "reconnecting" : "unavailable",
        }));
        nextDelayMs = 1500;
      } finally {
        if (!stopped) timer = window.setTimeout(load, nextDelayMs);
      }
    };

    void load();
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== null) window.clearTimeout(timer);
      if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
      currentUrl.current = null;
      etag.current = null;
    };
  }, [enabled]);

  return state;
}
