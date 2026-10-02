"""Validation script for the integrated Severity Pipeline with orchestration."""

import sys
sys.path.insert(0, ".")

from app.vision.schemas import Detection, BoundingBox, ROI, PerceptionSnapshot, VisionDetectionMessage, FrameMetadata, PerceptionFreshnessResponse, FreshnessItem
from app.sensors.schemas import LatestSensorState
from app.severity.policies import (
    SeverityComponentPolicyProvider,
    SeverityPolicyClassification,
)
from app.severity.service import build_severity_input
from app.severity.calculator import calculate_severity_score
from app.severity.classification import classify_severity
from app.fusion.schemas import ConfirmationSequenceResult

def make_snapshot(mq2: float, dht22: float, has_person: bool) -> PerceptionSnapshot:
    hazard_zone = ROI(name="hazard_zone", x=0, y=0, width=400, height=300)
    
    detections = []
    if has_person:
        # Confidence >= 0.50 and center inside hazard_zone
        detections.append(Detection(
            class_name="Person",
            confidence=0.8,
            bounding_box=BoundingBox(x1=100, y1=100, x2=200, y2=200)
        ))
    
    # We will pass the mock snapshot fields
    snapshot = PerceptionSnapshot.model_construct(
        sensors=[
            LatestSensorState.model_construct(sensor_type="MQ2", value=str(mq2), available=True),
            LatestSensorState.model_construct(sensor_type="DHT22", value=str(dht22), available=True),
        ],
        detection=VisionDetectionMessage.model_construct(
            frame=FrameMetadata.model_construct(frame_id="frame1", timestamp="2026-10-02T12:00:00Z"),
            detections=detections,
        ),
        person_in_hazard=has_person,
        freshness=PerceptionFreshnessResponse.model_construct(
            detection=FreshnessItem.model_construct(available=True, stale=False),
        )
    )
    return snapshot


def run_pipeline_test():
    print("=" * 60)
    print("Testing Pipeline Integration")
    print("=" * 60)

    hazard_zone = ROI(name="hazard_zone", x=0, y=0, width=400, height=300)
    provider = SeverityComponentPolicyProvider(zone_label="normal-risk", hazard_zone=hazard_zone)
    policy = SeverityPolicyClassification()
    
    # ---------------------------------------------------------
    # Test 1: Person in hazard zone -> CRITICAL override
    # ---------------------------------------------------------
    snapshot = make_snapshot(mq2=1000, dht22=35, has_person=True)
    
    # Assume fusion confirmed it
    confirmation = ConfirmationSequenceResult.model_construct(incident_confirmed=True)
    
    sev_input = build_severity_input(
        snapshot,
        confirmation=confirmation,
        component_provider=provider
    )
    
    # Check that input mapped the values
    assert sev_input.a == 0.0
    assert sev_input.s == 0.3333333333333333 # (1000-500)/1500
    assert sev_input.t == 0.25 # (35-30)/20
    assert sev_input.p == 1.0
    assert sev_input.z == 0.60
    assert sev_input.critical_override_signal is True
    
    score_result = calculate_severity_score(sev_input)
    assert score_result.status == "calculated"
    
    classification_result = classify_severity(score_result, policy)
    assert classification_result.status == "overridden_critical"
    assert classification_result.final_severity == "CRITICAL"
    print("  [PASS] Integration Test 1: P=1 triggers CRITICAL override through classification pipeline")

    # ---------------------------------------------------------
    # Test 2: Core calculation (LOW severity)
    # ---------------------------------------------------------
    snapshot2 = make_snapshot(mq2=1250, dht22=40, has_person=False)
    
    sev_input2 = build_severity_input(
        snapshot2,
        confirmation=confirmation,
        component_provider=provider
    )
    
    assert sev_input2.p == 0.0
    assert sev_input2.critical_override_signal is False
    
    score_result2 = calculate_severity_score(sev_input2)
    # R = 100 * (0.30*0 + 0.20*0.5 + 0.20*0.5 + 0.20*0 + 0.10*0.60) = 26.0
    assert abs(score_result2.severity_score - 26.0) < 1e-6
    
    classification_result2 = classify_severity(score_result2, policy)
    assert classification_result2.status == "classified"
    assert classification_result2.final_severity == "LOW"
    print(f"  [PASS] Integration Test 2: Calculated R={score_result2.severity_score:.2f} classified as {classification_result2.final_severity}")

    print("All integration tests passed.")

if __name__ == "__main__":
    run_pipeline_test()
