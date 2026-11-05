"""Unified background worker running monitoring scheduler and notification outbox delivery.

Can be run in production via:
    python -m app.worker

Handles graceful shutdown on SIGINT and SIGTERM.
Individual subsystems can also be executed independently:
    python -m app.monitor worker
    python -m app.notifications.worker
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import settings
from app.db.session import SessionLocal
from app.monitoring.config import MonitoringConfig
from app.monitoring.scheduler import worker as monitoring_worker
from app.notifications.config import NotificationConfig
from app.notifications.provider import get_email_provider
from app.notifications.worker import NotificationWorker

logger = logging.getLogger("app.worker")


async def run_worker() -> None:
    stop_event = asyncio.Event()

    def handle_stop_signal(sig_name: str) -> None:
        logger.info("Received %s, initiating graceful worker shutdown...", sig_name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_stop_signal, sig.name)
        except (NotImplementedError, AttributeError):
            # Fallback for platforms without add_signal_handler (e.g. Windows Proactor)
            signal.signal(sig, lambda s, f: handle_stop_signal("SIGNAL"))

    monitor_config = MonitoringConfig(
        tick_seconds=settings.monitor_tick_seconds,
        source_timeout_seconds=settings.monitor_source_timeout_seconds,
        source_batch_size=settings.monitor_source_batch_size,
        profile_batch_size=settings.monitor_profile_batch_size,
        job_batch_size=settings.monitor_job_batch_size,
        anomaly_drop_fraction=settings.monitor_anomaly_drop_fraction,
        pause_after_failures=settings.monitor_pause_after_failures,
    )

    notif_config = NotificationConfig.from_settings()
    email_provider = get_email_provider()
    notif_worker = NotificationWorker(SessionLocal, provider=email_provider, config=notif_config)

    logger.info(
        "JobPulse background worker started (monitoring interval=%.1fs, notifications interval=%.1fs)",
        monitor_config.tick_seconds,
        notif_config.tick_seconds,
    )

    monitoring_task = asyncio.create_task(
        monitoring_worker(SessionLocal, monitor_config, stop=stop_event),
        name="monitoring_scheduler",
    )
    notification_task = asyncio.create_task(
        notif_worker.run_loop(stop_event=stop_event),
        name="notification_outbox",
    )

    try:
        await asyncio.gather(monitoring_task, notification_task, return_exceptions=True)
    finally:
        logger.info("JobPulse background worker shutdown complete.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker terminated by keyboard interrupt.")


if __name__ == "__main__":
    main()
