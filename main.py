import logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Device, Telemetry
from rate_limiter import get_rate_limiter
from schemas import ErrorDetail, ErrorResponse, TelemetryCreate

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
