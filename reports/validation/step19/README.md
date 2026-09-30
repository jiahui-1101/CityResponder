# Step 19 Vision + Physical Hardware acceptance framework

This directory contains recorder templates only. Empty observations and cycles
are intentionally not PASS results.

## Authoritative targets

- YOLO object detection: at least 5 inferences/second.
- YOLO segmentation: 2 inferences/second.
- Building A ROI: at least 280 x 180 pixels.
- Minimum road width: at least 120 pixels.
- Hazard dimension MAE: at most 1 cm.
- Fire verification: at least 40 controlled scenarios, correctness at least 85%.
- False dispatch during non-fire scenarios: at most 10%.
- Physical ACK success: at least 95% across 20 complete end-to-end cycles.

## Usage

Fill the templates only with real camera/model and AC1 observations, then run:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m scripts.validate_vision_acceptance `
  --vision ..\reports\validation\step19\vision_scenarios.template.json `
  --hardware ..\reports\validation\step19\hardware_cycles.template.json `
  --output ..\reports\validation\step19\step19_acceptance.json
Pop-Location
```

The generated report must distinguish MQTT publish, actuator ACK, and visible
physical behavior. Step 16–18 reports are referenced only; mock ACKs are not
hardware evidence. Production policies and topology remain TBD_SOURCE.
