"""Send one generic actuator command through the backend command service."""

import json

from app.actuators.service import publish_actuator_command
from app.core.database import SessionLocal, initialize_database
from app.mqtt.client import mqtt_client


def main() -> None:
    initialize_database()
    mqtt_client.start()
    db = SessionLocal()
    try:
        if not mqtt_client.wait_until_connected():
            raise SystemExit("MQTT connection was not ready within 5 seconds")
        command = publish_actuator_command(
            db,
            node_id="AC1",
            command_type="demo_command",
            payload={"action": "demo"},
        )
    finally:
        db.close()
        mqtt_client.stop()

    print(json.dumps(command, indent=2))


if __name__ == "__main__":
    main()
