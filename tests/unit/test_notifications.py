from __future__ import annotations

import httpx
import pytest

from app.notifications.provider import (
    DeliveryResult,
    DisabledEmailProvider,
    EmailMessage,
    MockEmailProvider,
    PermanentDeliveryError,
    ResendEmailProvider,
    RetryableDeliveryError,
    validate_recipient_email,
)
from app.notifications.templates import render_notification_email
from app.notifications.worker import calculate_backoff_seconds


def test_validate_recipient_email():
    assert validate_recipient_email("alice@example.com") == "alice@example.com"
    assert (
        validate_recipient_email("User.Name+tag@sub.example.co.uk")
        == "User.Name+tag@sub.example.co.uk"
    )

    with pytest.raises(PermanentDeliveryError):
        validate_recipient_email("")
    with pytest.raises(PermanentDeliveryError):
        validate_recipient_email("not-an-email")
    with pytest.raises(PermanentDeliveryError):
        validate_recipient_email(None)


def test_calculate_backoff_seconds():
    # base 60, cap 3600
    assert calculate_backoff_seconds(1, 60, 3600) == 60
    assert calculate_backoff_seconds(2, 60, 3600) == 120
    assert calculate_backoff_seconds(3, 60, 3600) == 240
    assert calculate_backoff_seconds(4, 60, 3600) == 480
    assert calculate_backoff_seconds(10, 60, 3600) == 3600  # capped


def test_render_notification_email_escaping_and_content():
    payload = {
        "company": "Acme <script>alert('corp')</script>",
        "job": {
            "title": "Backend Lead & Architect",
            "location": "Bengaluru <b>HQ</b>",
            "employment_type": "full_time",
            "min_exp_years": 3.0,
            "max_exp_years": 7.0,
            "application_url": "https://careers.acme.com/job/123",
            "career_url": "https://careers.acme.com",
        },
        "profiles": [
            {
                "name": "Profile <1>",
                "score": 0.85,
                "evidence": {
                    "breakdown": {
                        "matched_roles": ["Backend Lead"],
                        "matched_skills": ["Python", "FastAPI"],
                    }
                },
            },
            {
                "name": "Profile 2",
                "score": 0.92,
                "evidence": {
                    "summary": "Strong architecture match",
                },
            },
        ],
    }

    subject, text, html_body = render_notification_email(payload)

    # Subject line
    assert "Acme <script>alert('corp')</script>" in subject
    assert "Backend Lead & Architect" in subject

    # Plain text content
    assert "Acme <script>alert('corp')</script>" in text
    assert "Experience: 3.0 - 7.0 years" in text
    assert "Profile <1> (Score: 85%)" in text
    assert "Profile 2 (Score: 92%)" in text
    assert "Matched role(s): Backend Lead" in text
    assert "Application URL: https://careers.acme.com/job/123" in text

    # HTML content strictly escaped
    assert "<script>" not in html_body
    assert "&lt;script&gt;alert(&#x27;corp&#x27;)&lt;/script&gt;" in html_body
    assert "&lt;b&gt;HQ&lt;/b&gt;" in html_body
    assert "Profile &lt;1&gt;" in html_body
    assert "href='https://careers.acme.com/job/123'" in html_body
    assert "85%" in html_body


def test_render_notification_email_unsafe_url_sanitization():
    payload = {
        "company": "Corp",
        "job": {
            "title": "Dev",
            "application_url": "javascript:alert(1)",
        },
        "profiles": [],
    }
    _, text, html_body = render_notification_email(payload)
    assert "javascript:" not in text
    assert "javascript:" not in html_body
    assert "href=" not in html_body


def test_render_notification_email_missing_fields_no_fabrication():
    payload = {
        "company": "",
        "job": {},
        "profiles": [],
    }
    subject, text, html_body = render_notification_email(payload)
    assert "Company" in subject
    assert "Open Position" in subject
    assert "Experience" not in text
    assert "Location" not in text


def test_mock_email_provider():
    mock = MockEmailProvider()
    msg = EmailMessage(
        recipient="user@example.com",
        subject="Test",
        body="Body",
        idempotency_key="key-1",
    )

    # Initial send succeeds
    result = mock.send(msg)
    assert isinstance(result, DeliveryResult)
    assert result.status == "sent"
    assert len(mock.sent_messages) == 1
    assert mock.call_count["key-1"] == 1

    # Simulate transient failure
    mock.fail_transiently_for("key-2", count=2)
    msg2 = EmailMessage(
        recipient="user@example.com",
        subject="Test 2",
        body="Body",
        idempotency_key="key-2",
    )
    with pytest.raises(RetryableDeliveryError):
        mock.send(msg2)
    with pytest.raises(RetryableDeliveryError):
        mock.send(msg2)
    # Third attempt succeeds
    res2 = mock.send(msg2)
    assert res2.status == "sent"

    # Simulate permanent failure
    mock.fail_permanently_for("invalid@example.com")
    msg3 = EmailMessage(
        recipient="invalid@example.com",
        subject="Test 3",
        body="Body",
    )
    with pytest.raises(PermanentDeliveryError):
        mock.send(msg3)


def test_disabled_email_provider():
    disabled = DisabledEmailProvider()
    msg = EmailMessage(recipient="user@example.com", subject="Hi", body="Text")
    res = disabled.send(msg)
    assert res.provider_id == "disabled-sink"
    assert res.status == "cancelled"


def test_resend_email_provider_success():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer re_test_key"
        assert request.headers["Idempotency-Key"] == "idem-123"
        return httpx.Response(200, json={"id": "email_xyz123"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = ResendEmailProvider(
        api_key="re_test_key",
        from_email="alerts@jobpulse.io",
        client=client,
    )

    msg = EmailMessage(
        recipient="candidate@example.com",
        subject="New Match",
        body="You matched!",
        html_body="<p>You matched!</p>",
        idempotency_key="idem-123",
    )
    result = provider.send(msg)
    assert result.provider_id == "email_xyz123"
    assert result.status == "sent"


def test_resend_email_provider_retryable_errors():
    # 429 Rate Limit
    t429 = httpx.MockTransport(lambda r: httpx.Response(429, text="Rate limit exceeded"))
    p429 = ResendEmailProvider("re_key", "from@example.com", client=httpx.Client(transport=t429))
    msg = EmailMessage("a@example.com", "Sub", "Body")
    with pytest.raises(RetryableDeliveryError):
        p429.send(msg)

    # 503 Service Unavailable
    t503 = httpx.MockTransport(lambda r: httpx.Response(503, text="Service Unavailable"))
    p503 = ResendEmailProvider("re_key", "from@example.com", client=httpx.Client(transport=t503))
    with pytest.raises(RetryableDeliveryError):
        p503.send(msg)


def test_resend_email_provider_permanent_errors():
    # 401 Unauthorized
    t401 = httpx.MockTransport(lambda r: httpx.Response(401, text="Unauthorized API key"))
    p401 = ResendEmailProvider("re_key", "from@example.com", client=httpx.Client(transport=t401))
    msg = EmailMessage("a@example.com", "Sub", "Body")
    with pytest.raises(PermanentDeliveryError):
        p401.send(msg)

    # 422 Unprocessable
    t422 = httpx.MockTransport(lambda r: httpx.Response(422, text="Domain not verified"))
    p422 = ResendEmailProvider("re_key", "from@example.com", client=httpx.Client(transport=t422))
    with pytest.raises(PermanentDeliveryError):
        p422.send(msg)
