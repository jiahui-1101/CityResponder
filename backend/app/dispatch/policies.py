"""Concrete dispatch matrix policies."""

from app.dispatch.matrix import ActionRecommendation, DispatchInput, DispatchRecommendation
from app.physical_actions.schemas import ActionCategory
from datetime import datetime, timezone


class DefaultDispatchMatrixPolicy:
    """Implements the authoritative Feature 2 dispatch matrix."""

    version: str = "1.0.0-jiabao-dispatch"

    def evaluate(self, dispatch_input: DispatchInput) -> DispatchRecommendation:
        severity = dispatch_input.final_severity
        
        # Rule 1: Dispatch Resource Matrix (DISPATCH-01)
        dispatch_actions: list[ActionRecommendation] = []
        
        if severity == "LOW":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="HOLD_UNIT",
                    parameters={"unit_id": "E1", "status": "AT_STATION"},
                )
            )
        elif severity == "MEDIUM":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_id": "E1", "unit_type": "FIRE_UNIT", "count": 1},
                )
            )
        elif severity == "HIGH":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "FIRE_UNIT", "count": 2}
                )
            )
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "AMBULANCE", "count": 1}
                )
            )
        elif severity == "CRITICAL":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "FIRE_UNIT", "count": 2}
                )
            )
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "AMBULANCE", "count": 1}
                )
            )
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "RESCUE_UNIT", "count": 1}
                )
            )
        else:
            # Fallback if unknown severity
            pass

        # Rule 4: Hardware Action Thresholds (DISPATCH-03b)
        building_actions: list[ActionRecommendation] = []
        traffic_actions: list[ActionRecommendation] = []
        
        if severity == "MEDIUM":
            building_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.BUZZER,
                    action_type="PULSE_500_MS",
                )
            )
            # The master contract requires this output, but the authoritative
            # hardware map has no zone-indicator GPIO. Preserve it as an
            # explicit unmapped recommendation instead of inventing a pin.
            building_actions.append(
                ActionRecommendation(
                    action_type="ZONE_AMBER_ON",
                    parameters={"output": "AMBER_ZONE_LED"},
                    reason="ZONE_INDICATOR_GPIO_UNMAPPED",
                )
            )
        elif severity in ("HIGH", "CRITICAL"):
            building_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.BUZZER,
                    action_type="ON",
                )
            )
            
        if severity in ("MEDIUM", "HIGH", "CRITICAL"):
            if dispatch_input.selected_corridor is None:
                raise ValueError(
                    f"{severity} requires an explicit selected corridor"
                )
            traffic_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.TRAFFIC,
                    action_type="GREEN_CORRIDOR",
                    parameters={"corridor": dispatch_input.selected_corridor},
                )
            )

        if severity in ("HIGH", "CRITICAL"):
            building_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.GATE,
                    action_type="OPEN",
                )
            )
        elif severity == "LOW":
            traffic_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.TRAFFIC,
                    action_type="NORMAL_CYCLE",
                )
            )
            building_actions.append(
                ActionRecommendation(
                    action_type="ZONE_AMBER_5_SECONDS",
                    parameters={"output": "AMBER_ZONE_LED", "duration_ms": 5000},
                    reason="ZONE_INDICATOR_GPIO_UNMAPPED",
                )
            )
            
        reasons = []
        timestamp_str = datetime.now(timezone.utc).isoformat()
        
        if dispatch_input.person_in_hazard:
            reasons.append("Trigger: P=1 (YOLO >= 0.50, inside polygon, 1 frame) -> CRITICAL -> 2 Fire + 1 Amb + 1 Rescue.")
            reasons.append(f"[{timestamp_str}] | [Actor: System] | [PERSON_ESCALATION]")
        else:
            if severity == "LOW":
                reasons.append("Trigger: LOW -> E1 held at station, NORMAL_CYCLE, amber zone indication for 5 seconds")
            elif severity == "MEDIUM":
                reasons.append("Trigger: MEDIUM -> dispatch E1, selected-route GREEN_CORRIDOR, buzzer 500 ms pulse, amber zone indication, gate remains closed")
            elif severity == "HIGH":
                reasons.append("Trigger: HIGH -> 2 Fire, 1 Ambulance, Buzzer ON, Gate OPEN, GREEN_CORRIDOR")
            elif severity == "CRITICAL":
                reasons.append("Trigger: CRITICAL -> 2 Fire, 1 Ambulance, 1 Rescue, Buzzer ON, Gate OPEN, GREEN_CORRIDOR")
                
            reasons.append(f"[{timestamp_str}] | [Actor: System] | [{severity}_DISPATCH]")
            
        return DispatchRecommendation(
            status="recommended",
            dispatch_actions=dispatch_actions,
            building_actions=building_actions,
            traffic_actions=traffic_actions,
            reasons=reasons,
            generated_at=datetime.now(timezone.utc),
        )
