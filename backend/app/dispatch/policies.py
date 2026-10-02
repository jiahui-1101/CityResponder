"""Concrete dispatch matrix policies."""

from app.dispatch.matrix import ActionRecommendation, DispatchInput, DispatchRecommendation
from app.physical_actions.schemas import ActionCategory
from datetime import datetime, timezone


class DefaultDispatchMatrixPolicy:
    """Implements TBD-DISPATCH-01 and TBD-DISPATCH-03b rules."""

    version: str = "1.0.0-jiabao-dispatch"

    def evaluate(self, dispatch_input: DispatchInput) -> DispatchRecommendation:
        severity = dispatch_input.final_severity
        
        # Rule 1: Dispatch Resource Matrix (DISPATCH-01)
        dispatch_actions: list[ActionRecommendation] = []
        
        if severity == "LOW":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "FIRE_UNIT", "count": 1}
                )
            )
        elif severity == "MEDIUM":
            dispatch_actions.append(
                ActionRecommendation(
                    action_type="DISPATCH_UNIT",
                    parameters={"unit_type": "FIRE_UNIT", "count": 2}
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
        
        if severity in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            building_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.BUZZER,
                    action_type="ON",
                )
            )
            
        if severity in ("MEDIUM", "HIGH", "CRITICAL"):
            building_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.GATE,
                    action_type="OPEN",
                )
            )
            traffic_actions.append(
                ActionRecommendation(
                    action_category=ActionCategory.TRAFFIC,
                    action_type="GREEN_CORRIDOR",
                )
            )
            
        reasons = []
        timestamp_str = datetime.now(timezone.utc).isoformat()
        
        if dispatch_input.person_in_hazard:
            reasons.append("Trigger: P=1 (YOLO >= 0.50, inside polygon, 1 frame) -> CRITICAL -> 2 Fire + 1 Amb + 1 Rescue.")
            reasons.append(f"[{timestamp_str}] | [Actor: System] | [PERSON_ESCALATION]")
        else:
            if severity == "LOW":
                reasons.append("Trigger: LOW -> 1 Fire Unit, Buzzer ON, No Gate, No Traffic")
            elif severity == "MEDIUM":
                reasons.append("Trigger: MEDIUM -> 2 Fire Units, Buzzer ON, Gate OPEN, GREEN_CORRIDOR")
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
