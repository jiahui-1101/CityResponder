"""Validated schemas for raw sensor messages."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class SensorMessage(BaseModel):
    """Common fields present in every raw sensor message."""

    model_config = ConfigDict(extra="allow")

    sensor_type: str
    value: Any
    timestamp: datetime
    node_id: str
    unit: str | None = None


class MQ2Message(SensorMessage):
    sensor_type: Literal["MQ2"]


class DHT22Message(SensorMessage):
    sensor_type: Literal["DHT22"]


class ButtonMessage(SensorMessage):
    sensor_type: Literal["BUTTON"]


class IRAMessage(SensorMessage):
    sensor_type: Literal["IR_A"]


class IRBMessage(SensorMessage):
    sensor_type: Literal["IR_B"]


SensorMessageUnion = Annotated[
    MQ2Message | DHT22Message | ButtonMessage | IRAMessage | IRBMessage,
    Field(discriminator="sensor_type"),
]
sensor_message_adapter = TypeAdapter(SensorMessageUnion)


class LatestSensorState(BaseModel):
    """Read-only current projection for one supported sensor type."""

    sensor_type: Literal["MQ2", "DHT22", "BUTTON", "IR_A", "IR_B"]
    value: Any | None = None
    timestamp: datetime | None = None
    node_id: str | None = None
    unit: str | None = None
    available: bool = False
