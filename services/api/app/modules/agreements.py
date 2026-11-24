import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.delivery import check_delivery, send_message
from app.core.security import as_utc, digest, hash_password, utc_iso, verify_password
from app.db.models import (Agreement, AgreementInvitation, AgreementVersion, AuditEvent,
                           Business, ConfirmationChallenge, ConfirmationEvent, Counterparty,
                           Transaction, utcnow)
from app.modules import vault


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def current_version(db: DbSession, agreement: Agreement) -> AgreementVersion:
    version = db.scalar(select(AgreementVersion).where(AgreementVersion.agreement_id == agreement.id,
                                                       AgreementVersion.version == agreement.current_version))
    if version is None or content_digest(version.content) != version.content_sha256:
        raise HTTPException(409, "Agreement version integrity check failed")
    return version


def require_agreement(db: DbSession, business_id: str, agreement_id: str) -> Agreement:
    agreement = db.scalar(select(Agreement).where(Agreement.id == agreement_id,
                                                  Agreement.business_id == business_id))
    if agreement is None:
        raise HTTPException(404, "Agreement not found")
    return agreement


def audit(db: DbSession, agreement: Agreement, action: str, version_id: str | None,
          user_id: str | None = None, detail: str | None = None) -> None:
    db.add(AuditEvent(business_id=agreement.business_id, agreement_id=agreement.id,
                      agreement_version_id=version_id, actor_user_id=user_id,
                      action=action, detail=detail))


def version_data(version: AgreementVersion) -> dict:
    return {"id": version.id, "version": version.version, "content": version.content,
            "content_sha256": version.content_sha256, "created_at": utc_iso(version.created_at)}


def summary(db: DbSession, agreement: Agreement) -> dict:
    transaction = db.get(Transaction, agreement.transaction_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    version = current_version(db, agreement)
    return {"id": agreement.id, "transaction_id": transaction.id, "counterparty_name": customer.display_name,
            "status": agreement.status, "current_version": agreement.current_version,
            "current_version_id": version.id, "content_sha256": version.content_sha256,
            "balance_ugx": transaction.total_ugx - transaction.paid_ugx,
            "created_at": utc_iso(agreement.created_at)}


def list_agreements(db: DbSession, business_id: str) -> list[dict]:
    agreements = db.scalars(select(Agreement).where(Agreement.business_id == business_id)
                            .order_by(Agreement.created_at.desc())).all()
    return [summary(db, agreement) for agreement in agreements]


def detail(db: DbSession, business_id: str, agreement_id: str) -> dict:
    agreement = require_agreement(db, business_id, agreement_id)
    versions = db.scalars(select(AgreementVersion).where(AgreementVersion.agreement_id == agreement.id)
                          .order_by(AgreementVersion.version.desc())).all()
    if any(content_digest(version.content) != version.content_sha256 for version in versions):
        raise HTTPException(409, "Agreement version integrity check failed")
    events = db.scalars(select(ConfirmationEvent).where(ConfirmationEvent.agreement_id == agreement.id)
                        .order_by(ConfirmationEvent.created_at)).all()
    audits = db.scalars(select(AuditEvent).where(AuditEvent.agreement_id == agreement.id)
                        .order_by(AuditEvent.created_at)).all()
    return {**summary(db, agreement), "versions": [version_data(version) for version in versions],
            "events": [{"action": event.action, "version_id": event.agreement_version_id,
                        "verification_method": event.verification_method, "note": event.note,
                        "created_at": utc_iso(event.created_at)} for event in events],
            "audit": [{"action": event.action, "detail": event.detail,
                       "created_at": utc_iso(event.created_at)} for event in audits]}


def render_credit_sale(business: Business, transaction: Transaction, customer: Counterparty) -> str:
    balance = transaction.total_ugx - transaction.paid_ugx
    return ("CREDIT SALE AGREEMENT — DRAFT\n\n"
            f"Business: {business.name}\n"
            f"Customer: {customer.display_name}\n"
            f"Transaction date: {transaction.transaction_date.isoformat()}\n"
            f"Goods or services supplied: {transaction.description}\n"
            f"Total value: UGX {transaction.total_ugx:,}\n"
            f"Amount reported as paid: UGX {transaction.paid_ugx:,}\n"
            f"Outstanding balance: UGX {balance:,}\n"
            f"Payment deadline: {transaction.due_date.isoformat()}\n"
            f"Delivery information: {transaction.delivery_notes or 'Not recorded'}\n\n"
            "Proposed terms\n"
            "1. The business records the goods or services above as supplied under this transaction.\n"
            f"2. The customer agrees to pay the outstanding UGX {balance:,} by {transaction.due_date.isoformat()}.\n"
            "3. Any correction or change to these terms should be documented as a new agreement version.\n\n"
            "The amount marked paid is a business report and has not been independently verified by MyBizVault.")


def create_draft(db: DbSession, business_id: str, transaction_id: str, user_id: str) -> dict:
    transaction = db.scalar(select(Transaction).where(Transaction.id == transaction_id,
                                                      Transaction.business_id == business_id))
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    if transaction.paid_ugx >= transaction.total_ugx or transaction.due_date is None:
        raise HTTPException(422, "Phase 3 supports credit transactions with a balance and deadline")
    if db.scalar(select(Agreement.id).where(Agreement.transaction_id == transaction_id)):
        raise HTTPException(409, "This transaction already has an agreement")
    business = db.get(Business, business_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    if customer is None or customer.business_id != business_id:
        raise HTTPException(409, "Transaction customer is unavailable")
    content = render_credit_sale(business, transaction, customer)
    agreement = Agreement(business_id=business_id, transaction_id=transaction_id,
                          status="draft", current_version=1)
    try:
        db.add(agreement)
        db.flush()
        version = AgreementVersion(agreement_id=agreement.id, version=1, content=content,
                                   content_sha256=content_digest(content), created_by_user_id=user_id)
        db.add(version)
        db.flush()
        audit(db, agreement, "draft_created", version.id, user_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This transaction already has an agreement") from None
    return detail(db, business_id, agreement.id)


def revise_draft(db: DbSession, business_id: str, agreement_id: str, user_id: str, content: str) -> dict:
    agreement = require_agreement(db, business_id, agreement_id)
    if agreement.status == "confirmed":
        raise HTTPException(409, "Confirmed terms cannot be edited; create an amendment in a later phase")
    old_version = current_version(db, agreement)
    if content_digest(content) == old_version.content_sha256:
        raise HTTPException(409, "The proposed terms have not changed")
    marker = "\n\nProposed terms\n"
    if marker not in old_version.content or not content.startswith(old_version.content.split(marker, 1)[0] + marker):
        raise HTTPException(422, "Core transaction facts are linked to the saved transaction and cannot be changed here")
    now = utcnow()
    for invitation in db.scalars(select(AgreementInvitation).where(
            AgreementInvitation.agreement_id == agreement.id,
            AgreementInvitation.revoked_at.is_(None),
            AgreementInvitation.completed_at.is_(None))).all():
        invitation.revoked_at = now
    version = AgreementVersion(agreement_id=agreement.id, version=agreement.current_version + 1,
                               content=content, content_sha256=content_digest(content),
                               created_by_user_id=user_id)
    db.add(version)
    db.flush()
    agreement.current_version = version.version
    agreement.status = "draft"
    audit(db, agreement, "draft_revised", version.id, user_id, f"Replaces version {old_version.version}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Agreement changed while you were editing; refresh and try again") from None
    return detail(db, business_id, agreement.id)


def create_invitation(db: DbSession, business_id: str, agreement_id: str, user_id: str) -> dict:
    agreement = require_agreement(db, business_id, agreement_id)
    if agreement.status not in {"draft", "invited"}:
        raise HTTPException(409, "Revise the draft before creating a new invitation")
    version = current_version(db, agreement)
    transaction = db.get(Transaction, agreement.transaction_id)
    now = utcnow()
    for old in db.scalars(select(AgreementInvitation).where(
            AgreementInvitation.agreement_id == agreement.id,
            AgreementInvitation.revoked_at.is_(None),
            AgreementInvitation.completed_at.is_(None))).all():
        old.revoked_at = now
    token = secrets.token_urlsafe(32)
    invitation = AgreementInvitation(agreement_id=agreement.id, agreement_version_id=version.id,
                                     counterparty_id=transaction.counterparty_id, token_hash=digest(token),
                                     expires_at=now + timedelta(days=7))
    db.add(invitation)
    agreement.status = "invited"
    audit(db, agreement, "review_link_created", version.id, user_id,
          "Invitation created; delivery is a separate explicit action")
    db.commit()
    return {"review_url": f"{settings.frontend_origin.rstrip('/')}/review/invite#token={token}",
            "expires_at": utc_iso(invitation.expires_at), "version_id": version.id,
            "delivery": "manual", "identity_verified": False}


def send_invitation(db: DbSession, business_id: str, agreement_id: str,
                    user_id: str, channel: str) -> dict:
    agreement = require_agreement(db, business_id, agreement_id)
    transaction = db.get(Transaction, agreement.transaction_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    business = db.get(Business, business_id)
    recipient = customer.email if channel == "email" else customer.phone
    check_delivery(channel, recipient)
    result = create_invitation(db, business_id, agreement_id, user_id)
    try:
        send_message(channel, recipient, f"Review an agreement from {business.name}",
            f"{business.name} invites you to review an agreement. Open this private link:\n{result['review_url']}\n\nThe link expires in seven days. Do not forward it.")
    except HTTPException as failure:
        audit(db, agreement, "invitation_delivery_failed", result["version_id"], user_id,
              f"{channel} delivery failed")
        db.commit()
        return {**result, "delivery": "failed", "delivery_error": failure.detail}
    audit(db, agreement, "invitation_sent", result["version_id"], user_id, f"Channel: {channel}")
    db.commit()
    return {**result, "delivery": channel}


def invitation_for_token(db: DbSession, token: str | None, allow_completed: bool = False) -> tuple[AgreementInvitation, Agreement, AgreementVersion]:
    if not token or len(token) > 256:
        raise HTTPException(404, "Invitation unavailable")
    invitation = db.scalar(select(AgreementInvitation).where(AgreementInvitation.token_hash == digest(token)))
    if invitation is None or invitation.revoked_at is not None or as_utc(invitation.expires_at) <= utcnow():
        raise HTTPException(404, "Invitation unavailable")
    agreement = db.get(Agreement, invitation.agreement_id)
    version = db.get(AgreementVersion, invitation.agreement_version_id)
    if agreement is None or version is None or agreement.current_version != version.version:
        raise HTTPException(404, "Invitation unavailable")
    if content_digest(version.content) != version.content_sha256:
        raise HTTPException(409, "Agreement version integrity check failed")
    if invitation.completed_at is not None:
        if not allow_completed or agreement.status != "confirmed":
            raise HTTPException(404, "Invitation unavailable")
    elif agreement.status != "invited":
        raise HTTPException(404, "Invitation unavailable")
    return invitation, agreement, version


def external_review(db: DbSession, token: str | None) -> dict:
    invitation, agreement, version = invitation_for_token(db, token, allow_completed=True)
    transaction = db.get(Transaction, agreement.transaction_id)
    customer = db.get(Counterparty, invitation.counterparty_id)
    business = db.get(Business, agreement.business_id)
    if transaction.counterparty_id != customer.id or customer.business_id != business.id:
        raise HTTPException(404, "Invitation unavailable")
    return {"agreement_id": agreement.id, "version_id": version.id, "version": version.version,
            "status": agreement.status, "content": version.content,
            "content_sha256": version.content_sha256, "business_name": business.name,
            "counterparty_name": customer.display_name, "transaction_id": transaction.id,
            "total_ugx": transaction.total_ugx, "paid_ugx": transaction.paid_ugx,
            "balance_ugx": transaction.total_ugx - transaction.paid_ugx,
            "due_date": transaction.due_date, "development_verification": settings.development_verification,
            "identity_verified": False, "expires_at": utc_iso(invitation.expires_at)}


def issue_challenge(db: DbSession, token: str | None) -> dict:
    if not settings.development_verification:
        raise HTTPException(503, "Independent verification delivery is not configured")
    invitation, agreement, version = invitation_for_token(db, token)
    now = utcnow()
    cutoff = now - timedelta(seconds=60)
    result = db.execute(update(AgreementInvitation).where(
        AgreementInvitation.id == invitation.id,
        AgreementInvitation.revoked_at.is_(None),
        AgreementInvitation.completed_at.is_(None),
        (AgreementInvitation.last_challenge_at.is_(None) | (AgreementInvitation.last_challenge_at < cutoff))
    ).values(last_challenge_at=now).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(429, "Wait before requesting another code")
    for old in db.scalars(select(ConfirmationChallenge).where(
            ConfirmationChallenge.invitation_id == invitation.id,
            ConfirmationChallenge.consumed_at.is_(None))).all():
        old.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = ConfirmationChallenge(invitation_id=invitation.id,
                                      code_hash=hash_password(code), attempts=0,
                                      expires_at=now + timedelta(minutes=5))
    db.add(challenge)
    audit(db, agreement, "development_code_issued", version.id,
          detail="Code displayed to link holder; identity not verified")
    db.commit()
    return {"development_code": code, "expires_at": utc_iso(challenge.expires_at),
            "warning": "Development-only code displayed to the link holder. This does not verify identity."}


def accept(db: DbSession, token: str | None, version_id: str, code: str, explicitly_accepted: bool) -> dict:
    if not settings.development_verification:
        raise HTTPException(503, "Independent verification delivery is not configured")
    invitation, agreement, version = invitation_for_token(db, token)
    if not explicitly_accepted or version.id != version_id:
        raise HTTPException(409, "Displayed agreement version must be explicitly accepted")
    challenge = db.scalar(select(ConfirmationChallenge).where(
        ConfirmationChallenge.invitation_id == invitation.id).order_by(ConfirmationChallenge.created_at.desc()))
    if challenge is None or challenge.consumed_at is not None or as_utc(challenge.expires_at) <= utcnow() or challenge.attempts >= 5:
        raise HTTPException(429, "Verification code unavailable or expired")
    if not verify_password(code, challenge.code_hash):
        db.execute(update(ConfirmationChallenge).where(
            ConfirmationChallenge.id == challenge.id,
            ConfirmationChallenge.consumed_at.is_(None),
            ConfirmationChallenge.attempts < 5).values(attempts=ConfirmationChallenge.attempts + 1))
        db.commit()
        raise HTTPException(400, "Verification code is incorrect")
    now = utcnow()
    consumed = db.execute(update(ConfirmationChallenge).where(
        ConfirmationChallenge.id == challenge.id,
        ConfirmationChallenge.consumed_at.is_(None),
        ConfirmationChallenge.attempts < 5,
        ConfirmationChallenge.expires_at > now).values(consumed_at=now).execution_options(synchronize_session=False))
    changed = db.execute(update(Agreement).where(
        Agreement.id == agreement.id, Agreement.status == "invited",
        Agreement.current_version == version.version).values(status="confirmed"))
    if consumed.rowcount != 1 or changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Agreement is no longer available for confirmation")
    invitation.completed_at = now
    db.add(ConfirmationEvent(agreement_id=agreement.id, agreement_version_id=version.id,
                             invitation_id=invitation.id, action="accepted",
                             verification_method="development_code", note=None))
    audit(db, agreement, "accepted_with_development_code", version.id,
          detail="No independent identity proof")
    key = None
    provider = None
    try:
        _document, key, provider = vault.stage_confirmed_agreement(db, agreement, version)
        db.commit()
    except IntegrityError:
        db.rollback()
        if provider:
            vault.cleanup(provider, key)
        raise HTTPException(409, "Confirmation changed concurrently; refresh and try again") from None
    except Exception:
        db.rollback()
        if provider:
            vault.cleanup(provider, key)
        raise
    return {"status": "confirmed", "version_id": version.id,
            "content_sha256": version.content_sha256, "identity_verified": False}


def respond(db: DbSession, token: str | None, version_id: str, action: str, note: str | None) -> dict:
    invitation, agreement, version = invitation_for_token(db, token)
    if version.id != version_id or action not in {"rejected", "correction_requested"}:
        raise HTTPException(409, "Response does not match the displayed agreement version")
    note = note.strip() if note else None
    if action == "correction_requested" and not note:
        raise HTTPException(422, "Describe the correction requested")
    now = utcnow()
    changed = db.execute(update(Agreement).where(
        Agreement.id == agreement.id, Agreement.status == "invited",
        Agreement.current_version == version.version).values(status=action))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Agreement is no longer available for response")
    invitation.revoked_at = now
    db.add(ConfirmationEvent(agreement_id=agreement.id, agreement_version_id=version.id,
                             invitation_id=invitation.id, action=action,
                             verification_method="invitation_link_only", note=note))
    audit(db, agreement, action, version.id, detail="Response from invitation link; identity not verified")
    db.commit()
    return {"status": action, "version_id": version.id, "identity_verified": False}
