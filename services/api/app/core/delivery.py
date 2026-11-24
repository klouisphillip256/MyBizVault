"""Optional operator-configured outbound email and SMS. No implicit sends."""

import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.core.config import settings


def capabilities() -> dict[str, bool]:
    return {"email": bool(settings.smtp_host and settings.smtp_from),
            "sms": bool(settings.sms_webhook_url and settings.sms_webhook_token and
                        urlparse(settings.sms_webhook_url).scheme == "https")}


def check_delivery(channel: str, recipient: str | None) -> None:
    if not recipient:
        raise HTTPException(422, f"Counterparty has no {channel} contact")
    if channel == "email":
        if not settings.smtp_host or not settings.smtp_from:
            raise HTTPException(503, "Email delivery is not configured")
        return
    if channel == "sms":
        endpoint = settings.sms_webhook_url
        if not endpoint or not settings.sms_webhook_token:
            raise HTTPException(503, "SMS delivery is not configured")
        if urlparse(endpoint).scheme != "https":
            raise HTTPException(503, "SMS delivery requires an HTTPS endpoint")
        return
    raise HTTPException(422, "Unknown delivery channel")


def send_message(channel: str, recipient: str | None, subject: str, body: str) -> None:
    check_delivery(channel, recipient)
    assert recipient is not None
    if channel == "email":
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = " ".join(subject.splitlines())
        message.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
                client.starttls(context=ssl.create_default_context())
                if settings.smtp_username and settings.smtp_password:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(message)
        except (OSError, ValueError, smtplib.SMTPException):
            raise HTTPException(503, "Email delivery failed") from None
        return
    if channel == "sms":
        endpoint = settings.sms_webhook_url
        assert endpoint is not None
        request = Request(endpoint, data=json.dumps({"to": recipient, "message": body}).encode(),
                          headers={"Content-Type": "application/json",
                                   "Authorization": f"Bearer {settings.sms_webhook_token}"}, method="POST")
        try:
            with urlopen(request, timeout=10) as response:
                if response.status < 200 or response.status >= 300:
                    raise HTTPException(503, "SMS delivery failed")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "SMS delivery failed") from None
        return
    raise HTTPException(422, "Unknown delivery channel")
