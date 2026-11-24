"""Africa's Talking sandbox USSD approval with a phone-bound, one-time PIN."""

import re
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.delivery import send_message
from app.core.security import as_utc, hash_password, utc_iso, verify_password
from app.db.models import (Agreement, AgreementInvitation, Business, ConfirmationEvent,
                           Counterparty, Transaction, UssdApproval, utcnow)
from app.modules import agreements, communications, vault


def phone_key(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def send_request(db: DbSession, business_id: str, agreement_id: str, user_id: str) -> dict:
    if not (settings.at_sandbox and settings.at_api_key and settings.ussd_callback_token):
        raise HTTPException(503, "Africa's Talking sandbox USSD is not configured")
    agreement = agreements.require_agreement(db, business_id, agreement_id)
    transaction = db.get(Transaction, agreement.transaction_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    if not customer.phone:
        raise HTTPException(422, "Customer phone is required for USSD")
    invitation = agreements.create_invitation(db, business_id, agreement_id, user_id)
    pin = f"{secrets.randbelow(1_000_000):06d}"
    reference = secrets.token_hex(4).upper()
    approval = UssdApproval(invitation_id=invitation["invitation_id"], reference=reference,
        code_hash=hash_password(pin), expires_at=utcnow() + timedelta(minutes=15), attempts=0)
    db.add(approval)
    db.commit()
    attempt = communications.start(db, business_id, transaction.id, agreement.id, None,
        "sms", customer.phone)
    try:
        result = send_message("sms", customer.phone, "MyBizVault USSD review",
            f"MyBizVault agreement review reference {reference}, code {pin}. Dial your sandbox USSD code, enter the reference and code, then review the terms. Expires in 15 minutes. Do not share the code.")
    except HTTPException as failure:
        approval.consumed_at = utcnow()
        db.commit()
        communications.fail(db, attempt, str(failure.detail))
        return {"status": "failed", "review_url": invitation["review_url"],
                "error": "Sandbox SMS submission failed; share the review link manually"}
    communications.finish(db, attempt, result)
    agreements.audit(db, agreement, "ussd_code_submitted", invitation["version_id"], user_id,
        "Phone-bound sandbox code submitted; delivery and legal identity not independently verified")
    db.commit()
    return {"status": attempt.status, "reference": reference,
            "expires_at": utc_iso(approval.expires_at), "review_url": invitation["review_url"]}


def _lookup(db: DbSession, reference: str, phone: str):
    approval = db.scalar(select(UssdApproval).where(UssdApproval.reference == reference.upper()).with_for_update())
    if approval is None or approval.consumed_at or as_utc(approval.expires_at) <= utcnow() or approval.attempts >= 5:
        return None
    invitation = db.get(AgreementInvitation, approval.invitation_id)
    if not invitation or invitation.revoked_at or invitation.completed_at or as_utc(invitation.expires_at) <= utcnow():
        return None
    agreement = db.get(Agreement, invitation.agreement_id)
    if not agreement or agreement.status != "invited":
        return None
    version = agreements.current_version(db, agreement)
    customer = db.get(Counterparty, invitation.counterparty_id)
    transaction = db.get(Transaction, agreement.transaction_id)
    if (version.id != invitation.agreement_version_id or not customer or not transaction or
            transaction.counterparty_id != customer.id or customer.business_id != agreement.business_id or
            phone_key(customer.phone) != phone_key(phone) or len(phone_key(phone)) < 10):
        return None
    return approval, invitation, agreement, version, customer, transaction


def callback(db: DbSession, phone: str, text: str) -> str:
    if not (settings.at_sandbox and settings.ussd_callback_token):
        return "END USSD approval is unavailable."
    parts = text.strip().split("*") if text.strip() else []
    if not parts:
        return "CON MyBizVault agreement review. Enter the 8-character reference from your SMS:"
    if len(parts) > 3 or not re.fullmatch(r"[0-9A-Fa-f]{8}", parts[0]):
        return "END Invalid reference."
    found = _lookup(db, parts[0], phone)
    if not found:
        return "END No pending agreement for this phone and reference."
    approval, invitation, agreement, version, customer, transaction = found
    if len(parts) == 1:
        return "CON Enter the 6-digit code sent to this phone:"
    if not re.fullmatch(r"[0-9]{6}", parts[1]) or not verify_password(parts[1], approval.code_hash):
        approval.attempts += 1
        db.commit()
        return "END Incorrect or expired code."
    balance = transaction.total_ugx - transaction.paid_ugx
    if len(parts) == 2:
        summary = (f"Agreement v{version.version}: {transaction.description[:70]}. "
            f"Seller {db.get(Business, agreement.business_id).name}; "
            f"buyer {customer.display_name}. Total UGX {transaction.total_ugx:,}; "
            f"paid UGX {transaction.paid_ugx:,}; due UGX {balance:,} by {transaction.due_date}. "
            "1 Accept  2 Reject")
        return "CON " + summary
    if parts[2] not in {"1", "2"}:
        return "END Select 1 to accept or 2 to reject."
    action = "accepted" if parts[2] == "1" else "rejected"
    now = utcnow()
    changed = db.execute(update(Agreement).where(
        Agreement.id == agreement.id, Agreement.status == "invited",
        Agreement.current_version == version.version).values(
        status="confirmed" if action == "accepted" else "rejected"))
    consumed = db.execute(update(UssdApproval).where(UssdApproval.id == approval.id,
        UssdApproval.consumed_at.is_(None), UssdApproval.attempts < 5,
        UssdApproval.expires_at > now).values(consumed_at=now)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1 or consumed.rowcount != 1:
        db.rollback()
        return "END Agreement already responded to or expired."
    if action == "accepted":
        invitation.completed_at = now
    else:
        invitation.revoked_at = now
    db.add(ConfirmationEvent(agreement_id=agreement.id, agreement_version_id=version.id,
        invitation_id=invitation.id, counterparty_id=customer.id, action=action,
        verification_method="ussd_sandbox_phone_pin", note="Sandbox phone and PIN match; legal identity not independently verified"))
    agreements.audit(db, agreement, f"ussd_{action}", version.id,
        detail="Explicit sandbox USSD response; identity not independently verified")
    key = provider = None
    try:
        if action == "accepted":
            _document, key, provider = vault.stage_confirmed_agreement(db, agreement, version)
        db.commit()
    except IntegrityError:
        db.rollback()
        if provider:
            vault.cleanup(provider, key)
        return "END Agreement response could not be saved."
    except Exception:
        db.rollback()
        if provider:
            vault.cleanup(provider, key)
        raise
    return "END Agreement version " + str(version.version) + (" accepted." if action == "accepted" else " rejected.")
