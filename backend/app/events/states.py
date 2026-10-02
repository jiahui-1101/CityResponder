"""State enumerations for the incident feedback lifecycle."""

from enum import Enum


class IncidentState(str, Enum):
    RESPONDING = "RESPONDING"
    ACTIVE = "ACTIVE"
    CONCLUDED = "CONCLUDED"
    VERIFIED = "VERIFIED"
    VERIFIED_FIRE = "VERIFIED_FIRE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILSAFE = "FAILSAFE"
