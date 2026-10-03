"""Frozen-model path resolution and startup contract validation."""

from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class ModelContractError(RuntimeError):
    """Raised when a configured frozen model does not match its contract."""


def resolve_weights_path(configured_path: str) -> Path:
    """Resolve a configured path without silently substituting another model."""

    candidate = Path(configured_path).expanduser()
    candidates = [candidate] if candidate.is_absolute() else [
        (Path.cwd() / candidate),
        (REPOSITORY_ROOT / candidate),
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.is_file():
            return resolved
    checked = ", ".join(str(path.resolve()) for path in candidates)
    raise ModelContractError(
        f"Configured model weights do not exist: {configured_path}; checked: {checked}"
    )


def validate_model_contract(
    model: Any,
    *,
    expected_task: str,
    expected_classes: tuple[str, ...],
    weights_path: Path,
) -> None:
    """Require the expected Ultralytics task and exact indexed class mapping."""

    task = str(getattr(model, "task", "")).strip().lower()
    if task != expected_task:
        raise ModelContractError(
            f"Model {weights_path} has task '{task or 'unknown'}'; "
            f"expected '{expected_task}'"
        )
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        try:
            actual = tuple(str(names[index]).strip().lower() for index in range(len(names)))
        except (KeyError, TypeError) as exc:
            raise ModelContractError(
                f"Model {weights_path} has a malformed class mapping"
            ) from exc
    elif isinstance(names, (list, tuple)):
        actual = tuple(str(name).strip().lower() for name in names)
    else:
        raise ModelContractError(f"Model {weights_path} has no readable class mapping")
    if actual != expected_classes:
        raise ModelContractError(
            f"Model {weights_path} classes {actual} do not match expected "
            f"{expected_classes}"
        )
