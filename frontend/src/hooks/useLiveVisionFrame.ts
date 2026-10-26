import { useEffect, useState } from "react";
import { getApiBaseUrl, getStoredAccessToken } from "../api/client";

export type VisionDisplayMode = "ai-overlay" | "raw" | "raw-fallback";
export type ModelStatus = "initializing" | "warming" | "processing" | "active" | "stale" | "error" | "idle" | "disabled";

export type LiveVisionFrame = {
  view: VisionDisplayMode;
  sequence: number;
  frame_id: string;
  inference_source_frame_id?: string;
  timestamp: string;
  processed_at?: string;
  frame_age_ms: number;
  capture_width: number;
  capture_height: number;
  source_width?: number;
  source_height?: number;
  crop_origin_x?: number;
  crop_origin_y?: number;
  crop_right_x?: number;
  crop_bottom_y?: number;
  crop_geometry_version?: string;
  preview_width: number;
  preview_height: number;
  camera_fps: number;
  capture_latency_ms?: number;
  resize_latency_ms?: number;
  jpeg_encode_ms?: number;
  jpeg_bytes: number;
  detection_status: ModelStatus;
  segmentation_status: ModelStatus;
  detection_fps: number;
  segmentation_fps: number;
  detection_latency_ms: number | null;
  segmentation_latency_ms: number | null;
  inference_latency_ms?: number;
  inference_device?: string;
  detections: Array<{ class_name: string; confidence: number }>;
  segmentations: Array<{ class_name: string; confidence: number }>;
  roi_status: "unverified";
  roi_overlay: "not_drawn";
  inference_error?: string | null;
  shadow_evaluation?: {
    mode: "LIVE_AI_SHADOW";
    status: string;
    source_frame_id: string;
    source_timestamp: string;
    processed_at: string;
    crop_geometry_version: string;
    detections: Array<{ class_name: string; confidence: number }>;
    road_observations: Array<{ class_name: string; confidence: number }>;
    mapped_edge_ids: string[];
    incident_created: false;
    route_recalculated: false;
    mqtt_published: false;
    hardware_actuated: false;
    warnings: string[];
  };
};

export type LiveVisionState = {
  imageUrl: string | null;
  frame: LiveVisionFrame | null;
  loading: boolean;
  connection: "connecting" | "connected" | "reconnecting" | "disconnected" | "error";
  error: string | null;
  phase: "initializing" | "live" | "stale" | "unavailable";
  displayedFps: number;
  overlayState: "warming" | "active" | "processing" | "stale" | "unavailable";
};

const initialState: LiveVisionState = {
  imageUrl: null,
  frame: null,
  loading: true,
  connection: "connecting",
  error: null,
  phase: "initializing",
  displayedFps: 0,
  overlayState: "warming",
};

export function useLiveVisionFrame(view: "ai" | "raw" = "ai") {
  const [state, setState] = useState<LiveVisionState>(initialState);

  useEffect(() => {
    let stopped = false;
    let reconnectTimer: number | null = null;
    let staleTimer: number | null = null;
    let reconnectAttempt = 0;
    let currentSocket: WebSocket | null = null;
    let currentUrl: string | null = null;
    let pendingFrame: LiveVisionFrame | null = null;
    let discardNextBinary = false;
    let displayedAt: number[] = [];
    let lastAiSequence = -1;
    let lastRawSequence = -1;
    let decodeGeneration = 0;
    let decodingUrl: string | null = null;
    const retiringUrls = new Set<string>();

    const connect = () => {
      if (stopped) return;
      const token = getStoredAccessToken();
      if (!token) {
        window.dispatchEvent(new Event("cityresponder:unauthorized"));
        setState((current) => ({ ...current, loading: false, connection: "disconnected", phase: "unavailable", error: "Sign in to view the camera." }));
        return;
      }

      const url = new URL(getApiBaseUrl() || window.location.origin, window.location.origin);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = "/ws/live";
      url.search = "";
      setState((current) => ({ ...current, connection: reconnectAttempt ? "reconnecting" : "connecting", loading: current.imageUrl === null }));

      const socket = new WebSocket(url.toString());
      currentSocket = socket;
      socket.binaryType = "blob";
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "authenticate", channel: "vision", view, token }));
      };
      socket.onmessage = (message) => {
        if (typeof message.data === "string") {
          try {
            const payload = JSON.parse(message.data) as { event_type?: string; payload?: Partial<LiveVisionFrame> & { status?: string; error?: string } };
            if (payload.event_type === "vision_stream_authenticated") {
              reconnectAttempt = 0;
              setState((current) => ({ ...current, connection: "connected", error: null }));
            } else if (payload.event_type === "vision_frame" && payload.payload?.frame_id) {
              const candidate = payload.payload as LiveVisionFrame;
              const ai = candidate.view === "ai-overlay";
              const previousSequence = ai ? lastAiSequence : lastRawSequence;
              if (Number.isFinite(candidate.sequence) && candidate.sequence <= previousSequence) {
                pendingFrame = null;
                discardNextBinary = true;
              } else {
                pendingFrame = candidate;
                discardNextBinary = false;
              }
            } else if (payload.event_type === "vision_stream_status") {
              const status = payload.payload as typeof payload.payload & {
                overlay_state?: LiveVisionState["overlayState"];
                inference?: { detection?: ModelStatus; segmentation?: ModelStatus; error?: string | null };
              };
              setState((current) => ({
                ...current,
                connection: current.connection === "error" ? "error" : "connected",
                overlayState: status.overlay_state ?? current.overlayState,
                phase: status.overlay_state === "stale" ? "stale" : current.phase,
                error: status.inference?.error ?? status.error ?? current.error,
                frame: current.frame && status.inference ? {
                  ...current.frame,
                  detection_status: status.inference.detection ?? current.frame.detection_status,
                  segmentation_status: status.inference.segmentation ?? current.frame.segmentation_status,
                } : current.frame,
              }));
            } else if (payload.event_type === "vision_status" && payload.payload?.error) {
              setState((current) => ({ ...current, loading: false, phase: current.imageUrl ? "stale" : "unavailable", error: payload.payload?.error ?? "Camera stream unavailable" }));
            }
          } catch {
            setState((current) => ({ ...current, error: "Camera stream sent an unreadable status." }));
          }
          return;
        }

        const metadata = pendingFrame;
        pendingFrame = null;
        const blob = message.data instanceof Blob ? message.data : new Blob([message.data], { type: "image/jpeg" });
        if (discardNextBinary) {
          discardNextBinary = false;
          return;
        }
        if (!metadata || blob.size === 0 || blob.size > 1_000_000) {
          setState((current) => ({ ...current, loading: false, connection: "error", phase: current.imageUrl ? "stale" : "unavailable", error: "Camera stream frame was missing metadata or exceeded the size limit." }));
          return;
        }
        const nextUrl = URL.createObjectURL(blob);
        if (decodingUrl) URL.revokeObjectURL(decodingUrl);
        decodingUrl = nextUrl;
        const generation = ++decodeGeneration;
        const preloaded = new Image();
        preloaded.onload = () => {
          if (stopped || generation !== decodeGeneration || decodingUrl !== nextUrl) {
            URL.revokeObjectURL(nextUrl);
            return;
          }
          decodingUrl = null;
          const previousUrl = currentUrl;
          currentUrl = nextUrl;
          if (metadata.view === "ai-overlay") lastAiSequence = metadata.sequence;
          else lastRawSequence = metadata.sequence;
          const now = performance.now();
          displayedAt = [...displayedAt.filter((value) => now - value <= 5000), now];
          const displayedFps = displayedAt.length > 1
            ? ((displayedAt.length - 1) * 1000) / (displayedAt[displayedAt.length - 1] - displayedAt[0])
            : 0;
          setState((current) => ({
            ...current,
            imageUrl: nextUrl,
            frame: metadata,
            loading: false,
            connection: "connected",
            overlayState: metadata.view === "ai-overlay" ? "active" : "warming",
            error: metadata.inference_error ?? null,
            phase: Date.now() - Date.parse(metadata.timestamp) > 3000 ? "stale" : "live",
            displayedFps,
          }));
          if (previousUrl) {
            retiringUrls.add(previousUrl);
            window.requestAnimationFrame(() => {
              window.requestAnimationFrame(() => {
                URL.revokeObjectURL(previousUrl);
                retiringUrls.delete(previousUrl);
              });
            });
          }
        };
        preloaded.onerror = () => {
          if (decodingUrl === nextUrl) decodingUrl = null;
          URL.revokeObjectURL(nextUrl);
          setState((current) => ({ ...current, error: "Camera JPEG could not be decoded." }));
        };
        preloaded.src = nextUrl;
      };
      socket.onerror = () => setState((current) => ({ ...current, connection: "error", loading: current.imageUrl === null }));
      socket.onclose = (event) => {
        if (currentSocket === socket) currentSocket = null;
        if (stopped) return;
        if (event.code === 1008) {
          window.dispatchEvent(new Event("cityresponder:unauthorized"));
          setState((current) => ({ ...current, connection: "error", loading: false, phase: current.imageUrl ? "stale" : "unavailable", error: "Camera stream authentication or origin validation failed." }));
          return;
        }
        setState((current) => ({ ...current, connection: "reconnecting", loading: current.imageUrl === null, phase: current.imageUrl ? "stale" : "initializing" }));
        const delay = Math.min(500 * (2 ** reconnectAttempt), 10000);
        reconnectAttempt += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    staleTimer = window.setInterval(() => {
      setState((current) => {
        if (!current.frame) return current;
        const stale = Date.now() - Date.parse(current.frame.timestamp) > 3000;
        return { ...current, phase: stale ? "stale" : current.phase === "initializing" ? "live" : current.phase };
      });
    }, 500);

    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (staleTimer !== null) window.clearInterval(staleTimer);
      currentSocket?.close();
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      if (decodingUrl) URL.revokeObjectURL(decodingUrl);
      retiringUrls.forEach((url) => URL.revokeObjectURL(url));
      retiringUrls.clear();
      currentUrl = null;
      decodingUrl = null;
      pendingFrame = null;
      displayedAt = [];
    };
  }, [view]);

  return state;
}
