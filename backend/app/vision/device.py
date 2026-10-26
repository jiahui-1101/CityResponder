"""Compute-device selection shared by the frozen YOLO wrappers."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


def resolve_inference_device(configured_device: str) -> int | str:
    """Resolve ``auto`` to CUDA when available, otherwise to CPU.

    Explicit device values are preserved so a requested GPU does not silently
    fall back to CPU when it is unavailable.
    """

    value = str(configured_device).strip().lower()
    if value == "auto":
        try:
            import torch

            return 0 if torch.cuda.is_available() else "cpu"
        except Exception:
            logger.warning("CUDA auto-detection failed; using CPU", exc_info=True)
            return "cpu"
    if value.isdecimal():
        return int(value)
    return value
