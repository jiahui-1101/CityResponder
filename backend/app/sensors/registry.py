"""Configured sensor node identities accepted by the ingestion boundary."""

from app.core.config import get_settings

ACTIVE_SENSOR_TOPIC_SUFFIXES = ("dht22", "ir_a", "ir_b")


def active_sensor_mqtt_topics(topic_prefix: str) -> tuple[str, ...]:
    """Return the exact observation topics enabled for the SN1 integration phase."""

    prefix = topic_prefix.strip("/")
    if not prefix:
        return ()
    return tuple(f"{prefix}/{suffix}" for suffix in ACTIVE_SENSOR_TOPIC_SUFFIXES)


def allowed_sensor_node_ids() -> frozenset[str]:
    """Return exact, case-sensitive node IDs allowed to publish telemetry."""

    raw = get_settings().sensor_allowed_node_ids
    return frozenset(node_id.strip() for node_id in raw.split(",") if node_id.strip())
