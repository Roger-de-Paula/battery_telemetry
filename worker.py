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
# Same offline period = last_seen within this many seconds (avoid duplicate alerts)
DEDUP_LAST_SEEN_TOLERANCE_SECONDS = 60


async def check_offline_devices() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)
    async with database.async_session_factory() as session:
        try:
            result = await session.execute(
                select(Device).where(Device.last_seen < cutoff)
            )
            devices = result.scalars().all()
            if not devices:
                return
            device_ids = [d.device_id for d in devices]
            # Latest alert per device (by detected_at desc)
            alerts_result = await session.execute(
                select(Alert).where(Alert.device_id.in_(device_ids)).order_by(Alert.detected_at.desc())
            )
            all_alerts = alerts_result.scalars().all()
            latest_by_device: dict[str, Alert] = {}
            for a in all_alerts:
                if a.device_id not in latest_by_device:
                    latest_by_device[a.device_id] = a
            to_alert = []
            for device in devices:
                latest = latest_by_device.get(device.device_id)
                if latest is not None:
                    delta_sec = abs((device.last_seen - latest.last_seen).total_seconds())
                    if delta_sec <= DEDUP_LAST_SEEN_TOLERANCE_SECONDS:
                        continue  # already alerted for this offline period
                to_alert.append(device)
            for device in to_alert:
                last_seen_str = device.last_seen.isoformat().replace("+00:00", "Z")
                logger.warning("[ALERT] Device %s offline - last seen %s", device.device_id, last_seen_str)
                session.add(
                    Alert(
                        device_id=device.device_id,
                        detected_at=datetime.now(timezone.utc),
                        last_seen=device.last_seen,
                    )
                )
            if to_alert:
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
