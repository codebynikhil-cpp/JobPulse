"""Developer/supervised worker CLI: python -m app.monitor --help."""

import argparse
import asyncio
import json
import logging
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import auth, catalog, job, monitoring, profile  # noqa: F401
from app.models.monitoring import MonitorRun
from app.monitoring.config import MonitoringConfig
from app.monitoring.runner import run_source
from app.monitoring.scheduler import run_due, worker
from app.monitoring.subscriptions import subscribe_company


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"level": record.levelname, "message": record.getMessage()}
        for key in (
            "source_id",
            "company_id",
            "adapter_key",
            "acquisition_method",
            "job_id",
            "profile_id",
            "run_id",
            "status",
            "error_type",
            "matched_count",
            "result",
        ):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data, default=str)


def main():
    parser = argparse.ArgumentParser(description="Monitor supported configured sources")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run").add_argument("source_id", type=uuid.UUID)
    commands.add_parser("due")
    commands.add_parser("worker")
    commands.add_parser("status").add_argument("source_id", type=uuid.UUID)
    subscribe = commands.add_parser("subscribe")
    subscribe.add_argument("user_id", type=uuid.UUID)
    subscribe.add_argument("profile_id", type=uuid.UUID)
    subscribe.add_argument("company_id", type=uuid.UUID)
    args = parser.parse_args()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    config = MonitoringConfig(
        tick_seconds=settings.monitor_tick_seconds,
        source_timeout_seconds=settings.monitor_source_timeout_seconds,
        source_batch_size=settings.monitor_source_batch_size,
        profile_batch_size=settings.monitor_profile_batch_size,
        job_batch_size=settings.monitor_job_batch_size,
        anomaly_drop_fraction=settings.monitor_anomaly_drop_fraction,
        pause_after_failures=settings.monitor_pause_after_failures,
    )
    if args.command == "worker":
        try:
            asyncio.run(worker(SessionLocal, config))
        except KeyboardInterrupt:
            pass
        return
    if args.command == "subscribe":
        with SessionLocal.begin() as db:
            subscribe_company(db, args.user_id, args.profile_id, args.company_id)
        print(json.dumps({"subscribed": True}))
        return
    if args.command == "status":
        with SessionLocal() as db:
            rows = list(
                db.scalars(
                    select(MonitorRun)
                    .where(MonitorRun.source_id == args.source_id)
                    .order_by(MonitorRun.started_at.desc())
                    .limit(20)
                )
            )
            output = [{"run_id": str(r.id), "status": r.status, "result": r.result} for r in rows]
    elif args.command == "run":
        output = asyncio.run(run_source(SessionLocal, args.source_id, config=config)).to_dict()
    else:
        output = [r.to_dict() for r in asyncio.run(run_due(SessionLocal, config=config))]
    print(json.dumps(output, default=str, indent=2))


if __name__ == "__main__":
    main()
