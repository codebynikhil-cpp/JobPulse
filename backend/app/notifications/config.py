from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = True
    changed_policy: Literal["material", "newly_relevant", "off"] = "material"
    max_attempts: int = 5
    retry_base_seconds: int = 60
    retry_cap_seconds: int = 3600
    lease_seconds: int = 120
    tick_seconds: float = 10
    batch_size: int = 50
    # Stop automatic ambiguous recovery before Resend's 24-hour key expiry.
    recovery_window_seconds: int = 23 * 3600

    def __post_init__(self):
        if self.changed_policy not in ("material", "newly_relevant", "off"):
            raise ValueError("Invalid changed-job policy")
        if not (1 <= self.max_attempts <= 10 and 30 <= self.lease_seconds <= 3600):
            raise ValueError("Invalid retry/lease limits")
        if (
            min(
                self.retry_base_seconds,
                self.retry_cap_seconds,
                self.tick_seconds,
                self.batch_size,
                self.recovery_window_seconds,
            )
            <= 0
        ):
            raise ValueError("Notification limits must be positive")
        if self.recovery_window_seconds > 23 * 3600:
            raise ValueError("Recovery must remain inside provider idempotency window")

    @classmethod
    def from_settings(cls):
        from app.core.config import settings

        return cls(
            enabled=settings.notifications_enabled,
            changed_policy=settings.notification_changed_policy,
            max_attempts=settings.notification_max_attempts,
            retry_base_seconds=settings.notification_retry_base_seconds,
            retry_cap_seconds=settings.notification_retry_cap_seconds,
            lease_seconds=settings.notification_lease_seconds,
            tick_seconds=settings.notification_tick_seconds,
            batch_size=settings.notification_batch_size,
        )
