"""Business-scoped communication attempts. A provider acceptance is not delivery."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.security import utc_iso
from app.db.models import CommunicationLog, utcnow


def masked(recipient: str) -> str:
    if "@" in recipient:
        local, domain = recipient.split("@", 1)
        return f"{local[:1]}***@{domain}"
    return f"***{recipient[-4:]}"


def start(db: DbSession, business_id: str, transaction_id: str,
          agreement_id: str | None, proposal_id: str | None,
          channel: str, recipient: str) -> CommunicationLog:
    attempt = CommunicationLog(business_id=business_id, transaction_id=transaction_id,
        agreement_id=agreement_id, proposal_id=proposal_id, channel=channel,
        provider="pending", recipient_masked=masked(recipient), status="initiated")
    db.add(attempt)
    db.commit()
    return attempt


def finish(db: DbSession, attempt: CommunicationLog, result: dict | None) -> None:
    attempt.provider = result.get("provider", "legacy") if result else "legacy"
    attempt.provider_message_id = result.get("message_id") if result else None
    attempt.status = result.get("status", "submitted") if result else "submitted"
    attempt.updated_at = utcnow()
    db.commit()


def fail(db: DbSession, attempt: CommunicationLog, detail: str) -> None:
    attempt.status = "failed"
    attempt.detail = detail[:300]
    attempt.updated_at = utcnow()
    db.commit()


def update_from_webhook(db: DbSession, provider: str, message_id: str, status: str) -> bool:
    attempt = db.scalar(select(CommunicationLog).where(
        CommunicationLog.provider == provider,
        CommunicationLog.provider_message_id == message_id))
    if attempt is None:
        return False
    if attempt.status not in {"delivered", "failed"}:
        attempt.status = status
        attempt.updated_at = utcnow()
        db.commit()
    return True


def list_for_transaction(db: DbSession, business_id: str, transaction_id: str) -> list[dict]:
    rows = db.scalars(select(CommunicationLog).where(
        CommunicationLog.business_id == business_id,
        CommunicationLog.transaction_id == transaction_id)
        .order_by(CommunicationLog.created_at.desc())).all()
    return [{"id": row.id, "channel": row.channel, "provider": row.provider,
        "recipient_masked": row.recipient_masked, "status": row.status,
        "detail": row.detail, "created_at": utc_iso(row.created_at),
        "updated_at": utc_iso(row.updated_at)} for row in rows]
