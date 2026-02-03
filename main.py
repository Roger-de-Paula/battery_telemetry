import logging
from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Device, Telemetry
from rate_limiter import get_rate_limiter
from schemas import (
    DailySummaryResponse,
    ErrorDetail,
    ErrorResponse,
    MetricSummary,
    TelemetryCreate,
    TelemetryMetricsResponse,
    TelemetryRow,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Battery Telemetry API", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        ErrorDetail(loc=[str(p) for p in e["loc"]], msg=e["msg"], type=e["type"])
        for e in exc.errors()
    ]
    first = exc.errors()[0]["msg"] if exc.errors() else "Validation failed"
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(detail=first, errors=errors).model_dump(),
    )


@app.exception_handler(SQLAlchemyError)
async def sql_exception_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="Internal server error").model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=detail).model_dump(),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/telemetry", status_code=status.HTTP_201_CREATED)
async def post_telemetry(
    body: TelemetryCreate,
    session: AsyncSession = Depends(get_session),
):
    limiter = get_rate_limiter()
    if await limiter.is_rate_limited(body.device_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    result = await session.execute(select(Device).where(Device.device_id == body.device_id))
    device = result.scalar_one_or_none()
    if device is None:
        device = Device(
            device_id=body.device_id,
            last_seen=body.timestamp,
            status="online",
        )
        session.add(device)
    else:
        device.last_seen = body.timestamp
        device.status = "online"
    session.add(
        Telemetry(
            device_id=body.device_id,
            timestamp=body.timestamp,
            soc_percent=body.metrics.soc_percent,
            voltage_v=body.metrics.voltage_v,
            current_a=body.metrics.current_a,
            temp_c=body.metrics.temp_c,
        )
    )
    return {"status": "created"}


@app.get("/devices/{device_id}/metrics", response_model=TelemetryMetricsResponse)
async def get_device_metrics(
    device_id: str,
    start_time: datetime = Query(..., description="Start of range (ISO 8601)"),
    end_time: datetime = Query(..., description="End of range (ISO 8601)"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Device).where(Device.device_id == device_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    stmt = (
        select(Telemetry)
        .where(
            Telemetry.device_id == device_id,
            Telemetry.timestamp >= start_time,
            Telemetry.timestamp <= end_time,
        )
        .order_by(Telemetry.timestamp)
    )
    rows = (await session.execute(stmt)).scalars().all()
    data = [
        TelemetryRow(
            timestamp=r.timestamp,
            soc_percent=float(r.soc_percent),
            voltage_v=float(r.voltage_v),
            current_a=float(r.current_a),
            temp_c=float(r.temp_c),
        )
        for r in rows
    ]
    return TelemetryMetricsResponse(device_id=device_id, data=data)


@app.get("/devices/{device_id}/summary", response_model=DailySummaryResponse)
async def get_device_summary(
    device_id: str,
    date: str = Query(..., description="Date YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Device).where(Device.device_id == device_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    try:
        day_start = datetime.fromisoformat(date + "T00:00:00+00:00")
        day_end = datetime.fromisoformat(date + "T23:59:59.999999+00:00")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format, use YYYY-MM-DD")
    agg = (
        select(
            func.min(Telemetry.soc_percent).label("soc_min"),
            func.max(Telemetry.soc_percent).label("soc_max"),
            func.avg(Telemetry.soc_percent).label("soc_avg"),
            func.min(Telemetry.voltage_v).label("v_min"),
            func.max(Telemetry.voltage_v).label("v_max"),
            func.avg(Telemetry.voltage_v).label("v_avg"),
            func.min(Telemetry.current_a).label("i_min"),
            func.max(Telemetry.current_a).label("i_max"),
            func.avg(Telemetry.current_a).label("i_avg"),
            func.min(Telemetry.temp_c).label("t_min"),
            func.max(Telemetry.temp_c).label("t_max"),
            func.avg(Telemetry.temp_c).label("t_avg"),
        )
        .where(
            Telemetry.device_id == device_id,
            Telemetry.timestamp >= day_start,
            Telemetry.timestamp <= day_end,
        )
    )
    row = (await session.execute(agg)).one()
    if row.soc_min is None:
        summary = {
            "soc_percent": MetricSummary(min=0, max=0, avg=0),
            "voltage_v": MetricSummary(min=0, max=0, avg=0),
            "current_a": MetricSummary(min=0, max=0, avg=0),
            "temp_c": MetricSummary(min=0, max=0, avg=0),
        }
    else:
        summary = {
            "soc_percent": MetricSummary(min=float(row.soc_min), max=float(row.soc_max), avg=float(row.soc_avg)),
            "voltage_v": MetricSummary(min=float(row.v_min), max=float(row.v_max), avg=float(row.v_avg)),
            "current_a": MetricSummary(min=float(row.i_min), max=float(row.i_max), avg=float(row.i_avg)),
            "temp_c": MetricSummary(min=float(row.t_min), max=float(row.t_max), avg=float(row.t_avg)),
        }
    return DailySummaryResponse(device_id=device_id, date=date, summary=summary)
