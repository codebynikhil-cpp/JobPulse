from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from email_validator import EmailNotValidError, validate_email

from app.core.config import Settings
from app.core.config import settings as global_settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class NotificationError(Exception):
    """Base class for all notification failures."""


class RetryableDeliveryError(NotificationError):
    """Transient delivery failure that should be retried with exponential backoff."""


class PermanentDeliveryError(NotificationError):
    """Permanent delivery failure that must not be retried."""


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    body: str
    html_body: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    provider_id: str
    status: str = "sent"


def validate_recipient_email(address: str) -> str:
    """Validate and normalize recipient email. Raises PermanentDeliveryError if invalid."""
    if not address or not isinstance(address, str):
        raise PermanentDeliveryError("Recipient email address is missing or empty")
    try:
        info = validate_email(address, check_deliverability=False)
        return info.normalized
    except EmailNotValidError as exc:
        raise PermanentDeliveryError(f"Invalid recipient email address: {exc}") from exc


class NotificationProvider(ABC):
    """Abstract root for notification providers."""

    @abstractmethod
    def send(self, message: EmailMessage) -> DeliveryResult:
        """Deliver a structured notification message."""


class EmailNotificationProvider(NotificationProvider):
    """Base class for email notification providers."""

    @abstractmethod
    def send(self, message: EmailMessage) -> DeliveryResult:
        """Deliver an email message."""


class DisabledEmailProvider(EmailNotificationProvider):
    """Provider used when notifications or email delivery is disabled."""

    def send(self, message: EmailMessage) -> DeliveryResult:
        validate_recipient_email(message.recipient)
        logger.info(
            "Email notifications disabled; suppressing message",
            extra={"recipient": message.recipient, "subject": message.subject},
        )
        return DeliveryResult(provider_id="disabled-sink", status="sent")


class ResendEmailProvider(EmailNotificationProvider):
    """Vendor-specific email delivery via Resend HTTP API with idempotency support."""

    def __init__(
        self,
        api_key: str,
        from_email: str,
        *,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ):
        if not api_key:
            raise PermanentDeliveryError("Resend API key is not configured")
        if not from_email:
            raise PermanentDeliveryError("Email sender address (email_from) is not configured")
        self._api_key = api_key
        self._from_email = from_email
        self._timeout = timeout_seconds
        self._client = client

    def send(self, message: EmailMessage) -> DeliveryResult:
        recipient = validate_recipient_email(message.recipient)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "JobPulse-NotificationWorker/1.0",
        }
        if message.idempotency_key:
            headers["Idempotency-Key"] = message.idempotency_key

        payload = {
            "from": self._from_email,
            "to": [recipient],
            "subject": message.subject,
            "text": message.body,
        }
        if message.html_body:
            payload["html"] = message.html_body

        should_close = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self._timeout)
            should_close = True

        try:
            # Enforce hardcoded endpoint to prevent SSRF
            response = client.post(RESEND_API_URL, headers=headers, json=payload)
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.NetworkError,
        ) as exc:
            raise RetryableDeliveryError(
                f"Transient network error connecting to Resend: {type(exc).__name__}"
            ) from exc
        except Exception as exc:
            raise RetryableDeliveryError(
                f"Unexpected HTTP client failure: {type(exc).__name__}"
            ) from exc
        finally:
            if should_close:
                client.close()

        status = response.status_code
        if status in (200, 201):
            try:
                data = response.json()
                provider_id = str(data.get("id") or "resend-ok")
            except Exception:
                provider_id = "resend-ok"
            logger.info(
                "Resend delivered email successfully",
                extra={
                    "recipient": recipient,
                    "provider_id": provider_id,
                    "idempotency_key": message.idempotency_key,
                },
            )
            return DeliveryResult(provider_id=provider_id, status="sent")

        if status == 429:
            raise RetryableDeliveryError(
                f"Rate limited by Resend (HTTP 429): {response.text[:200]}"
            )

        if status >= 500:
            raise RetryableDeliveryError(
                f"Transient Resend server failure (HTTP {status}): {response.text[:200]}"
            )

        if status in (401, 403):
            raise PermanentDeliveryError(
                f"Resend authentication/authorization failure (HTTP {status})"
            )

        # 400, 422 or other 4xx errors are permanent client/payload errors
        raise PermanentDeliveryError(
            f"Resend permanent rejection (HTTP {status}): {response.text[:200]}"
        )


class MockEmailProvider(EmailNotificationProvider):
    """Configurable mock email provider for deterministic testing."""

    def __init__(self):
        self.sent_messages: list[EmailMessage] = []
        self.fail_transient_attempts: dict[str, int] = {}
        self.fail_permanent_recipients: set[str] = set()
        self.call_count: dict[str, int] = {}

    def fail_transiently_for(self, key: str, count: int = 1):
        """Simulate transient failures for key (recipient or idempotency key) for count attempts."""
        self.fail_transient_attempts[key] = count

    def fail_permanently_for(self, recipient: str):
        """Simulate permanent failure for recipient."""
        self.fail_permanent_recipients.add(recipient)

    def send(self, message: EmailMessage) -> DeliveryResult:
        validate_recipient_email(message.recipient)
        key = message.idempotency_key or message.recipient
        self.call_count[key] = self.call_count.get(key, 0) + 1

        # Check permanent failure
        if message.recipient in self.fail_permanent_recipients or any(
            target in message.recipient for target in self.fail_permanent_recipients
        ):
            raise PermanentDeliveryError(f"Permanent rejection simulated for {message.recipient}")

        # Check transient failure
        for k in (key, message.recipient):
            if k in self.fail_transient_attempts and self.fail_transient_attempts[k] > 0:
                self.fail_transient_attempts[k] -= 1
                raise RetryableDeliveryError(
                    f"Transient error simulated for {k} (attempts left: {self.fail_transient_attempts[k]})"
                )

        for target, rem in list(self.fail_transient_attempts.items()):
            if rem > 0 and (
                target in message.recipient
                or (message.idempotency_key and target in message.idempotency_key)
            ):
                self.fail_transient_attempts[target] = rem - 1
                raise RetryableDeliveryError(
                    f"Transient error simulated for {target} (attempts left: {rem - 1})"
                )

        self.sent_messages.append(message)
        provider_id = f"mock-{uuid.uuid4().hex[:12]}"
        return DeliveryResult(provider_id=provider_id, status="sent")

    def reset(self):
        self.sent_messages.clear()
        self.fail_transient_attempts.clear()
        self.fail_permanent_recipients.clear()
        self.call_count.clear()


def get_email_provider(app_settings: Settings | None = None) -> EmailNotificationProvider:
    """Factory resolving the configured email notification provider."""
    cfg = app_settings or global_settings
    if not cfg.notifications_enabled or cfg.email_provider == "disabled":
        return DisabledEmailProvider()

    if cfg.email_provider == "resend":
        api_key = cfg.resend_api_key.get_secret_value()
        return ResendEmailProvider(api_key=api_key, from_email=cfg.email_from)

    return DisabledEmailProvider()
