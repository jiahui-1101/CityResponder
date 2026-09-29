"""Receive generic MQTT commands and optionally publish simulated ACKs."""

import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.logging import configure_logging
from app.mqtt.client import mqtt_client


logger = logging.getLogger(__name__)


def make_command_handler(ack_delay: float, no_ack: bool) -> Callable[[str, Any], None]:
    """Create a mock command handler with configurable ACK behavior."""

    def handle_command(topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            logger.warning("Invalid command on %s: JSON object required", topic)
            return

        command_id = payload.get("command_id")
        node_id = payload.get("node_id")
        if not isinstance(command_id, str) or not command_id:
            logger.warning("Invalid command on %s: command_id is required", topic)
            return
        if not isinstance(node_id, str) or not node_id:
            logger.warning("Invalid command %s: node_id is required", command_id)
            return

        logger.info("Mock actuator received command %s on %s: %s", command_id, topic, payload)
        if no_ack:
            logger.info("ACK disabled for command %s", command_id)
            return

        if ack_delay:
            time.sleep(ack_delay)

        ack = {
            "command_id": command_id,
            "node_id": node_id,
            "status": "ACK",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mqtt_client.publish(f"city/acks/{node_id}", ack, qos=1)
        logger.info("Mock actuator published ACK for command %s", command_id)

    return handle_command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ack-delay",
        type=float,
        default=0.0,
        help="Seconds to wait before publishing an ACK (default: 0)",
    )
    parser.add_argument(
        "--no-ack",
        action="store_true",
        help="Receive and log commands without publishing ACKs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.ack_delay < 0:
        raise SystemExit("--ack-delay cannot be negative")

    configure_logging("INFO")
    mqtt_client.subscribe("city/commands/#", make_command_handler(args.ack_delay, args.no_ack))
    mqtt_client.start()
    try:
        if not mqtt_client.wait_until_connected():
            raise SystemExit("MQTT connection was not ready within 5 seconds")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return
    finally:
        mqtt_client.stop()


if __name__ == "__main__":
    main()
