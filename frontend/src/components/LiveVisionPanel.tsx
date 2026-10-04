import { Camera, Eye, ShieldCheck, TriangleAlert } from "lucide-react";
import { useLiveVisionFrame } from "../hooks/useLiveVisionFrame";
import { Card, LoadingState, StatusBadge } from "./ui";

const formatTime = (value: string | null) => value ? new Date(value).toLocaleTimeString() : "No frame timestamp";

export function LiveVisionPanel({ compact = false }: { compact?: boolean }) {
  const live = useLiveVisionFrame();
  const frameAgeMs = live.timestamp ? Date.now() - Date.parse(live.timestamp) : Number.POSITIVE_INFINITY;
  const stale = Boolean(live.imageUrl && frameAgeMs > 5000 && live.phase !== "reconnecting");
  const phase = stale ? "stale" : live.phase;
  const statusLabel = phase === "initializing" ? "Initializing AI camera" : phase === "live" ? "Live" : phase === "stale" ? "Stale" : phase === "reconnecting" ? "Reconnecting" : "Unavailable";
  return <Card className={`live-vision-card${compact ? " compact" : ""}`}>
    <div className="live-vision-heading"><div><span className="route-label">Shared real camera pipeline</span><h3><Camera size={17} />Live AI view</h3></div><StatusBadge tone={phase === "live" ? "success" : phase === "unavailable" ? "danger" : "warning"}>{statusLabel}</StatusBadge></div>
    {phase === "initializing" && !live.imageUrl ? <LoadingState label="Camera warming up..." /> : live.imageUrl ? <img className="live-vision-image" src={live.imageUrl} alt="Real CityResponder overhead camera with current AI annotations" /> : <div className="live-vision-unavailable"><TriangleAlert size={20} /><strong>Live camera unavailable</strong><span>{live.error ?? "No real frame has been returned."}</span></div>}
    <div className="live-vision-meta"><span><Eye size={13} />{formatTime(live.timestamp)}</span><span>Detection V2 · {live.detectionCount} object(s)</span><span>Segmentation V1 · {live.segmentationCount} mask(s)</span></div>
    {phase === "stale" || phase === "reconnecting" ? <div className="live-vision-warning"><TriangleAlert size={14} />{live.error ? `${live.error}. ` : "Frame freshness exceeds 5 seconds. "}Last real frame remains visible while the shared pipeline recovers.</div> : null}
    <div className="live-vision-privacy"><ShieldCheck size={13} />Display-only shared stream · continuous video is not stored · selected incident evidence remains capped at five frames</div>
  </Card>;
}
