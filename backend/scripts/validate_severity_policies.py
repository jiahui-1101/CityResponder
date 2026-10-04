"""Validation script for Severity policies (TBD-SEV-01 through 06)."""

import sys
sys.path.insert(0, ".")

from app.vision.schemas import Detection, BoundingBox, ROI
from app.severity.policies import (
    normalize_smoke_score,
    normalize_t_heat_score,
    calculate_fire_extent_score,
    evaluate_person_in_hazard,
    get_zone_vulnerability,
    classify_severity_band,
    calculate_severity,
    SEVERITY_WEIGHT_A, SEVERITY_WEIGHT_S, SEVERITY_WEIGHT_T_HEAT,
    SEVERITY_WEIGHT_P, SEVERITY_WEIGHT_Z,
    SEV_MQ2_NORMAL, SEV_MQ2_ALARM,
    SEV_DHT22_NORMAL, SEV_DHT22_ALARM,
)

bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)
hazard = ROI(name="hazard_zone", x=0, y=0, width=400, height=300)

print("=" * 60)
print("TBD-SEV-02: Smoke Score (S) - Pure MQ-2")
print("=" * 60)

assert normalize_smoke_score(500) == 0.0, "MQ2 at normal should be 0.0"
assert normalize_smoke_score(2000) == 1.0, "MQ2 at alarm should be 1.0"
assert normalize_smoke_score(1250) == 0.5, "MQ2 midpoint should be 0.5"
assert normalize_smoke_score(100) == 0.0, "MQ2 below normal clamped to 0.0"
assert normalize_smoke_score(3000) == 1.0, "MQ2 above alarm clamped to 1.0"
print("  [PASS] S normalization (pure MQ-2)")


print()
print("=" * 60)
print("TBD-SEV-03: Temperature Score (T_heat) - Pure DHT22")
print("=" * 60)

assert normalize_t_heat_score(30) == 0.0, "DHT22 at normal should be 0.0"
assert normalize_t_heat_score(40) == 1.0, "DHT22 at alarm should be 1.0"
assert normalize_t_heat_score(35) == 0.5, "DHT22 midpoint should be 0.5"
assert normalize_t_heat_score(20) == 0.0, "DHT22 below normal clamped to 0.0"
assert normalize_t_heat_score(50) == 1.0, "DHT22 above alarm clamped to 1.0"
print("  [PASS] T_heat normalization (pure DHT22)")


print()
print("=" * 60)
print("TBD-SEV-01: Fire Extent Score (A) - Pixel Ratio")
print("=" * 60)

# Fire bbox = 100x100=10000, hazard = 400x300=120000
# A = 10000/120000 = 0.0833...
fire_det = Detection(class_name="Fire", confidence=0.8, bounding_box=bbox)
a = calculate_fire_extent_score([fire_det], hazard)
expected_a = (100 * 100) / (400 * 300)
assert abs(a - expected_a) < 1e-6, f"Expected {expected_a:.6f}, got {a}"
print(f"  [PASS] A = {a:.6f} (100x100 fire in 400x300 hazard)")

# No fire detections -> A = 0
a = calculate_fire_extent_score([], hazard)
assert a == 0.0
print("  [PASS] No fire detections -> A = 0.0")

# Large fire covering full hazard -> clamped to 1.0
large_fire = Detection(
    class_name="Fire", confidence=0.9,
    bounding_box=BoundingBox(x1=0, y1=0, x2=500, y2=400),
)
a = calculate_fire_extent_score([large_fire], hazard)
assert a == 1.0
print("  [PASS] Large fire clamped to A = 1.0")


print()
print("=" * 60)
print("TBD-SEV-04: Person in Hazard Zone (P)")
print("=" * 60)

# Person with confidence >= 0.50 and center inside hazard
person_inside = Detection(
    class_name="Person", confidence=0.8,
    bounding_box=BoundingBox(x1=100, y1=100, x2=200, y2=200),  # center=(150,150) inside hazard
)
assert evaluate_person_in_hazard([person_inside], hazard) is True
print("  [PASS] Person inside hazard zone -> P=1")

# Person with confidence < 0.50 -> ignored
person_low_conf = Detection(
    class_name="Person", confidence=0.3,
    bounding_box=BoundingBox(x1=100, y1=100, x2=200, y2=200),
)
assert evaluate_person_in_hazard([person_low_conf], hazard) is False
print("  [PASS] Person below confidence 0.50 -> P=0")

# Person outside hazard zone
person_outside = Detection(
    class_name="Person", confidence=0.9,
    bounding_box=BoundingBox(x1=500, y1=500, x2=600, y2=600),  # center=(550,550) outside
)
assert evaluate_person_in_hazard([person_outside], hazard) is False
print("  [PASS] Person outside hazard zone -> P=0")


print()
print("=" * 60)
print("TBD-SEV-05: Zone Vulnerability (Z)")
print("=" * 60)

assert get_zone_vulnerability("low-risk") == 0.30
assert get_zone_vulnerability("normal-risk") == 0.60
assert get_zone_vulnerability("high-risk") == 1.00
assert get_zone_vulnerability("Low") == 0.30    # alias
assert get_zone_vulnerability("High") == 1.00   # alias
print("  [PASS] Z prototype dictionary mappings")


print()
print("=" * 60)
print("TBD-SEV-06: Severity Bands")
print("=" * 60)

assert classify_severity_band(0) == "LOW"
assert classify_severity_band(15) == "LOW"
assert classify_severity_band(29) == "LOW"
assert classify_severity_band(30) == "MEDIUM"
assert classify_severity_band(49) == "MEDIUM"
assert classify_severity_band(50) == "HIGH"
assert classify_severity_band(69) == "HIGH"
assert classify_severity_band(70) == "CRITICAL"
assert classify_severity_band(80) == "CRITICAL"
assert classify_severity_band(90) == "CRITICAL"  # above 80 still CRITICAL
print("  [PASS] Severity band mapping")


print()
print("=" * 60)
print("Critical Override: P=1 -> CRITICAL immediately")
print("=" * 60)

result = calculate_severity(
    mq2_reading=1000,
    dht22_reading=35,
    detections=[person_inside],  # Person inside hazard
    hazard_zone=hazard,
    zone_label="normal-risk",
)
assert result.status == "critical_override"
assert result.severity_label == "CRITICAL"
assert result.critical_override is True
assert result.person_in_hazard is True
assert result.p_score == 1.0
assert result.severity_score is None  # R is NOT calculated for override
print("  [PASS] P=1 -> CRITICAL override (R not calculated)")


print()
print("=" * 60)
print("Core Formula: R = 100 * (0.30*A + 0.20*S + 0.20*T_heat + 0.20*P + 0.10*Z)")
print("=" * 60)

# MQ2=1250 -> S=0.5, DHT22=35 -> T_heat=0.5
# Fire 100x100 in 400x300 -> A=0.0833
# P=0 (no person), Z=normal-risk=0.60
result = calculate_severity(
    mq2_reading=1250,
    dht22_reading=35,
    detections=[fire_det],  # Fire only, no person
    hazard_zone=hazard,
    zone_label="normal-risk",
)
assert result.status == "calculated"
assert result.critical_override is False
assert result.person_in_hazard is False
assert result.p_score == 0.0

# Manual check:
# A = 0.08333...
# S = 0.5
# T_heat = 0.5
# P = 0.0
# Z = 0.60
# R = 100 * (0.30*0.08333 + 0.20*0.5 + 0.20*0.5 + 0.20*0.0 + 0.10*0.60)
# R = 100 * (0.025 + 0.10 + 0.10 + 0.0 + 0.06) = 100 * 0.285 = 28.5
expected_r = 100 * (0.30 * expected_a + 0.20 * 0.5 + 0.20 * 0.5 + 0.20 * 0.0 + 0.10 * 0.60)
assert abs(result.severity_score - expected_r) < 1e-6, f"Expected {expected_r:.2f}, got {result.severity_score:.2f}"
assert result.severity_label == "LOW"  # 28.5 < 30 -> LOW
print(f"  [PASS] R = {result.severity_score:.2f} -> {result.severity_label}")
print(f"         A={result.a_score:.4f} S={result.s_score:.4f} T_heat={result.t_heat_score:.4f} P={result.p_score:.4f} Z={result.z_score:.4f}")


# High severity scenario
result2 = calculate_severity(
    mq2_reading=1800,    # S = 0.8667
    dht22_reading=48,    # T_heat = 1.0 (above alarm)
    detections=[
        Detection(class_name="Fire", confidence=0.9,
                  bounding_box=BoundingBox(x1=0, y1=0, x2=300, y2=250)),
    ],
    hazard_zone=hazard,
    zone_label="high-risk",
)
assert result2.status == "calculated"
fire_a = min(1.0, (300*250) / (400*300))
s2 = normalize_smoke_score(1800)
th2 = normalize_t_heat_score(48)
expected_r2 = 100 * (0.30*fire_a + 0.20*s2 + 0.20*th2 + 0.20*0.0 + 0.10*1.0)
assert abs(result2.severity_score - expected_r2) < 1e-6
print(f"  [PASS] R = {result2.severity_score:.2f} -> {result2.severity_label}")
print(f"         A={result2.a_score:.4f} S={result2.s_score:.4f} T_heat={result2.t_heat_score:.4f} P={result2.p_score:.4f} Z={result2.z_score:.4f}")


print()
print("=" * 60)
print("Variable Isolation Verification")
print("=" * 60)

# Verify: severity S and T_heat constants are isolated from fusion
from app.fusion.policies import MQ2_NORMAL, MQ2_ALARM, DHT22_NORMAL, DHT22_ALARM
assert SEV_MQ2_NORMAL == MQ2_NORMAL == 500.0
assert SEV_MQ2_ALARM == MQ2_ALARM == 2000.0
assert SEV_DHT22_NORMAL == DHT22_NORMAL == 30.0
assert SEV_DHT22_ALARM == DHT22_ALARM == 40.0
print("  [PASS] Same baseline constants, different variable semantics")
print("  - Fusion S = max(smoke, heat); Severity S = pure MQ-2")
print("  - Fusion T = temporal consistency; Severity T_heat = pure DHT22")

# Verify weights sum to 1.0
total_w = SEVERITY_WEIGHT_A + SEVERITY_WEIGHT_S + SEVERITY_WEIGHT_T_HEAT + SEVERITY_WEIGHT_P + SEVERITY_WEIGHT_Z
assert abs(total_w - 1.0) < 1e-12, f"Weights sum to {total_w}, expected 1.0"
print(f"  [PASS] Weights sum to {total_w}")


print()
print("=" * 60)
print("All Severity policy tests PASSED!")
print("=" * 60)
