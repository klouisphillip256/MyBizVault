"""Optional provider submissions. No implicit customer sends."""

import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.core.config import settings


def capabilities() -> dict[str, bool]:
    return {"email": bool((settings.brevo_api_key and settings.brevo_sender_email) or
                          (settings.smtp_host and settings.smtp_from)),
            "sms": bool(settings.at_api_key and settings.at_username or
                        (settings.sms_webhook_url and settings.sms_webhook_token and
                         urlparse(settings.sms_webhook_url).scheme == "https")),
            "whatsapp": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
            "ussd": bool(settings.at_sandbox and settings.at_api_key and settings.ussd_callback_token)}


def check_delivery(channel: str, recipient: str | None) -> None:
    if not recipient:
        raise HTTPException(422, f"Counterparty has no {channel} contact")
    if channel == "email":
        if not capabilities()["email"]:
            raise HTTPException(503, "Email delivery is not configured")
        return
    if channel == "sms":
        if settings.at_api_key and settings.at_username:
            return
        endpoint = settings.sms_webhook_url
        if not endpoint or not settings.sms_webhook_token:
            raise HTTPException(503, "SMS delivery is not configured")
        if urlparse(endpoint).scheme != "https":
            raise HTTPException(503, "SMS delivery requires an HTTPS endpoint")
        return
    if channel == "whatsapp":
        if not capabilities()["whatsapp"]:
            raise HTTPException(503, "WhatsApp delivery is not configured")
        return
    raise HTTPException(422, "Unknown delivery channel")


def _json_request(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode() or "{}")
    except Exception:
        raise HTTPException(503, "Provider submission failed") from None


def send_message(channel: str, recipient: str | None, subject: str, body: str) -> dict | None:
    check_delivery(channel, recipient)
    assert recipient is not None
    if channel == "email" and settings.brevo_api_key and settings.brevo_sender_email:
        result = _json_request("https://api.brevo.com/v3/smtp/email", {
            "sender": {"email": settings.brevo_sender_email, "name": settings.brevo_sender_name},
            "to": [{"email": recipient}], "subject": " ".join(subject.splitlines()),
            "textContent": body}, {"api-key": settings.brevo_api_key})
        return {"provider": "brevo", "status": "submitted", "message_id": result.get("messageId")}
    if channel == "sms" and settings.at_api_key and settings.at_username:
        host = "api.sandbox.africastalking.com" if settings.at_sandbox else "api.africastalking.com"
        request = Request(f"https://{host}/version1/messaging",
            data=urlencode({"username": settings.at_username, "to": recipient, "message": body}).encode(),
            headers={"apiKey": settings.at_api_key,
                     "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode())
            entry = result["SMSMessageData"]["Recipients"][0]
            if entry.get("status") != "Success":
                raise HTTPException(503, "SMS provider rejected the message")
            return {"provider": "africas_talking", "status": "simulated" if settings.at_sandbox else "submitted",
                    "message_id": entry.get("messageId")}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "SMS provider submission failed") from None
    if channel == "whatsapp":
        result = _json_request(
            f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages",
            {"messaging_product": "whatsapp", "to": recipient, "type": "text",
             "text": {"preview_url": True, "body": body}},
            {"Authorization": f"Bearer {settings.whatsapp_access_token}"})
        message_id = (result.get("messages") or [{}])[0].get("id")
        if not message_id:
            raise HTTPException(503, "WhatsApp provider did not return a message ID")
        return {"provider": "meta_whatsapp", "status": "simulated" if settings.whatsapp_test_mode else "submitted",
                "message_id": message_id}
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
        return {"provider": "smtp", "status": "submitted", "message_id": None}
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
        return {"provider": "sms_webhook", "status": "submitted", "message_id": None}
    raise HTTPException(422, "Unknown delivery channel")
