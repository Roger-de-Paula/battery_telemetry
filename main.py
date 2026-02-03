from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Device, Telemetry
from rate_limiter import get_rate_limiter
from schemas import TelemetryCreate

app = FastAPI(title="Battery Telemetry API", version="0.1.0")


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
