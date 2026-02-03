"""
Background worker: every 5 minutes, finds devices with no telemetry in the last 10 minutes,
logs an offline alert and records it in the alerts table.
Run: python -m worker
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import database
from models import Alert, Device

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

OFFLINE_THRESHOLD_MINUTES = 10
CHECK_INTERVAL_SECONDS = 5 * 60  # 5 minutes


async def check_offline_devices() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)
    async with database.async_session_factory() as session:
        try:
            result = await session.execute(
                select(Device).where(Device.last_seen < cutoff)
            )
            devices = result.scalars().all()
            for device in devices:
                last_seen_str = device.last_seen.isoformat().replace("+00:00", "Z")
                logger.warning("[ALERT] Device %s offline - last seen %s", device.device_id, last_seen_str)
                session.add(
                    Alert(
                        device_id=device.device_id,
                        detected_at=datetime.now(timezone.utc),
                        last_seen=device.last_seen,
                    )
                )
            if devices:
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_worker() -> None:
    database.init_db()
    logger.info("Worker started: checking every %s seconds for devices offline > %s minutes",
                CHECK_INTERVAL_SECONDS, OFFLINE_THRESHOLD_MINUTES)
    while True:
        try:
            await check_offline_devices()
        except Exception as e:
            logger.exception("Error during offline check: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
