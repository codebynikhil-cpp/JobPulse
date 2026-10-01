from app.notifications.config import NotificationConfig
from app.notifications.metrics import NotificationMetrics, get_notification_metrics
from app.notifications.outbox import (
    enqueue_matches,
    material_fields,
    material_hash,
    previous_relevant_users,
)
from app.notifications.provider import (
    DeliveryResult,
    DisabledEmailProvider,
    EmailMessage,
    EmailNotificationProvider,
    MockEmailProvider,
    NotificationError,
    NotificationProvider,
    PermanentDeliveryError,
    ResendEmailProvider,
    RetryableDeliveryError,
    get_email_provider,
)
from app.notifications.templates import render_notification_email
from app.notifications.worker import BatchSummary, NotificationWorker

__all__ = [
    "BatchSummary",
    "DeliveryResult",
    "DisabledEmailProvider",
    "EmailMessage",
    "EmailNotificationProvider",
    "MockEmailProvider",
    "NotificationConfig",
    "NotificationError",
    "NotificationMetrics",
    "NotificationProvider",
    "NotificationWorker",
    "PermanentDeliveryError",
    "ResendEmailProvider",
    "RetryableDeliveryError",
    "enqueue_matches",
    "get_email_provider",
    "get_notification_metrics",
    "material_fields",
    "material_hash",
    "previous_relevant_users",
    "render_notification_email",
]
