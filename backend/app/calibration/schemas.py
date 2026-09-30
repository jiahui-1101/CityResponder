"""Explicit adaptive-calibration contracts with no invented learning policy."""

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

MIN_WEIGHT = 0.10
MAX_WEIGHT = 0.50
REQUIRED_WEIGHT_SUM = 1.00
BATCH_GRADIENT_SETTING = 0.02
TRAINING_OUTCOME_COUNT = 30
VALIDATION_OUTCOME_COUNT = 15
WEIGHT_TOLERANCE = 1e-9
BASELINE_FUSION_WEIGHTS = {"S": 0.30, "T": 0.20, "V": 0.35, "H": 0.15}


class CalibrationWeights(BaseModel):
    s: float
    t: float
    v: float
    h: float

    @model_validator(mode="after")
    def validate_bounds_and_sum(self) -> "CalibrationWeights":
        validate_calibration_weights(self)
        return self


def _weight_values(weights: CalibrationWeights | dict[str, float]) -> dict[str, float]:
    if isinstance(weights, CalibrationWeights):
        return {"S": weights.s, "T": weights.t, "V": weights.v, "H": weights.h}
    return {name: float(weights[name.lower()]) for name in ("S", "T", "V", "H")}


def validate_calibration_weights(weights: CalibrationWeights | dict[str, float]) -> CalibrationWeights:
    """Validate finite bounded weights and the fixed simplex sum."""

    values = _weight_values(weights)
    if any(not isfinite(value) for value in values.values()):
        raise ValueError("calibration weights must be finite")
    if any(value < MIN_WEIGHT or value > MAX_WEIGHT for value in values.values()):
        raise ValueError(f"each calibration weight must be within [{MIN_WEIGHT}, {MAX_WEIGHT}]")
    if abs(sum(values.values()) - REQUIRED_WEIGHT_SUM) > WEIGHT_TOLERANCE:
        raise ValueError("calibration weights must sum to 1.00")
    return weights if isinstance(weights, CalibrationWeights) else CalibrationWeights(**{key.lower(): value for key, value in values.items()})


def project_to_bounded_simplex(candidate: dict[str, float] | list[float] | tuple[float, ...]) -> CalibrationWeights:
    """Project four finite values onto the bounded simplex deterministically.

    This is the Euclidean water-filling projection: one shared Lagrange
    multiplier is solved by bisection while every coordinate is clipped to the
    same bounds. It is independent of record ordering and does not normalize
    by sequential redistribution.
    """

    if isinstance(candidate, dict):
        raw = [float(candidate[name]) for name in ("s", "t", "v", "h")]
    else:
        raw = [float(value) for value in candidate]
    if len(raw) != 4 or any(not isfinite(value) for value in raw):
        raise ValueError("candidate must contain four finite weights")
    lower, upper = min(raw) - MAX_WEIGHT, max(raw) - MIN_WEIGHT
    for _ in range(120):
        midpoint = (lower + upper) / 2
        projected_sum = sum(min(MAX_WEIGHT, max(MIN_WEIGHT, value - midpoint)) for value in raw)
        if projected_sum > REQUIRED_WEIGHT_SUM:
            lower = midpoint
        else:
            upper = midpoint
    projected = [min(MAX_WEIGHT, max(MIN_WEIGHT, value - (lower + upper) / 2)) for value in raw]
    # Bisection is already within tolerance; this only removes floating drift.
    residual = REQUIRED_WEIGHT_SUM - sum(projected)
    if abs(residual) > WEIGHT_TOLERANCE:
        adjustable = [index for index, value in enumerate(projected) if MIN_WEIGHT < value < MAX_WEIGHT]
        if adjustable:
            share = residual / len(adjustable)
            projected = [value + share if index in adjustable else value for index, value in enumerate(projected)]
    return validate_calibration_weights(dict(zip(("s", "t", "v", "h"), projected)))


class VerifiedCalibrationOutcome(BaseModel):
    outcome_id: str
    incident_decision_id: str
    operator_decision_id: str
    operator_action: str
    verified_at: datetime
    immutable_source_references: list[dict[str, Any]] = Field(min_length=1)
    operator_verified: bool
    explicit_features: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_verified_source(self) -> "VerifiedCalibrationOutcome":
        if not self.operator_verified:
            raise ValueError("calibration outcomes must be explicitly operator-verified")
        return self


class CalibrationDataset(BaseModel):
    training_outcomes: list[VerifiedCalibrationOutcome]
    validation_outcomes: list[VerifiedCalibrationOutcome]

    @model_validator(mode="after")
    def validate_dataset(self) -> "CalibrationDataset":
        if len(self.training_outcomes) != TRAINING_OUTCOME_COUNT:
            raise ValueError("training set must contain exactly 30 outcomes")
        if len(self.validation_outcomes) != VALIDATION_OUTCOME_COUNT:
            raise ValueError("validation set must contain exactly 15 outcomes")
        training_ids = [item.outcome_id for item in self.training_outcomes]
        validation_ids = [item.outcome_id for item in self.validation_outcomes]
        if len(set(training_ids)) != len(training_ids) or len(set(validation_ids)) != len(validation_ids):
            raise ValueError("outcome IDs must be unique within each dataset split")
        if set(training_ids) & set(validation_ids):
            raise ValueError("training and validation outcomes must not overlap")
        return self

    @property
    def identity(self) -> str:
        ids = sorted(item.outcome_id for item in self.training_outcomes + self.validation_outcomes)
        return ":".join(ids)


class CalibrationGradientProvider(Protocol):
    name: str
    version: str

    def propose(self, training: list[VerifiedCalibrationOutcome], baseline: CalibrationWeights, batch_gradient_setting: float) -> dict[str, float]:
        """Return explicitly defined raw proposed weights or update output."""
        ...


class CalibrationCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    based_on_version: int | None = None
    baseline_weights: CalibrationWeights
    raw_proposed_weights: dict[str, float] | None = None
    projected_candidate_weights: CalibrationWeights | None = None
    batch_gradient_setting: float = BATCH_GRADIENT_SETTING
    training_count: int
    validation_count: int
    dataset_identity: str
    provider_name: str | None = None
    provider_version: str | None = None
    status: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_references: list[dict[str, Any]] = Field(default_factory=list)


def build_calibration_candidate(
    dataset: CalibrationDataset,
    *,
    baseline: CalibrationWeights | None = None,
    provider: CalibrationGradientProvider | None = None,
    based_on_version: int | None = None,
) -> CalibrationCandidate:
    baseline_weights = baseline or CalibrationWeights(**{key.lower(): value for key, value in BASELINE_FUSION_WEIGHTS.items()})
    if provider is None:
        return CalibrationCandidate(
            based_on_version=based_on_version,
            baseline_weights=baseline_weights,
            training_count=len(dataset.training_outcomes),
            validation_count=len(dataset.validation_outcomes),
            dataset_identity=dataset.identity,
            status="not_evaluated",
            reasons=["no CalibrationGradientProvider was supplied"],
            warnings=["gradient, loss, labels, and update direction are source-undefined"],
        )
    raw = provider.propose(dataset.training_outcomes, baseline_weights, BATCH_GRADIENT_SETTING)
    projected = project_to_bounded_simplex(raw)
    return CalibrationCandidate(
        based_on_version=based_on_version,
        baseline_weights=baseline_weights,
        raw_proposed_weights=raw,
        projected_candidate_weights=projected,
        training_count=len(dataset.training_outcomes),
        validation_count=len(dataset.validation_outcomes),
        dataset_identity=dataset.identity,
        provider_name=provider.name,
        provider_version=provider.version,
        status="candidate_ready",
        audit_references=[{"provider": provider.name, "provider_version": provider.version}],
    )


class CalibrationValidationPolicy(Protocol):
    name: str
    version: str

    def evaluate(self, candidate: CalibrationCandidate, validation: list[VerifiedCalibrationOutcome]) -> dict[str, Any]:
        ...


class CalibrationValidationResult(BaseModel):
    candidate_id: str
    status: str
    passed: bool | None
    metrics: dict[str, Any] = Field(default_factory=dict)
    policy_name: str | None = None
    policy_version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_references: list[dict[str, Any]] = Field(default_factory=list)


def evaluate_calibration_candidate(
    candidate: CalibrationCandidate,
    validation: list[VerifiedCalibrationOutcome],
    policy: CalibrationValidationPolicy | None = None,
) -> CalibrationValidationResult:
    if policy is None:
        return CalibrationValidationResult(
            candidate_id=candidate.candidate_id,
            status="not_evaluated",
            passed=None,
            reasons=["no CalibrationValidationPolicy was supplied"],
        )
    result = policy.evaluate(candidate, validation)
    result_status = "passed" if result.get("passed") is True else "failed" if result.get("passed") is False else "not_evaluated"
    return CalibrationValidationResult(
        candidate_id=candidate.candidate_id,
        status=result_status,
        passed=result.get("passed"),
        metrics=result.get("metrics", {}),
        policy_name=policy.name,
        policy_version=policy.version,
        reasons=result.get("reasons", []),
        warnings=result.get("warnings", []),
    )


class CalibrationVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid4()))
    version_number: int
    weights: CalibrationWeights
    source_candidate_id: str | None = None
    status: str
    approved_by: int | None = None
    approved_at: datetime | None = None
    activated_at: datetime | None = None
    supersedes_version: int | None = None
    rollback_from_version: int | None = None
    reasons: list[str] = Field(default_factory=list)
    audit_references: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
