"""Receive generic MQTT commands and optionally publish simulated ACKs."""

import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.core.logging import configure_logging
from app.mqtt.client import mqtt_client


logger = logging.getLogger(__name__)


def make_command_handler(
    ack_delay: float,
    no_ack: bool,
    topic_prefix: str,
) -> Callable[[str, Any], None]:
    """Create a mock command handler with configurable ACK behavior."""

    def handle_command(topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            logger.warning("Invalid command on %s: JSON object required", topic)
            return

        command_id = payload.get("command_id")
        node_id = payload.get("node_id")
        topic_node_id = topic.rsplit("/", 1)[-1]
        if not isinstance(command_id, str) or not command_id:
            logger.warning("Invalid command on %s: command_id is required", topic)
            return
        if not isinstance(node_id, str) or not node_id:
            logger.warning("Invalid command %s: node_id is required", command_id)
            return
        if topic_node_id != node_id:
            logger.warning("Mock command topic/device mismatch on %s", topic)
            return

        logger.info("Mock actuator received command %s on %s: %s", command_id, topic, payload)
        if no_ack:
            logger.info("ACK disabled for command %s", command_id)
            return

        if ack_delay:
            time.sleep(ack_delay)

        command_payload = payload.get("payload")
        if not isinstance(command_payload, dict):
            command_payload = {}
        ack = {
            "command_id": command_id,
            "node_id": node_id,
            "status": "ACK",
            "stage": "execution_reported",
            "result": "SIMULATED_OUTPUT",
            "action_category": command_payload.get("action_category"),
            "action_type": command_payload.get("action_type"),
            "source": "simulation",
            "simulated": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mqtt_client.publish(f"{topic_prefix}/acks/{node_id}", ack, qos=1)
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
    parser.add_argument(
        "--topic-prefix",
        default=f"cityresponder/test/{uuid4().hex}",
        help="Isolated test topic prefix (must not be city or start with city/)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.ack_delay < 0:
        raise SystemExit("--ack-delay cannot be negative")
    topic_prefix = args.topic_prefix.strip("/")
    if not topic_prefix or topic_prefix == "city" or topic_prefix.startswith("city/"):
        raise SystemExit("mock actuator refuses production city/... MQTT topics")

    configure_logging("INFO")
    logger.info("Mock AC1 isolated topics: %s/commands/# -> %s/acks/<node>", topic_prefix, topic_prefix)
    mqtt_client.subscribe(
        f"{topic_prefix}/commands/#",
        make_command_handler(args.ack_delay, args.no_ack, topic_prefix),
    )
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
