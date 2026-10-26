"""In-memory command and ACK simulation with no MQTT dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from app.physical_actions.sequence import PhysicalCommandSequence


@dataclass
class SimulatedCommandTransport:
    scenario_id: str
    ack_mode: str = "success"
    publications: list[dict[str, Any]] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)

    @property
    def mqtt_capable(self) -> bool:
        return False

    def execute(self, sequence: PhysicalCommandSequence | None) -> dict[str, Any]:
        if sequence is None or sequence.status != "planned":
            return {"status": "NOT_EXECUTED", "commands": [], "mqtt_publications": 0}
        outcomes: list[dict[str, Any]] = []
        for spec in sequence.ordered_command_specs:
            command_id = str(uuid5(NAMESPACE_URL, f"{self.scenario_id}:{spec.spec_id}"))
            if command_id in self._seen:
                outcomes.append({"command_id": command_id, "status": "DUPLICATE_IGNORED", "attempts": 0})
                continue
            self._seen.add(command_id)
            record = {
                "command_id": command_id,
                "target": "SIMULATED_AC1",
                "action_category": spec.action_category.value,
                "action_type": spec.action_type.value,
                "simulation_marker": "SIMULATED",
            }
            self.publications.append(record)
            if self.ack_mode == "timeout":
                outcomes.append({**record, "status": "ACK_TIMEOUT_EXHAUSTED", "attempts": 2})
                return {
                    "status": "FAILED_IN_SIMULATION",
                    "commands": outcomes,
                    "failsafe": "SAFE_DEFAULT_APPLIED_IN_SIMULATION",
                    "retry_limit": 1,
                    "mqtt_publications": 0,
                }
            outcomes.append({**record, "status": "ACKNOWLEDGED_IN_SIMULATION", "attempts": 1})
        return {
            "status": "ACKNOWLEDGED_IN_SIMULATION",
            "commands": outcomes,
            "failsafe": None,
            "mqtt_publications": 0,
        }
