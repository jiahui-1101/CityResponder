"""Publish a bounded, safe sensor stream for live-update diagnostics."""

import argparse
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.core.logging import configure_logging
from app.mqtt.client import mqtt_client


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="Number of sensor events to publish")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between events")
    parser.add_argument("--node-id", default="live-latency-harness")
    args = parser.parse_args()
    if args.count <= 0 or args.interval <= 0:
        raise SystemExit("--count and --interval must be greater than zero")

    configure_logging("INFO")
    mqtt_client.start()
    try:
        if not mqtt_client.wait_until_connected(timeout=5):
            raise SystemExit("MQTT connection was not ready within 5 seconds")
        for index in range(args.count):
            source_timestamp = datetime.now(timezone.utc).isoformat()
            harness_id = str(uuid4())
            payload = {"sensor_type": "MQ2", "value": float(index), "timestamp": source_timestamp, "node_id": args.node_id, "unit": "raw"}
            mqtt_client.publish("city/sensors/mq2", payload, qos=1)
            print(json.dumps({"harness_id": harness_id, "source_timestamp": source_timestamp, "topic": "city/sensors/mq2"}))
            if index + 1 < args.count:
                time.sleep(args.interval)
    finally:
        mqtt_client.stop()


if __name__ == "__main__":
    main()
