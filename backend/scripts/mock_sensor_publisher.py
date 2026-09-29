"""Publish schema-valid demo sensor messages over MQTT."""

import argparse
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logging import configure_logging
from app.mqtt.client import mqtt_client


DEMO_SENSORS = (
    ("city/sensors/mq2", "MQ2", 0.0, "raw"),
    ("city/sensors/dht22", "DHT22", 25.0, "C"),
    ("city/sensors/button", "BUTTON", False, None),
    ("city/sensors/ir_a", "IR_A", False, "raw"),
    ("city/sensors/ir_b", "IR_B", False, "raw"),
)


def build_demo_messages(node_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Build one valid raw-message batch without applying business logic."""

    timestamp = datetime.now(timezone.utc).isoformat()
    messages = []
    for topic, sensor_type, value, unit in DEMO_SENSORS:
        payload: dict[str, Any] = {
            "sensor_type": sensor_type,
            "value": value,
            "timestamp": timestamp,
            "node_id": node_id,
        }
        if unit is not None:
            payload["unit"] = unit
        messages.append((topic, payload))
    return messages


def publish_demo_cycle(node_id: str) -> None:
    """Publish one message for each supported raw sensor type."""

    for topic, payload in build_demo_messages(node_id):
        mqtt_client.publish(topic, payload, qos=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between demo batches (default: 1.0)",
    )
    parser.add_argument(
        "--node-id",
        default="mock-sn1",
        help="Sensor node identifier (default: mock-sn1)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Publish one batch and exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")

    configure_logging("INFO")
    mqtt_client.start()
    try:
        if not mqtt_client.wait_until_connected():
            raise SystemExit("MQTT connection was not ready within 5 seconds")
        while True:
            publish_demo_cycle(args.node_id)
            if args.once:
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return
    finally:
        mqtt_client.stop()


if __name__ == "__main__":
    main()
