from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.notification import Notification
from app.notifications.config import NotificationConfig
from app.notifications.provider import (
    DeliveryResult,
    EmailMessage,
    EmailNotificationProvider,
    PermanentDeliveryError,
    RetryableDeliveryError,
    get_email_provider,
    validate_recipient_email,
)
from app.notifications.templates import render_notification_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchSummary:
    claimed: int = 0
    sent: int = 0
    retried: int = 0
    permanently_failed: int = 0
    lost_lease: int = 0
    errors: list[str] = field(default_factory=list)


def calculate_backoff_seconds(attempt: int, base_seconds: int, cap_seconds: int) -> int:
    """Bounded exponential backoff: base * 2^(attempt - 1), capped at cap_seconds."""
    if attempt <= 1:
        return min(cap_seconds, base_seconds)
    delay = base_seconds * (2 ** (attempt - 1))
    return min(cap_seconds, delay)


def claim_due_records(
    db: Session,
    config: NotificationConfig,
    *,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Atomically claim a batch of due notifications using SELECT FOR UPDATE SKIP LOCKED.

    Returns (claim_token, list_of_claimed_notification_ids).
    """
    now = now or datetime.now(UTC)
    limit = batch_size or config.batch_size
    claim_token = uuid.uuid4()
    lease_until = now + timedelta(seconds=config.lease_seconds)

    # Concurrency safe: SKIP LOCKED skips rows already locked by another transaction
    candidate_ids = list(
        db.scalars(
            select(Notification.id)
            .where(
                or_(
                    and_(
                        Notification.status.in_(["pending", "failed"]),
                        Notification.available_at <= now,
                    ),
                    and_(
                        Notification.status == "processing",
                        Notification.lease_until <= now,
                    ),
                )
            )
            .order_by(Notification.available_at.asc(), Notification.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )

    if not candidate_ids:
        db.commit()
        return claim_token, []

    records = list(
        db.scalars(
            select(Notification)
            .where(Notification.id.in_(candidate_ids))
            .order_by(Notification.available_at.asc(), Notification.id.asc())
        )
    )

    claimed_ids: list[uuid.UUID] = []
    for item in records:
        # Check recovery window: if crashed during processing past recovery window, fail permanently
        if (
            item.first_attempt_at is not None
            and (now - item.first_attempt_at).total_seconds() > config.recovery_window_seconds
        ):
            item.status = "permanently_failed"
            item.last_error = "Recovery window expired for orphaned delivery"
            item.claim_token = None
            item.lease_until = None
            continue

        item.status = "processing"
        item.claim_token = claim_token
        item.lease_until = lease_until
        item.attempts += 1
        if item.first_attempt_at is None:
            item.first_attempt_at = now
        claimed_ids.append(item.id)

    db.commit()
    return claim_token, claimed_ids


def deliver_claimed_notification(
    factory: sessionmaker[Session],
    notification_id: uuid.UUID,
    claim_token: uuid.UUID,
    provider: EmailNotificationProvider,
    config: NotificationConfig,
) -> tuple[str, str | None]:
    """Execute delivery for a claimed outbox notification and update durable status."""
    with factory.begin() as db:
        record = db.get(Notification, notification_id)
        if record is None or record.status != "processing" or record.claim_token != claim_token:
            return "lost_lease", None
        payload = dict(record.payload)
        attempts = record.attempts

    # Construct idempotent structured message
    idempotency_key = f"jobpulse-{notification_id}"
    try:
        recipient = validate_recipient_email(payload.get("recipient", ""))
    except PermanentDeliveryError as exc:
        error_msg = str(exc)[:500]
        with factory.begin() as db:
            record = db.get(Notification, notification_id)
            if record and record.claim_token == claim_token:
                record.status = "permanently_failed"
                record.last_error = error_msg
                record.claim_token = None
                record.lease_until = None
        return "permanently_failed", error_msg

    subject, text_body, html_body = render_notification_email(payload)
    message = EmailMessage(
        recipient=recipient,
        subject=subject,
        body=text_body,
        html_body=html_body,
        idempotency_key=idempotency_key,
    )

    try:
        result: DeliveryResult = provider.send(message)
        with factory.begin() as db:
            record = db.get(Notification, notification_id)
            if record and record.claim_token == claim_token:
                record.status = "sent"
                record.sent_at = datetime.now(UTC)
                record.provider_id = result.provider_id
                record.claim_token = None
                record.lease_until = None
                record.last_error = None
        return "sent", None
    except RetryableDeliveryError as exc:
        error_msg = str(exc)[:500]
        with factory.begin() as db:
            record = db.get(Notification, notification_id)
            if record and record.claim_token == claim_token:
                if attempts >= config.max_attempts:
                    record.status = "permanently_failed"
                    record.last_error = f"Max attempts ({config.max_attempts}) reached: {error_msg}"
                    record.claim_token = None
                    record.lease_until = None
                    return "permanently_failed", error_msg
                backoff = calculate_backoff_seconds(
                    attempts, config.retry_base_seconds, config.retry_cap_seconds
                )
                record.status = "failed"
                record.available_at = datetime.now(UTC) + timedelta(seconds=backoff)
                record.last_error = error_msg
                record.claim_token = None
                record.lease_until = None
        return "retried", error_msg
    except PermanentDeliveryError as exc:
        error_msg = str(exc)[:500]
        with factory.begin() as db:
            record = db.get(Notification, notification_id)
            if record and record.claim_token == claim_token:
                record.status = "permanently_failed"
                record.last_error = error_msg
                record.claim_token = None
                record.lease_until = None
        return "permanently_failed", error_msg
    except Exception as exc:
        error_msg = f"Unexpected failure: {type(exc).__name__}: {str(exc)}"[:500]
        with factory.begin() as db:
            record = db.get(Notification, notification_id)
            if record and record.claim_token == claim_token:
                if attempts >= config.max_attempts:
                    record.status = "permanently_failed"
                    record.last_error = error_msg
                    record.claim_token = None
                    record.lease_until = None
                    return "permanently_failed", error_msg
                backoff = calculate_backoff_seconds(
                    attempts, config.retry_base_seconds, config.retry_cap_seconds
                )
                record.status = "failed"
                record.available_at = datetime.now(UTC) + timedelta(seconds=backoff)
                record.last_error = error_msg
                record.claim_token = None
                record.lease_until = None
        return "retried", error_msg


class NotificationWorker:
    """Database-backed transactional outbox worker for email notification delivery."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        provider: EmailNotificationProvider | None = None,
        config: NotificationConfig | None = None,
    ):
        self.factory = factory
        self.config = config or NotificationConfig.from_settings()
        self.provider = provider or get_email_provider()

    def process_batch(self, batch_size: int | None = None) -> BatchSummary:
        """Claim and deliver one batch of pending/due notifications."""
        with self.factory() as db:
            claim_token, claimed_ids = claim_due_records(db, self.config, batch_size=batch_size)

        if not claimed_ids:
            return BatchSummary(claimed=0)

        sent = retried = permanently_failed = lost_lease = 0
        errors: list[str] = []

        for notif_id in claimed_ids:
            status, err = deliver_claimed_notification(
                self.factory, notif_id, claim_token, self.provider, self.config
            )
            if status == "sent":
                sent += 1
            elif status == "retried":
                retried += 1
                if err:
                    errors.append(err)
            elif status == "permanently_failed":
                permanently_failed += 1
                if err:
                    errors.append(err)
            elif status == "lost_lease":
                lost_lease += 1

        return BatchSummary(
            claimed=len(claimed_ids),
            sent=sent,
            retried=retried,
            permanently_failed=permanently_failed,
            lost_lease=lost_lease,
            errors=errors,
        )

    def run_once(self) -> BatchSummary:
        """Process all currently due notifications until the queue is drained."""
        total_claimed = total_sent = total_retried = total_failed = total_lost = 0
        all_errors: list[str] = []

        while True:
            batch = self.process_batch()
            if batch.claimed == 0:
                break
            total_claimed += batch.claimed
            total_sent += batch.sent
            total_retried += batch.retried
            total_failed += batch.permanently_failed
            total_lost += batch.lost_lease
            all_errors.extend(batch.errors)

        return BatchSummary(
            claimed=total_claimed,
            sent=total_sent,
            retried=total_retried,
            permanently_failed=total_failed,
            lost_lease=total_lost,
            errors=all_errors,
        )

    async def run_loop(
        self,
        stop_event: asyncio.Event | None = None,
        max_iterations: int | None = None,
    ):
        """Asynchronous execution loop for the outbox worker."""
        iterations = 0
        while stop_event is None or not stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("Error in notification worker iteration: %s", exc)

            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break

            try:
                if stop_event:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.config.tick_seconds)
                else:
                    await asyncio.sleep(self.config.tick_seconds)
            except TimeoutError:
                pass
