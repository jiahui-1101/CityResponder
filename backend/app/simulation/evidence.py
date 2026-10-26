"""Fail-closed evidence validation for deterministic simulations."""

from __future__ import annotations

from datetime import datetime, timezone

from app.simulation.contracts import EvidenceValidationResult, SimulatedEvidence


class SimulatedEvidenceValidator:
    """Validate provenance, freshness, duplicates, and source ordering."""

    def __init__(self, *, stale_after_seconds: float = 5.0) -> None:
        self.stale_after_seconds = stale_after_seconds

    def validate(self, evidence: list[SimulatedEvidence], *, now: datetime) -> EvidenceValidationResult:
        now = _utc(now)
        result = EvidenceValidationResult()
        seen: set[str] = set()
        latest_by_source: dict[tuple[str, str | None], datetime] = {}
        for item in evidence:
            if item.evidence_id in seen:
                result.duplicate_ids.append(item.evidence_id)
                result.rejected.append({"evidence_id": item.evidence_id, "reason": "duplicate evidence_id"})
                continue
            seen.add(item.evidence_id)
            key = (item.source_type, item.association)
            timestamp = _utc(item.source_timestamp)
            if key in latest_by_source and timestamp < latest_by_source[key]:
                result.out_of_order_ids.append(item.evidence_id)
                result.rejected.append({"evidence_id": item.evidence_id, "reason": "out-of-order source timestamp"})
                continue
            latest_by_source[key] = timestamp
            age = (now - timestamp).total_seconds()
            if age > self.stale_after_seconds or item.freshness_status == "STALE":
                result.rejected.append({"evidence_id": item.evidence_id, "reason": "stale evidence"})
                continue
            result.accepted.append(item)
        return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
