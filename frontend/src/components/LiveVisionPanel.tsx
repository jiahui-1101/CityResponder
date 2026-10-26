import { useState } from "react";
import { Camera, Eye, ShieldCheck, TriangleAlert } from "lucide-react";
import { useLiveVisionFrame, type ModelStatus } from "../hooks/useLiveVisionFrame";
import { Card, LoadingState, StatusBadge } from "./ui";

type VisionView = "ai" | "raw";

const formatTime = (value?: string) => value ? new Date(value).toLocaleTimeString() : "Waiting for a frame";
const statusText = (status?: ModelStatus, shown = true) => {
  if (!shown) return "Not shown in Raw Camera view";
  if (!status || status === "initializing" || status === "warming") return "Warming";
  if (status === "processing") return "Processing";
  if (status === "active") return "Active";
  if (status === "stale") return "Stale";
  if (status === "error") return "Unavailable";
  if (status === "disabled") return "Disabled";
  return "Idle";
};
const predictionSummary = (items: Array<{ class_name: string; confidence: number }>) => {
  const grouped = new Map<string, { count: number; confidence: number }>();
  items.forEach((item) => {
    const current = grouped.get(item.class_name) ?? { count: 0, confidence: 0 };
    grouped.set(item.class_name, { count: current.count + 1, confidence: Math.max(current.confidence, item.confidence) });
  });
  return [...grouped.entries()].map(([className, value]) => ({ className, ...value }));
};

export function LiveVisionPanel({ compact = false }: { compact?: boolean }) {
  const [view, setView] = useState<VisionView>("ai");
  const live = useLiveVisionFrame(view);
  const frame = live.frame;
  const ageMs = frame ? Math.max(0, Date.now() - Date.parse(frame.timestamp)) : Number.POSITIVE_INFINITY;
  const stale = Boolean(frame && ageMs > 3000) || live.phase === "stale";
  const cameraStatus = !frame ? (live.loading ? "Initializing" : "Offline") : stale ? "Stale" : "Live";
  const annotated = frame?.view === "ai-overlay";
  const displayModelStatus = live.overlayState === "processing" ? "processing" : undefined;
  const detectionStatus = statusText(displayModelStatus ?? frame?.detection_status, view === "ai");
  const segmentationStatus = statusText(displayModelStatus ?? frame?.segmentation_status, view === "ai");
  const hasPredictions = Boolean(frame && (frame.detections.length || frame.segmentations.length));
  const hasFreshEmptyResult = Boolean(
    annotated && frame?.detection_status === "active" && frame.segmentation_status === "active" && !hasPredictions,
  );
  const detectionSummary = predictionSummary(frame?.detections ?? []);
  const segmentationSummary = predictionSummary(frame?.segmentations ?? []);

  return <Card className={`live-vision-card${compact ? " compact" : ""}`}>
    <div className="live-vision-heading">
      <div><span className="route-label">Shared Camera 0 · observation only</span><h3><Camera size={17} />Live AI Camera</h3></div>
      <StatusBadge tone={cameraStatus === "Live" ? "success" : cameraStatus === "Offline" ? "danger" : "warning"}>{cameraStatus}</StatusBadge>
    </div>

    <div className="live-vision-controls" role="group" aria-label="Camera display mode">
      <button type="button" className={view === "ai" ? "active" : ""} aria-pressed={view === "ai"} onClick={() => setView("ai")}>AI Overlay</button>
      <button type="button" className={view === "raw" ? "active" : ""} aria-pressed={view === "raw"} onClick={() => setView("raw")}>Raw Camera</button>
      <span>Display controls only</span>
    </div>

    {live.loading && !live.imageUrl ? <LoadingState label={view === "ai" ? "Opening camera and warming models..." : "Opening camera..."} /> : live.imageUrl ? <div className="live-vision-frame-wrap">
      <img className="live-vision-image" src={live.imageUrl} alt={annotated ? "Live camera frame with synchronized YOLO detection and segmentation overlays" : "Live raw USB camera preview"} />
      {frame?.view === "raw-fallback" ? <span className="live-vision-fallback">RAW CAMERA · AI WARMING</span> : null}
      {frame?.view === "ai-overlay" && live.overlayState === "processing" ? <span className="live-vision-fallback">LIVE CAMERA · AI PROCESSING</span> : null}
      {frame?.view === "ai-overlay" && live.overlayState === "stale" ? <span className="live-vision-fallback">LIVE CAMERA · AI STALE</span> : null}
    </div> : <div className="live-vision-unavailable"><TriangleAlert size={20} /><strong>Live camera unavailable</strong><span>{live.error ?? "No fresh camera frame has been returned."}</span></div>}

    <div className="live-vision-ai-status">
      <span><i className={`vision-dot ${frame?.detection_status === "active" ? "online" : "offline"}`} />Detection AI <strong>{detectionStatus}</strong></span>
      <span><i className={`vision-dot ${frame?.segmentation_status === "active" ? "online" : "offline"}`} />Segmentation AI <strong>{segmentationStatus}</strong></span>
      <span><i className={`vision-dot ${live.connection === "connected" ? "online" : "offline"}`} />Stream <strong>{live.connection === "connected" ? "Connected" : live.connection === "reconnecting" ? "Reconnecting" : live.connection}</strong></span>
    </div>

    <div className="live-vision-meta">
      <span><Eye size={13} />Captured {formatTime(frame?.timestamp)}</span>
      <span>{frame ? `${frame.capture_width} × ${frame.capture_height} model crop` : "Waiting for camera"}</span>
      <span>{frame?.source_width && frame.source_height ? `${frame.source_width} × ${frame.source_height} native` : ""}</span>
      <span>{frame ? `${frame.preview_width} × ${frame.preview_height} display` : ""}</span>
      <span>Age {frame ? `${(ageMs / 1000).toFixed(1)} s` : "—"}</span>
    </div>

    <div className="live-vision-meta">
      <span>Camera {frame?.camera_fps.toFixed(1) ?? "—"} FPS</span>
      <span>Displayed {live.displayedFps ? `${live.displayedFps.toFixed(1)} FPS` : "—"}</span>
      <span>Detection {annotated ? `${frame?.detection_fps.toFixed(1)} FPS` : "—"}</span>
      <span>Segmentation {annotated ? `${frame?.segmentation_fps.toFixed(1)} FPS` : "—"}</span>
      <span>Detection latency {annotated && frame?.detection_latency_ms != null ? `${frame.detection_latency_ms.toFixed(0)} ms` : "—"}</span>
      <span>Segmentation latency {annotated && frame?.segmentation_latency_ms != null ? `${frame.segmentation_latency_ms.toFixed(0)} ms` : "—"}</span>
      <span>Inference total {annotated && frame?.inference_latency_ms !== undefined ? `${frame.inference_latency_ms.toFixed(0)} ms` : "—"}</span>
      <span>Transport {frame ? `${Math.round(frame.jpeg_bytes / 1024)} KB JPEG` : "—"}</span>
      <span>Device {annotated ? (frame?.inference_device ?? "Unavailable") : "—"}</span>
      <span>Last AI update {annotated ? formatTime(frame?.processed_at) : "—"}</span>
    </div>

    {annotated && hasPredictions ? <div className="live-vision-prediction-groups">
      <div><strong>Detections</strong><div className="live-vision-predictions">{detectionSummary.length ? detectionSummary.map((item) => <span key={item.className}>{item.className.replaceAll("_", " ")} ×{item.count} · max {item.confidence.toFixed(2)}</span>) : <small>None</small>}</div></div>
      <div><strong>Segmentation</strong><div className="live-vision-predictions">{segmentationSummary.length ? segmentationSummary.map((item) => <span key={item.className}>{item.className.replaceAll("_", " ")} ×{item.count} · max {item.confidence.toFixed(2)}</span>) : <small>None</small>}</div></div>
    </div> : annotated && hasFreshEmptyResult ? <div className="live-vision-meta">No detections in this successful inference frame.</div> : annotated ? <div className="live-vision-warning">Inference unavailable or incomplete; no detection result is being claimed.</div> : null}

    {annotated && frame?.shadow_evaluation ? <div className="live-shadow-panel"><div><strong>LIVE AI SHADOW</strong><StatusBadge tone={frame.shadow_evaluation.status === "OBSERVATIONS_PRESENT" ? "warning" : "neutral"}>{frame.shadow_evaluation.status.replaceAll("_", " ")}</StatusBadge></div><span>Source frame {frame.shadow_evaluation.source_frame_id} · geometry {frame.shadow_evaluation.crop_geometry_version}</span><span>{frame.shadow_evaluation.detections.length} hazard observations · {frame.shadow_evaluation.road_observations.length} road observations</span><span>Mapped physical edges: {frame.shadow_evaluation.mapped_edge_ids.length ? frame.shadow_evaluation.mapped_edge_ids.join(", ") : "NONE — mapping unverified"}</span><small>Incident {String(frame.shadow_evaluation.incident_created)} · reroute {String(frame.shadow_evaluation.route_recalculated)} · MQTT {String(frame.shadow_evaluation.mqtt_published)} · hardware {String(frame.shadow_evaluation.hardware_actuated)}</small></div> : null}

    {stale || live.connection === "reconnecting" ? <div className="live-vision-warning"><TriangleAlert size={14} />Last image is stale while the stream reconnects. Check the timestamp before interpreting overlays.</div> : null}
    {live.error ? <div className="live-vision-warning"><TriangleAlert size={14} />{live.error}</div> : null}
    <div className="live-vision-warning"><TriangleAlert size={14} />ROI overlays are hidden because the active geometry is unverified. No ROI decisions are made.</div>
    <div className="live-vision-privacy"><ShieldCheck size={13} />Observation only · no evidence storage, incident creation, MQTT publishing, dispatch, or actuator actions</div>
  </Card>;
}
