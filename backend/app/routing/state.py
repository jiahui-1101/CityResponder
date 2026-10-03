"""Real-time routing state management and sensor fusion logic."""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Literal

@dataclass
class CameraFrame:
    timestamp: datetime
    o_score: float
    l_score: float
    c_routing: float

@dataclass
class EdgeState:
    edge_id: str
    
    # Camera State
    camera_window: list[CameraFrame] = field(default_factory=list)
    
    # IR State
    ir_blocked_consecutive: int = 0
    ir_clear_consecutive: int = 0
    ir_last_timestamp: datetime | None = None
    ir_state: Literal["BLOCKED", "OPEN"] = "OPEN"
    
    # Computed State
    current_state: Literal["BLOCKED", "OPEN", "SENSOR_CONFLICT", "MANUAL_OVERRIDE_OPEN"] = "OPEN"
    
    # Grace Period & Overrides
    disagreement_start_time: datetime | None = None
    override_expiry: datetime | None = None

def compute_median_o(window: list[CameraFrame]) -> float | None:
    if not window:
        return None
    return median([frame.o_score for frame in window])

def fuse_sensor_data(edge_state: EdgeState, now: datetime) -> None:
    # 1. Clean stale camera frames (> 2.0s)
    cutoff = now - timedelta(seconds=2.0)
    edge_state.camera_window = [f for f in edge_state.camera_window if f.timestamp >= cutoff]
    
    # 2. Check Override Expiry
    if edge_state.current_state == "MANUAL_OVERRIDE_OPEN" and edge_state.override_expiry:
        if now >= edge_state.override_expiry:
            edge_state.current_state = "OPEN" # Expiry returns control to automation
            edge_state.override_expiry = None
            
    if edge_state.current_state == "MANUAL_OVERRIDE_OPEN":
        return # Skip automated logic if overridden
        
    # 3. Determine camera state
    camera_blocked = False
    newest_camera_time = None
    if edge_state.camera_window:
        med_o = compute_median_o(edge_state.camera_window)
        if med_o is not None and med_o >= 0.80:
            camera_blocked = True
        newest_camera_time = max(f.timestamp for f in edge_state.camera_window)
        
    ir_blocked = (edge_state.ir_state == "BLOCKED")
    
    # 4. Check for 750ms Sync Rule OR Stale sensors
    if newest_camera_time and edge_state.ir_last_timestamp:
        gap = abs((newest_camera_time - edge_state.ir_last_timestamp).total_seconds())
        if gap > 0.750:
            edge_state.current_state = "SENSOR_CONFLICT"
            return
            
    if not edge_state.camera_window or not edge_state.ir_last_timestamp:
        # If camera is completely stale or IR never received
        return

    # 5. Determine combined state and Grace Period
    if camera_blocked and ir_blocked:
        edge_state.current_state = "BLOCKED"
        edge_state.disagreement_start_time = None
    elif not camera_blocked and not ir_blocked:
        edge_state.current_state = "OPEN"
        edge_state.disagreement_start_time = None
    else:
        # Disagreement
        if edge_state.disagreement_start_time is None:
            edge_state.disagreement_start_time = now
        else:
            if (now - edge_state.disagreement_start_time).total_seconds() > 1.0:
                edge_state.current_state = "SENSOR_CONFLICT"
                

def process_ir_reading(edge_state: EdgeState, is_blocked: bool, now: datetime) -> None:
    edge_state.ir_last_timestamp = now
    if is_blocked:
        edge_state.ir_blocked_consecutive += 1
        edge_state.ir_clear_consecutive = 0
        if edge_state.ir_blocked_consecutive >= 5:
            edge_state.ir_state = "BLOCKED"
    else:
        edge_state.ir_clear_consecutive += 1
        edge_state.ir_blocked_consecutive = 0
        if edge_state.ir_clear_consecutive >= 5:
            edge_state.ir_state = "OPEN"


def calculate_live_cost(distance_cm: float, o: float, l: float, c_routing: float) -> float:
    """edge_cost = distance_cm * (1 + 4 * (0.70 * O + 0.20 * L + 0.10 * C_routing))"""
    weighted_risk = 0.70 * o + 0.20 * l + 0.10 * c_routing
    return distance_cm * (1.0 + 4.0 * weighted_risk)


# Mock MQTT Ingress Handlers
def on_mqtt_camera_message(edge_state: EdgeState, o_score: float, l_score: float, c_routing: float):
    now = datetime.now(timezone.utc)
    # Ensure window only has max 3 frames (rolling window)
    if len(edge_state.camera_window) >= 3:
        edge_state.camera_window.pop(0)
    edge_state.camera_window.append(CameraFrame(now, o_score, l_score, c_routing))
    fuse_sensor_data(edge_state, now)
    _broadcast_if_conflict(edge_state)


def on_mqtt_ir_message(edge_state: EdgeState, is_blocked: bool):
    now = datetime.now(timezone.utc)
    process_ir_reading(edge_state, is_blocked, now)
    fuse_sensor_data(edge_state, now)
    _broadcast_if_conflict(edge_state)


def operator_manual_override(edge_state: EdgeState):
    """Triggered via WebSocket from the frontend"""
    edge_state.current_state = "MANUAL_OVERRIDE_OPEN"
    edge_state.override_expiry = datetime.now(timezone.utc) + timedelta(seconds=60)
    edge_state.disagreement_start_time = None
    print(f"[WebSocket] Operator verified edge {edge_state.edge_id} clear. Override active for 60s.")


# Mock WebSocket Broadcast Trigger
def _broadcast_if_conflict(edge_state: EdgeState):
    if edge_state.current_state == "SENSOR_CONFLICT":
        # Remove edge from active graph is handled by status logic
        print(f"[WebSocket Broadcast] ALERT: Edge {edge_state.edge_id} has SENSOR_CONFLICT! Edge removed from graph.")
                
