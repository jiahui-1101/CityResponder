"""Validated schemas for raw sensor messages."""

from datetime import datetime
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    field_validator,
)


NodeId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
SensorNumber = Annotated[float, Field(allow_inf_nan=False)]


class SensorMessage(BaseModel):
    """Common fields present in every raw sensor message."""

    model_config = ConfigDict(extra="forbid")

    sensor_type: str
    value: Any
    timestamp: datetime
    node_id: NodeId
    unit: str | None = None
    firmware_version: str | None = Field(default=None, max_length=48)
    protocol_version: str | None = Field(default=None, max_length=16)
    message_id: str | None = Field(default=None, max_length=64)
    simulated: StrictBool = False

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class MQ2Message(SensorMessage):
    sensor_type: Literal["MQ2"]
    value: Annotated[StrictInt, Field(ge=0, le=4095)]
    unit: Literal["raw"] = "raw"
    measurement_kind: Literal["RAW_ADC"] | None = None
    adc_status: Literal["OK", "SATURATED"] | None = None


class DHT22Message(SensorMessage):
    sensor_type: Literal["DHT22"]
    value: SensorNumber
    unit: Literal["C"] = "C"
    humidity: SensorNumber | None = Field(default=None, ge=0.0, le=100.0)
    humidity_unit: Literal["pct"] | None = None
    dht_ok: StrictBool = True

    @field_validator("value", "humidity", mode="before")
    @classmethod
    def require_finite_numeric_measurement(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("measurement must be a JSON number")
        if not isfinite(value):
            raise ValueError("measurement must be finite")
        return value

    @field_validator("value")
    @classmethod
    def validate_temperature_range(cls, value: float) -> float:
        if not -40.0 <= value <= 80.0:
            raise ValueError("DHT22 temperature must be between -40 and 80 C")
        return value

    @field_validator("dht_ok")
    @classmethod
    def reject_invalid_dht_events(cls, value: bool) -> bool:
        if not value:
            raise ValueError("failed DHT reads must not be published as measurements")
        return value


class ButtonMessage(SensorMessage):
    sensor_type: Literal["BUTTON"]
    value: StrictBool
    unit: None = None
    raw: Literal["LOW", "HIGH"] | None = None


class IRAMessage(SensorMessage):
    sensor_type: Literal["IR_A"]
    value: StrictBool
    unit: Literal["blocked", "raw"] = "blocked"
    raw: Literal["LOW", "HIGH"] | None = None


class IRBMessage(SensorMessage):
    sensor_type: Literal["IR_B"]
    value: StrictBool
    unit: Literal["blocked", "raw"] = "blocked"
    raw: Literal["LOW", "HIGH"] | None = None


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
    humidity_pct: float | None = None
    quality: str | None = None
    firmware_version: str | None = None
    protocol_version: str | None = None
    simulated: bool = False
    available: bool = False
