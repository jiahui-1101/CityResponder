"""Shared labels and type aliases for future vision branches."""

from typing import Final, Literal


FIRE: Final[str] = "fire"
SMOKE: Final[str] = "smoke"
PERSON: Final[str] = "person"
ROAD_OBSTACLE: Final[str] = "road_obstacle"
POTHOLE: Final[str] = "pothole"

VisionLabel = Literal["fire", "smoke", "person", "road_obstacle", "pothole"]
VISION_LABELS: Final[tuple[str, ...]] = (FIRE, SMOKE, PERSON, ROAD_OBSTACLE, POTHOLE)
