from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import re


def _alphanumeric(v: str) -> str:
    if not v or not re.match(r"^[a-zA-Z0-9\-_]+$", v):
        raise ValueError("device_id must be alphanumeric (letters, digits, hyphens, underscores)")
    return v


class TelemetryMetrics(BaseModel):
    soc_percent: float = Field(..., ge=0, le=100, description="State of charge 0-100%")
    voltage_v: float = Field(..., ge=200, le=500, description="Voltage in V")
    current_a: float = Field(..., ge=-100, le=100, description="Current in A")
    temp_c: float = Field(..., ge=-20, le=60, description="Temperature in °C")


class TelemetryCreate(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    timestamp: datetime
    metrics: TelemetryMetrics

    @field_validator("device_id")
    @classmethod
    def device_id_alphanumeric(cls, v: str) -> str:
        return _alphanumeric(v)


class TelemetryRow(BaseModel):
    timestamp: datetime
    soc_percent: float
    voltage_v: float
    current_a: float
    temp_c: float

    model_config = {"from_attributes": True}


class TelemetryMetricsResponse(BaseModel):
    device_id: str
    data: list[TelemetryRow]


class MetricSummary(BaseModel):
    min: float
    max: float
    avg: float


class DailySummaryResponse(BaseModel):
    device_id: str
    date: str
    summary: dict[str, MetricSummary]


class ErrorDetail(BaseModel):
    loc: list[str]
    msg: str
    type: str


class ErrorResponse(BaseModel):
    detail: str
    errors: list[ErrorDetail] | None = None
