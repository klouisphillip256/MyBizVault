"""Read-only provider probes and authenticated delivery status webhooks."""

import hashlib
import hmac
import json
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.db.models import Membership
from app.db.session import get_db
from app.modules import communications
from app.modules.business import require_owner

router = APIRouter(prefix="/api")


def _probe(url: str, headers: dict[str, str]) -> bool:
    try:
        with urlopen(UrlRequest(url, headers=headers), timeout=8) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _brevo_sender_status() -> str:
    if not settings.brevo_api_key or not settings.brevo_sender_email:
        return "unconfigured"
    try:
        with urlopen(UrlRequest("https://api.brevo.com/v3/senders",
                             headers={"api-key": settings.brevo_api_key}), timeout=8) as response:
            senders = json.load(response).get("senders", [])
    except Exception:
        return "check_failed"
    sender = next((item for item in senders if
                   item.get("email", "").casefold() == settings.brevo_sender_email.casefold()), None)
    if sender is None:
        return "not_found"
    return "active" if sender.get("active") is True else "inactive"


@router.get("/businesses/{business_id}/delivery/provider-tests")
def provider_tests(business_id: str, _owner: Membership = Depends(require_owner)):
    """Check credentials without sending any customer communication."""
    results = {"brevo": "unconfigured", "africas_talking": "unconfigured",
               "meta_whatsapp": "unconfigured"}
    if settings.brevo_api_key:
        results["brevo"] = "connected" if _probe("https://api.brevo.com/v3/account",
            {"api-key": settings.brevo_api_key}) else "failed"
    results["brevo_sender"] = _brevo_sender_status()
    if settings.at_api_key and settings.at_username:
        host = "api.sandbox.africastalking.com" if settings.at_sandbox else "api.africastalking.com"
        url = f"https://{host}/version1/user?{urlencode({'username': settings.at_username})}"
        results["africas_talking"] = "connected" if _probe(url,
            {"apiKey": settings.at_api_key}) else "failed"
    if settings.whatsapp_access_token and settings.whatsapp_phone_number_id:
        url = f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}?fields=id,display_phone_number"
        results["meta_whatsapp"] = "connected" if _probe(url,
            {"Authorization": f"Bearer {settings.whatsapp_access_token}"}) else "failed"
    return results


def _require_token(actual: str | None, expected: str | None) -> None:
    if not expected or not actual or not hmac.compare_digest(actual, expected):
        raise HTTPException(403, "Webhook authentication failed")


@router.post("/webhooks/brevo")
async def brevo_webhook(request: Request, authorization: str | None = Header(None),
                        db: DbSession = Depends(get_db)):
    _require_token(authorization.removeprefix("Bearer ") if authorization else None,
                   settings.brevo_webhook_token)
    payload = await request.json()
    events = payload if isinstance(payload, list) else [payload]
    updated = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        message_id = event.get("message-id") or event.get("messageId")
        kind = event.get("event")
        status = "delivered" if kind == "delivered" else "failed" if kind in {
            "hard_bounce", "soft_bounce", "blocked", "invalid", "error"} else None
        if message_id and status:
            updated += communications.update_from_webhook(db, "brevo", str(message_id), status)
    return {"updated": updated}


@router.post("/webhooks/africas-talking")
async def at_delivery_webhook(request: Request, x_webhook_token: str | None = Header(None),
                              db: DbSession = Depends(get_db)):
    _require_token(x_webhook_token or request.query_params.get("token"), settings.at_webhook_token)
    form = await request.form()
    message_id = str(form.get("id") or form.get("messageId") or "")
    provider_status = str(form.get("status") or "").lower()
    status = "delivered" if provider_status == "success" else "failed" if provider_status in {
        "failed", "rejected", "expired"} else None
    updated = communications.update_from_webhook(db, "africas_talking", message_id, status) if message_id and status else False
    return {"updated": int(updated)}


@router.get("/webhooks/meta")
def meta_verify(request: Request):
    params = request.query_params
    _require_token(params.get("hub.verify_token"), settings.meta_verify_token)
    if params.get("hub.mode") != "subscribe":
        raise HTTPException(403, "Webhook verification failed")
    return Response(params.get("hub.challenge") or "", media_type="text/plain")


@router.post("/webhooks/meta")
async def meta_webhook(request: Request, x_hub_signature_256: str | None = Header(None),
                       db: DbSession = Depends(get_db)):
    raw = await request.body()
    if not settings.meta_app_secret or not x_hub_signature_256:
        raise HTTPException(403, "Webhook authentication failed")
    expected = "sha256=" + hmac.new(settings.meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(x_hub_signature_256, expected):
        raise HTTPException(403, "Webhook authentication failed")
    payload = await request.json()
    updated = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for item in change.get("value", {}).get("statuses", []):
                state = item.get("status")
                status = "delivered" if state in {"delivered", "read"} else "failed" if state == "failed" else None
                if status and item.get("id"):
                    updated += communications.update_from_webhook(db, "meta_whatsapp", item["id"], status)
    return {"updated": updated}
