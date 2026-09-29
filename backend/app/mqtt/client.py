"""Small reconnecting MQTT client with JSON payload support."""

import json
import logging
from collections.abc import Callable
from threading import Event
from typing import Any

from paho.mqtt import client as mqtt

from app.core.config import get_settings


logger = logging.getLogger(__name__)
MessageHandler = Callable[[str, Any], None]

DEFAULT_SUBSCRIPTION_TOPICS = (
    "city/sensors/#",
    "city/vision/#",
    "city/acks/#",
)


class MQTTClient:
    """Own one MQTT connection and safely re-subscribe after reconnects."""

    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.mqtt_host
        self._port = settings.mqtt_port
        self._username = settings.mqtt_username
        self._password = settings.mqtt_password
        self._subscriptions: dict[str, list[MessageHandler]] = {}
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._started = False
        self._stopping = False
        self._connected_event = Event()

        if self._username is not None:
            self._client.username_pw_set(self._username, self._password)

    def start(self) -> None:
        """Start the network loop and attempt a non-blocking broker connection."""

        if self._started:
            return

        self._started = True
        self._stopping = False
        self._connected_event.clear()
        for topic in DEFAULT_SUBSCRIPTION_TOPICS:
            self._subscriptions.setdefault(topic, [])

        try:
            self._client.loop_start()
            self._client.connect_async(self._host, self._port)
        except Exception:
            logger.exception("MQTT startup failed; the application will continue")
            self._client.loop_stop()
            self._started = False
            self._connected_event.clear()

    def stop(self) -> None:
        """Stop the network loop and close the broker connection if possible."""

        if not self._started:
            return

        self._stopping = True
        try:
            self._client.disconnect()
        except Exception:
            logger.warning("MQTT disconnect failed", exc_info=True)
        finally:
            self._client.loop_stop()
            self._started = False
            self._connected_event.clear()
            self._stopping = False

    def is_connected(self) -> bool:
        """Return whether the MQTT broker connection is currently ready."""

        return self._connected_event.is_set() and self._client.is_connected()

    def wait_until_connected(self, timeout: float = 5.0) -> bool:
        """Wait for the initial broker connection, returning readiness status."""

        if timeout < 0:
            raise ValueError("timeout cannot be negative")
        return self._connected_event.wait(timeout) and self.is_connected()

    def subscribe(self, topic: str, handler: MessageHandler | None = None) -> None:
        """Register a topic handler and subscribe immediately when connected."""

        handlers = self._subscriptions.setdefault(topic, [])
        if handler is not None:
            handlers.append(handler)

        if self._client.is_connected():
            result, _ = self._client.subscribe(topic, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("MQTT subscribe failed for topic %s: rc=%s", topic, result)

    def publish(self, topic: str, payload: Any, qos: int = 1) -> None:
        """Publish a text, bytes, or JSON-serializable payload."""

        message = payload
        if not isinstance(payload, (str, bytes, bytearray)):
            message = json.dumps(payload)

        result = self._client.publish(topic, message, qos=qos)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("MQTT publish failed for topic %s: rc=%s", topic, result.rc)

    def _on_connect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if reason_code != 0:
            self._connected_event.clear()
            logger.warning("MQTT connection rejected: %s", reason_code)
            return

        self._connected_event.set()
        logger.info("Connected to MQTT broker at %s:%s", self._host, self._port)
        for topic in self._subscriptions:
            self._client.subscribe(topic, qos=1)

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, *args: Any) -> None:
        reason_code = args[1] if len(args) > 1 else None
        self._connected_event.clear()
        if self._started and not self._stopping:
            logger.warning("MQTT disconnected; retrying automatically: %s", reason_code)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: Any) -> None:
        try:
            payload: Any = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = message.payload.decode("utf-8", errors="replace")

        for topic, handlers in self._subscriptions.items():
            if not mqtt.topic_matches_sub(topic, message.topic):
                continue
            for handler in tuple(handlers):
                try:
                    handler(message.topic, payload)
                except Exception:
                    logger.exception("MQTT handler failed for topic %s", message.topic)


mqtt_client = MQTTClient()


def subscribe(topic: str, handler: MessageHandler | None = None) -> None:
    """Register a reusable MQTT subscription."""

    mqtt_client.subscribe(topic, handler)


def publish(topic: str, payload: Any, qos: int = 1) -> None:
    """Publish a reusable MQTT message."""

    mqtt_client.publish(topic, payload, qos)
