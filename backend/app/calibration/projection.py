"""Rebuildable calibration governance projections."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calibration.schemas import CalibrationCandidate, CalibrationValidationResult, CalibrationVersion
from app.events.models import Event


def calibration_events(db: Session) -> list[Event]:
    return list(db.scalars(select(Event).where(Event.entity_type.in_(["calibration", "calibration_candidate"])).order_by(Event.created_at.asc(), Event.id.asc())).all())


def get_candidate(db: Session, candidate_id: str) -> CalibrationCandidate | None:
    event = db.scalar(select(Event).where(Event.event_type == "calibration_candidate", Event.entity_id == candidate_id).order_by(Event.id.desc()))
    return CalibrationCandidate.model_validate(event.payload) if event else None


def get_candidates(db: Session) -> list[tuple[CalibrationCandidate, CalibrationValidationResult | None]]:
    events = db.scalars(select(Event).where(Event.event_type == "calibration_candidate").order_by(Event.created_at.desc(), Event.id.desc())).all()
    return [(candidate, get_validation(db, candidate.candidate_id)) for candidate in (CalibrationCandidate.model_validate(event.payload) for event in events)]


def get_validation(db: Session, candidate_id: str) -> CalibrationValidationResult | None:
    event = db.scalar(select(Event).where(Event.event_type == "calibration_validation", Event.entity_id == candidate_id).order_by(Event.id.desc()))
    return CalibrationValidationResult.model_validate(event.payload) if event else None


def get_versions(db: Session) -> list[CalibrationVersion]:
    events = calibration_events(db)
    versions: dict[str, CalibrationVersion] = {}
    for event in events:
        if event.event_type.startswith("calibration_version_"):
            version = CalibrationVersion.model_validate(event.payload)
            versions[version.version_id] = version
    return sorted(versions.values(), key=lambda item: item.version_number)


def get_active_version(db: Session) -> CalibrationVersion | None:
    active = [version for version in get_versions(db) if version.status == "active"]
    return active[-1] if active else None
