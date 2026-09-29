"""Builder for severity-assessment inputs without calculating severity."""

from typing import Protocol

from app.fusion.schemas import ConfirmationSequenceResult, FusionSourceReference
from app.vision.schemas import PerceptionSnapshot

from app.severity.schemas import SeverityComponentValues, SeverityInput


class SeverityComponentProvider(Protocol):
    """Future source-backed provider for severity-specific A/S/T/Z values."""

    def provide(self, snapshot: PerceptionSnapshot) -> SeverityComponentValues:
        """Return explicitly defined severity components, without fusion mapping."""


def build_severity_input(
    perception_snapshot: PerceptionSnapshot,
    confirmation: ConfirmationSequenceResult | None = None,
    component_provider: SeverityComponentProvider | None = None,
) -> SeverityInput:
    """Build a deterministic severity input contract from explicit evidence."""

    person_valid = _person_evidence_is_fresh(perception_snapshot)
    person_in_hazard = (
        perception_snapshot.person_in_hazard if person_valid else None
    )
    person_score = (
        1.0 if person_in_hazard is True
        else 0.0 if person_in_hazard is False
        else None
    )
    reasons: list[str] = []
    unavailable_inputs: list[str] = []
    if not person_valid:
        unavailable_inputs.append("person_in_hazard")
        reasons.append("person-in-hazard evidence is missing, stale, or unresolved")

    if confirmation is None:
        incident_confirmed = None
        confirmation_status = "not_evaluated"
        reasons.append("incident confirmation reference is unavailable")
    else:
        incident_confirmed = confirmation.incident_confirmed
        confirmation_status = "not_evaluated"
        if incident_confirmed is not True:
            reasons.append("incident confirmation is not true")

    components = SeverityComponentValues()
    if component_provider is not None:
        try:
            components = component_provider.provide(perception_snapshot)
            reasons.extend(components.reasons)
        except Exception as exc:
            reasons.append(f"severity component provider failed: {exc}")
    else:
        reasons.append("severity A/S/T/Z provider is not configured")

    source_references = list(components.source_references)
    if perception_snapshot.detection is not None:
        source_references.append(
            FusionSourceReference(
                source_type="vision_detection",
                source_id=perception_snapshot.detection.frame.frame_id,
                timestamp=perception_snapshot.detection.frame.timestamp,
            )
        )
    status = "not_confirmed" if incident_confirmed is False else confirmation_status
    return SeverityInput(
        status=status,
        confirmation_reference=confirmation,
        incident_confirmed=incident_confirmed,
        a=components.a,
        s=components.s,
        p=person_score,
        t=components.t,
        z=components.z,
        person_in_hazard=person_in_hazard,
        person_evidence=perception_snapshot.detection,
        person_source_timestamp=(
            perception_snapshot.detection.frame.timestamp
            if person_valid and perception_snapshot.detection is not None
            else None
        ),
        critical_override_signal=(
            True if person_score == 1.0
            else False if person_score == 0.0
            else None
        ),
        source_timestamps={
            "person_in_hazard": (
                perception_snapshot.detection.frame.timestamp
                if person_valid and perception_snapshot.detection is not None
                else None
            )
        },
        unavailable_inputs=unavailable_inputs,
        reasons=reasons,
        audit_references=source_references,
    )


def _person_evidence_is_fresh(snapshot: PerceptionSnapshot) -> bool:
    return (
        snapshot.detection is not None
        and snapshot.person_in_hazard is not None
        and snapshot.freshness.detection.available
        and snapshot.freshness.detection.stale is False
    )
