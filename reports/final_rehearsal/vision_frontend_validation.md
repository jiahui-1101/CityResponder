# Vision Frontend Validation

## Implemented

- Role-protected `GET /api/vision/live-frame` endpoint.
- One shared, on-demand `IntegratedVisionPipeline`; no second camera owner is created per viewer.
- Operator and Firefighter pages show the real overhead frame.
- Server-rendered overlays include the locked Building A ROI, detection labels/confidence boxes, and segmentation polygons/labels/confidence when real outputs exist.
- Clear scenes show the clean real frame; detections are never fabricated.
- Metadata identifies Detection V2, Segmentation V1, frame timestamp, and object/mask counts.
- Continuous video is not persisted; the separate incident-evidence cap remains five frames.
- UI unmount aborts pending fetches and revokes object URLs.

## Runtime evidence

- Valid JPEG returned: YES.
- Models reported: `cityresponder_detection_v2` and `cityresponder_segmentation_v1`.
- Tested clear frame detections/masks: 0/0.
- Headless 1920×1080 browser proof: real annotated frame rendered at natural width 1080 with the locked Building A ROI and an explicit stale warning.
- Firefighter 390×844 proof: no horizontal overflow, but the vision panel remained in cold-start state after eight seconds.
- Cold model/camera startup: approximately 14.35 seconds.
- Cached real-frame delivery: approximately 4–33 ms, but cached delivery is not new inference.
- Frame freshness after warm-up was variable in short observations; stable camera-to-dashboard ≤1 second is not proven.
- The previous 10-second worker idle timeout caused repeated cold starts during normal page transitions; it is now 60 seconds.
- UI marks frames older than 1.5 seconds as stale while retaining the last real image.

## Acceptance

The visual proof path exists and reuses the correct pipeline, but current cold-start/freshness evidence does not satisfy the proposal's ≤1 second camera-to-dashboard target. Prior controlled validation also recorded false person and road-obstacle outputs in negative scenes. Vision is therefore **integrated with documented acceptance limitations**, not a final PASS.
