"""Verification script for live Resend email delivery.

Usage:
    python scripts/verify_resend.py [--to email@example.com]

Requirements:
    RESEND_API_KEY and EMAIL_FROM must be configured in environment or .env.
    If not provided, the script reports missing configuration with actionable instructions.
"""

import argparse
import os
import sys

# Ensure backend app is on import path
for p in ("/app", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")), os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.core.config import settings
from app.notifications.provider import (
    EmailMessage,
    PermanentDeliveryError,
    ResendEmailProvider,
    RetryableDeliveryError,
)


def verify_resend(recipient: str) -> bool:
    api_key = settings.resend_api_key.get_secret_value() or os.getenv("RESEND_API_KEY", "")
    email_from = settings.email_from or os.getenv("EMAIL_FROM", "")

    if not api_key:
        print("[-] Verification SKIPPED: RESEND_API_KEY is not configured.")
        print("    To enable live Resend testing:")
        print("    1. Set RESEND_API_KEY=re_your_api_key in .env")
        print("    2. Set EMAIL_FROM=\"JobPulse <verified-sender@domain.com>\" in .env")
        print("    3. Set EMAIL_PROVIDER=resend in .env")
        return False

    if not email_from:
        print("[-] Verification FAILED: EMAIL_FROM is not configured.")
        print("    Please set EMAIL_FROM in your environment (e.g. JobPulse <alerts@domain.com>).")
        return False

    print(f"[+] Initializing ResendEmailProvider with sender: {email_from}")
    try:
        provider = ResendEmailProvider(api_key=api_key, from_email=email_from)
        message = EmailMessage(
            recipient=recipient,
            subject="JobPulse — Delivery Verification",
            body="This is a test notification confirming that JobPulse email delivery is operational.",
            html_body="<p>This is a test notification confirming that <strong>JobPulse</strong> email delivery is operational.</p>",
            idempotency_key=f"verify-{os.urandom(8).hex()}",
        )
        print(f"[+] Dispatching test notification to {recipient}...")
        result = provider.send(message)
        print(f"[SUCCESS] Email delivered successfully via Resend!")
        print(f"          Provider Message ID: {result.provider_id}")
        print(f"          Status: {result.status}")
        return True
    except PermanentDeliveryError as exc:
        print(f"[ERROR] Permanent delivery failure: {exc}")
        return False
    except RetryableDeliveryError as exc:
        print(f"[ERROR] Transient / retryable delivery failure: {exc}")
        return False
    except Exception as exc:
        print(f"[ERROR] Unexpected error verifying Resend: {type(exc).__name__}: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify Resend email delivery configuration")
    parser.add_argument(
        "--to",
        default="delivered@resend.dev",
        help="Recipient email address (default: Resend test sink delivered@resend.dev)",
    )
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="Exit with 0 if RESEND_API_KEY is not configured rather than 1",
    )
    args = parser.parse_args()

    api_key = settings.resend_api_key.get_secret_value() or os.getenv("RESEND_API_KEY", "")
    if not api_key and args.allow_skip:
        verify_resend(args.to)
        sys.exit(0)

    success = verify_resend(args.to)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
