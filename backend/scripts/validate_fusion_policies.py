"""Validation script for Fire Fusion policies (TBD-FUSION-01 through 06)."""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

from app.sensors.schemas import LatestSensorState
from app.vision.schemas import Detection, BoundingBox, FreshnessItem
from app.area_risk.schemas import AreaRiskResult
from app.fusion.policies import (
    FireSensorNormalizationPolicy,
    FireVisionNormalizationPolicy,
    FireTemporalNormalizationPolicy,
    FireHistoricalNormalizationPolicy,
    FireSupportingChannelPolicy,
    FireFusionEngine,
    FireAlarmDecision,
    WindowEvidence,
    build_historical_context,
    is_button_pressed,
    _normalize_sensor,
    MQ2_NORMAL, MQ2_ALARM, DHT22_NORMAL, DHT22_ALARM,
)

now = datetime.now(timezone.utc)
bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)

def fresh(source_type, age=0.1):
    return FreshnessItem(source_type=source_type, available=True, stale=False, age_seconds=age, timestamp=now)

def stale(source_type, age=5.0):
    return FreshnessItem(source_type=source_type, available=True, stale=True, age_seconds=age, timestamp=now)

def unavailable(source_type):
    return FreshnessItem(source_type=source_type, available=False, stale=None, age_seconds=None, timestamp=None)

def mq2_sensor(value):
    return LatestSensorState(sensor_type="MQ2", value=value, available=True, timestamp=now, node_id="test")

def dht22_sensor(value):
    return LatestSensorState(sensor_type="DHT22", value=value, available=True, timestamp=now, node_id="test")

def button_sensor(pressed):
    return LatestSensorState(sensor_type="BUTTON", value=pressed, available=pressed, timestamp=now, node_id="test")


print("=" * 60)
print("TBD-FUSION-01: Sensor Normalization Tests")
print("=" * 60)

# Test normalization clamping
assert _normalize_sensor(500, 500, 2000) == 0.0, "MQ2 at normal should be 0.0"
assert _normalize_sensor(2000, 500, 2000) == 1.0, "MQ2 at alarm should be 1.0"
assert _normalize_sensor(1250, 500, 2000) == 0.5, "MQ2 midpoint should be 0.5"
assert _normalize_sensor(100, 500, 2000) == 0.0, "MQ2 below normal clamped to 0.0"
assert _normalize_sensor(3000, 500, 2000) == 1.0, "MQ2 above alarm clamped to 1.0"

assert _normalize_sensor(30, 30, 50) == 0.0, "DHT22 at normal should be 0.0"
assert _normalize_sensor(50, 30, 50) == 1.0, "DHT22 at alarm should be 1.0"
assert _normalize_sensor(40, 30, 50) == 0.5, "DHT22 midpoint should be 0.5"
assert _normalize_sensor(20, 30, 50) == 0.0, "DHT22 below normal clamped to 0.0"
assert _normalize_sensor(60, 30, 50) == 1.0, "DHT22 above alarm clamped to 1.0"
print("  [PASS] Normalization clamping")

# Test S = max(s_smoke, s_heat)
policy = FireSensorNormalizationPolicy()
score, status = policy.score_with_freshness(
    mq2_sensor(1250), dht22_sensor(40),
    fresh("MQ2"), fresh("DHT22"),
)
assert status == "available"
# s_smoke = 0.5, s_heat = 0.5, max = 0.5
assert score == 0.5, f"Expected 0.5, got {score}"
print("  [PASS] S = max(s_smoke, s_heat)")

# Test stale: one stale uses other
score, status = policy.score_with_freshness(
    mq2_sensor(1250), dht22_sensor(40),
    stale("MQ2"), fresh("DHT22"),
)
assert status == "available"
assert score == 0.5, f"MQ2 stale, should use DHT22=0.5, got {score}"
print("  [PASS] One sensor stale: use the other")

# Test stale: both stale → unavailable
score, status = policy.score_with_freshness(
    mq2_sensor(1250), dht22_sensor(40),
    stale("MQ2"), stale("DHT22"),
)
assert score is None
assert status == "unavailable"
print("  [PASS] Both sensors stale → S unavailable")


print()
print("=" * 60)
print("TBD-FUSION-02: Temporal Consistency Tests")
print("=" * 60)

# 0 evidence windows
t_policy = FireTemporalNormalizationPolicy([])
t = t_policy.score(None, [], [])
assert t == 0.0
print("  [PASS] No evidence → T=0")

# 3 windows, all with evidence
t_policy = FireTemporalNormalizationPolicy([
    WindowEvidence(s_score=0.5),  # S >= 0.20 → evidence
    WindowEvidence(v_score=0.6),  # V >= 0.40 → evidence
    WindowEvidence(button_pressed=True),  # button → evidence
])
t = t_policy.score(None, [], [])
assert t == 1.0, f"Expected 1.0, got {t}"
print("  [PASS] 3/3 evidence → T=1.0")

# 3 windows, 1 with evidence
t_policy = FireTemporalNormalizationPolicy([
    WindowEvidence(s_score=0.1),  # S < 0.20 → no evidence
    WindowEvidence(v_score=0.3),  # V < 0.40 → no evidence
    WindowEvidence(s_score=0.25),  # S >= 0.20 → evidence
])
t = t_policy.score(None, [], [])
expected = 1 / 3
assert abs(t - expected) < 1e-9, f"Expected {expected}, got {t}"
print(f"  [PASS] 1/3 evidence → T={expected:.4f}")


print()
print("=" * 60)
print("TBD-FUSION-03: Vision Normalization Tests")
print("=" * 60)

v_policy = FireVisionNormalizationPolicy()

# Fire 0.8, Smoke 0.6, Person 0.9 → V = max(0.8, 0.6) = 0.8
v = v_policy.score([
    Detection(class_name="Fire", confidence=0.8, bounding_box=bbox),
    Detection(class_name="Smoke", confidence=0.6, bounding_box=bbox),
    Detection(class_name="Person", confidence=0.9, bounding_box=bbox),
], None)
assert v == 0.8, f"Expected 0.8, got {v}"
print("  [PASS] V = max(fire, smoke), Person excluded")

# Below minimum confidence (0.50)
v = v_policy.score([
    Detection(class_name="Fire", confidence=0.3, bounding_box=bbox),
    Detection(class_name="Smoke", confidence=0.4, bounding_box=bbox),
], None)
assert v == 0.0, f"Expected 0.0 (below min confidence), got {v}"
print("  [PASS] Below min confidence → V=0.0")

# No detections → V=0
v = v_policy.score([], None)
assert v == 0.0
print("  [PASS] No detections → V=0.0")


print()
print("=" * 60)
print("TBD-FUSION-04: Historical Baseline Tests")
print("=" * 60)

# Cold start (no history) → H=0
h_ctx = build_historical_context(None)
h_policy = FireHistoricalNormalizationPolicy(None)
h = h_policy.score(h_ctx)
assert h == 0.0
print("  [PASS] Cold start (no area risk) → H=0")

# Area risk score = 60 → H = 0.6
area_risk = AreaRiskResult(
    area_id="test", status="calculated", score=60.0,
    window_start=now, window_end=now, calculated_at=now,
)
h_ctx = build_historical_context(area_risk)
h_policy = FireHistoricalNormalizationPolicy(area_risk)
h = h_policy.score(h_ctx)
assert abs(h - 0.6) < 1e-9, f"Expected 0.6, got {h}"
print("  [PASS] Area risk 60 → H=0.6")


print()
print("=" * 60)
print("TBD-FUSION-05: Supporting Channels Tests")
print("=" * 60)

# MQ2=0.4, DHT22=0.1, Camera=0.6, Button=off → 2 supporting (MQ2, Camera)
sp = FireSupportingChannelPolicy(
    mq2_score=0.4, dht22_score=0.1, camera_score=0.6,
    button_pressed=False,
    mq2_available=True, dht22_available=True, camera_available=True,
)
assert sp.count_supporting() == 2, f"Expected 2, got {sp.count_supporting()}"
print("  [PASS] 2 supporting: MQ2 + Camera (DHT22 below 0.30)")

# Button pressed → +1
sp = FireSupportingChannelPolicy(
    mq2_score=0.4, dht22_score=0.1, camera_score=0.6,
    button_pressed=True,
    mq2_available=True, dht22_available=True, camera_available=True,
)
assert sp.count_supporting() == 3
print("  [PASS] Button adds 1 supporting channel")


print()
print("=" * 60)
print("TBD-FUSION-06: Manual Button Tests")
print("=" * 60)

assert is_button_pressed(button_sensor(True)) is True
assert is_button_pressed(button_sensor(False)) is False
assert is_button_pressed(button_sensor(1)) is True
assert is_button_pressed(button_sensor(0)) is False
print("  [PASS] Button press detection")


print()
print("=" * 60)
print("Core Formula: C = 100 * (0.30*S + 0.20*T + 0.35*V + 0.15*H)")
print("=" * 60)

engine = FireFusionEngine(
    area_risk_result=area_risk,  # score=60 → H=0.6
    window_evidence_history=[
        WindowEvidence(s_score=0.5, v_score=0.7),  # evidence
        WindowEvidence(s_score=0.6, v_score=0.8),  # evidence
    ],
)
result = engine.evaluate(
    mq2=mq2_sensor(1250),       # s_smoke = 0.5
    dht22=dht22_sensor(40),     # s_heat = 0.5
    mq2_freshness=fresh("MQ2"),
    dht22_freshness=fresh("DHT22"),
    detections=[
        Detection(class_name="Fire", confidence=0.7, bounding_box=bbox),
        Detection(class_name="Smoke", confidence=0.6, bounding_box=bbox),
    ],
    vision_freshness=fresh("vision"),
    button=button_sensor(False),
)

assert result.status == "calculated"
assert result.s_score == 0.5
assert result.v_score == 0.7
assert result.h_score == 0.6

# T: 3 windows all have evidence (current has S=0.5 >= 0.20 → evidence)
# So T = 3/3 = 1.0
assert result.t_score == 1.0

# C = 100 * (0.30*0.5 + 0.20*1.0 + 0.35*0.7 + 0.15*0.6)
# C = 100 * (0.15 + 0.20 + 0.245 + 0.09) = 100 * 0.685 = 68.5
expected_c = 100 * (0.30*0.5 + 0.20*1.0 + 0.35*0.7 + 0.15*0.6)
assert abs(result.confidence - expected_c) < 1e-9, f"Expected {expected_c}, got {result.confidence}"
print(f"  [PASS] C = {result.confidence:.2f} (expected {expected_c:.2f})")
print(f"  S={result.s_score}, T={result.t_score}, V={result.v_score}, H={result.h_score}")
print(f"  Supporting channels: {result.supporting_count}")


print()
print("=" * 60)
print("Three-Window Alarm Decision")
print("=" * 60)

# Create 3 identical high-alarm results
windows = []
for _ in range(3):
    r = engine.evaluate(
        mq2=mq2_sensor(1800),       # s_smoke ≈ 0.867
        dht22=dht22_sensor(48),      # s_heat = 0.90
        mq2_freshness=fresh("MQ2"),
        dht22_freshness=fresh("DHT22"),
        detections=[
            Detection(class_name="Fire", confidence=0.85, bounding_box=bbox),
        ],
        vision_freshness=fresh("vision"),
        button=button_sensor(False),
    )
    windows.append(r)

alarm = FireAlarmDecision(windows)
print(f"  All calculated: {alarm.all_calculated}")
print(f"  All confidence >= 40: {alarm.all_confidence_pass}")
print(f"  All >= 2 supporting: {alarm.all_supporting_pass}")
print(f"  Should alarm: {alarm.should_alarm}")
for w in windows:
    print(f"    Window C={w.confidence:.2f}, supporting={w.supporting_count}")
assert alarm.should_alarm is True, "Should trigger alarm"
print("  [PASS] Alarm triggered correctly")


print()
print("=" * 60)
print("All Fire Fusion policy tests PASSED!")
print("=" * 60)
