import { readFileSync } from "node:fs";

const panel = readFileSync(new URL("../src/components/LiveVisionPanel.tsx", import.meta.url), "utf8");
const hook = readFileSync(new URL("../src/hooks/useLiveVisionFrame.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles/global.css", import.meta.url), "utf8");
const failures = [];

const requireText = (source, text, message) => {
  if (!source.includes(text)) failures.push(message);
};

requireText(css, "object-fit: contain", "camera image must preserve its aspect ratio");
requireText(panel, "RAW CAMERA · AI WARMING", "raw fallback state must be visible");
requireText(panel, "LIVE CAMERA · AI PROCESSING", "AI processing state must be visible without replacing the image");
requireText(panel, "LIVE CAMERA · AI STALE", "stale AI overlay state must be visible");
requireText(panel, "No detections in this successful inference frame.", "empty successful inference must be explicit");
requireText(panel, "Live camera unavailable", "camera offline state must be visible");
requireText(panel, "Last image is stale", "stale frame state must be visible");
requireText(panel, "ROI overlays are hidden", "unverified ROI state must be visible");
requireText(panel, "displayedFps", "browser delivered FPS must use measured metadata");
requireText(panel, "inference_device", "inference device must use backend metadata");
requireText(panel, "detection_latency_ms", "detection latency must use backend metadata");
requireText(panel, "segmentation_latency_ms", "segmentation latency must use backend metadata");
requireText(panel, "LIVE AI SHADOW", "live AI shadow state must be visible");
requireText(panel, "NONE — mapping unverified", "unverified physical edge mapping must remain explicit");
requireText(hook, "pendingFrame = null", "binary frames must consume exactly one metadata record");
requireText(hook, "URL.revokeObjectURL", "replaced JPEG object URLs must be released");
requireText(hook, "preloaded.onload", "JPEGs must decode before replacing the displayed image");
requireText(hook, "requestAnimationFrame", "old object URLs must survive through the image swap paint");
requireText(hook, "discardNextBinary", "out-of-order metadata and JPEG pairs must be discarded together");
requireText(hook, "Math.min(500 * (2 ** reconnectAttempt), 10000)", "reconnects must use bounded backoff");
if (/Hazard Confirmed/i.test(panel)) failures.push("YOLO predictions must not be presented as confirmed hazards");

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Live vision rendering and lifecycle contract PASS");
