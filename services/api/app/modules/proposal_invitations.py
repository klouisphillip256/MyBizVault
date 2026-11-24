"""Token-bound counterparty review of one immutable proposal."""

import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.delivery import check_delivery, send_message
from app.core.security import as_utc, digest, hash_password, utc_iso, verify_password
from app.db.models import (Business, Counterparty, NegotiationRecord,
                           ProposalChallenge, ProposalInvitation, ProposalResponse, Transaction, utcnow)


def create_invitation(db: DbSession, business_id: str, transaction_id: str, proposal_id: str) -> dict:
    proposal = db.scalar(select(NegotiationRecord).where(NegotiationRecord.id == proposal_id,
        NegotiationRecord.business_id == business_id, NegotiationRecord.transaction_id == transaction_id))
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "open":
        raise HTTPException(409, "Only an open proposal can be shared")
    transaction = db.get(Transaction, transaction_id)
    now = utcnow()
    for previous in db.scalars(select(ProposalInvitation).where(
        ProposalInvitation.negotiation_id == proposal.id,
        ProposalInvitation.revoked_at.is_(None), ProposalInvitation.completed_at.is_(None))).all():
        previous.revoked_at = now
    token = secrets.token_urlsafe(32)
    invitation = ProposalInvitation(negotiation_id=proposal.id,
        counterparty_id=transaction.counterparty_id, token_hash=digest(token),
        expires_at=now + timedelta(days=7))
    db.add(invitation)
    db.commit()
    return {"review_url": f"{settings.frontend_origin.rstrip('/')}/review/proposal#token={token}",
            "expires_at": utc_iso(invitation.expires_at), "proposal_id": proposal.id,
            "delivery": "manual", "identity_verified": False}


def send_invitation(db: DbSession, business_id: str, transaction_id: str,
                    proposal_id: str, channel: str) -> dict:
    proposal = db.scalar(select(NegotiationRecord).where(NegotiationRecord.id == proposal_id,
        NegotiationRecord.business_id == business_id, NegotiationRecord.transaction_id == transaction_id))
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    transaction = db.get(Transaction, transaction_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    business = db.get(Business, business_id)
    recipient = customer.email if channel == "email" else customer.phone
    check_delivery(channel, recipient)
    result = create_invitation(db, business_id, transaction_id, proposal_id)
    try:
        send_message(channel, recipient, f"Review a proposal from {business.name}",
            f"{business.name} invites you to review a proposed change. Open this private link:\n{result['review_url']}\n\nThe link expires in seven days. Do not forward it.")
    except HTTPException as failure:
        return {**result, "delivery": "failed", "delivery_error": failure.detail}
    return {**result, "delivery": channel}


def invitation_for_token(db: DbSession, token: str | None,
                         allow_completed: bool = False) -> tuple[ProposalInvitation, NegotiationRecord, Transaction]:
    if not token or len(token) > 256:
        raise HTTPException(404, "Invitation unavailable")
    invitation = db.scalar(select(ProposalInvitation).where(ProposalInvitation.token_hash == digest(token)))
    if invitation is None or invitation.revoked_at is not None or as_utc(invitation.expires_at) <= utcnow():
        raise HTTPException(404, "Invitation unavailable")
    proposal = db.get(NegotiationRecord, invitation.negotiation_id)
    if proposal is None or (proposal.status != "open" and not (allow_completed and invitation.completed_at is not None)):
        raise HTTPException(404, "Invitation unavailable")
    if invitation.completed_at is not None and not allow_completed:
        raise HTTPException(404, "Invitation unavailable")
    transaction = db.get(Transaction, proposal.transaction_id)
    if transaction is None or transaction.business_id != proposal.business_id or transaction.counterparty_id != invitation.counterparty_id:
        raise HTTPException(404, "Invitation unavailable")
    return invitation, proposal, transaction


def review(db: DbSession, token: str | None) -> dict:
    invitation, proposal, transaction = invitation_for_token(db, token, allow_completed=True)
    business = db.get(Business, proposal.business_id)
    customer = db.get(Counterparty, invitation.counterparty_id)
    return {"proposal_id": proposal.id, "kind": proposal.kind, "proposal": proposal.proposal,
            "proposed_due_date": proposal.proposed_due_date,
            "proposed_amount_ugx": proposal.proposed_amount_ugx, "status": proposal.status,
            "business_name": business.name, "counterparty_name": customer.display_name,
            "transaction_description": transaction.description,
            "original_due_date": transaction.due_date, "total_ugx": transaction.total_ugx,
            "initial_paid_ugx": transaction.paid_ugx,
            "development_verification": settings.development_verification,
            "identity_verified": False, "expires_at": utc_iso(invitation.expires_at)}


def issue_challenge(db: DbSession, token: str | None) -> dict:
    if not settings.development_verification:
        raise HTTPException(503, "Independent verification delivery is not configured")
    invitation, _, _ = invitation_for_token(db, token)
    now = utcnow()
    changed = db.execute(update(ProposalInvitation).where(
        ProposalInvitation.id == invitation.id,
        ProposalInvitation.revoked_at.is_(None), ProposalInvitation.completed_at.is_(None),
        (ProposalInvitation.last_challenge_at.is_(None) |
         (ProposalInvitation.last_challenge_at < now - timedelta(seconds=60)))
    ).values(last_challenge_at=now).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(429, "Wait before requesting another code")
    for previous in db.scalars(select(ProposalChallenge).where(
        ProposalChallenge.invitation_id == invitation.id,
        ProposalChallenge.consumed_at.is_(None))).all():
        previous.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(ProposalChallenge(invitation_id=invitation.id, code_hash=hash_password(code),
                             attempts=0, expires_at=now + timedelta(minutes=5)))
    db.commit()
    return {"development_code": code, "expires_at": utc_iso(now + timedelta(minutes=5)),
            "warning": "Development-only code shown to link holder. Identity is not verified."}


def respond(db: DbSession, token: str | None, proposal_id: str, action: str,
            note: str | None, code: str | None, explicitly_accepted: bool) -> dict:
    invitation, proposal, _ = invitation_for_token(db, token)
    if proposal.id != proposal_id or action not in {"accepted", "declined", "correction_requested"}:
        raise HTTPException(409, "Response does not match the displayed proposal")
    if action == "accepted" and proposal.kind == "payment_dispute":
        raise HTTPException(422, "A payment dispute needs a resolution proposal")
    note = note.strip() if note else None
    if action == "correction_requested" and not note:
        raise HTTPException(422, "Describe the correction requested")
    method = "invitation_link_only"
    now = utcnow()
    if action == "accepted":
        if not settings.development_verification:
            raise HTTPException(503, "Independent verification delivery is not configured")
        if not explicitly_accepted or not code:
            raise HTTPException(422, "Explicit acceptance and code are required")
        challenge = db.scalar(select(ProposalChallenge).where(
            ProposalChallenge.invitation_id == invitation.id).order_by(ProposalChallenge.created_at.desc()))
        if challenge is None or challenge.consumed_at is not None or as_utc(challenge.expires_at) <= now or challenge.attempts >= 5:
            raise HTTPException(429, "Verification code unavailable or expired")
        if not verify_password(code, challenge.code_hash):
            db.execute(update(ProposalChallenge).where(ProposalChallenge.id == challenge.id,
                ProposalChallenge.consumed_at.is_(None), ProposalChallenge.attempts < 5)
                .values(attempts=ProposalChallenge.attempts + 1))
            db.commit()
            raise HTTPException(400, "Verification code is incorrect")
        consumed = db.execute(update(ProposalChallenge).where(ProposalChallenge.id == challenge.id,
            ProposalChallenge.consumed_at.is_(None), ProposalChallenge.attempts < 5,
            ProposalChallenge.expires_at > now).values(consumed_at=now).execution_options(synchronize_session=False))
        if consumed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Code already used")
        method = "development_code"
    changed = db.execute(update(NegotiationRecord).where(NegotiationRecord.id == proposal.id,
        NegotiationRecord.status == "open").values(status=action, response_source=method).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Proposal is no longer available")
    invitation.completed_at = now
    db.add(ProposalResponse(negotiation_id=proposal.id, invitation_id=invitation.id,
        action=action, note=note, verification_method=method))
    db.commit()
    return {"status": action, "proposal_id": proposal.id, "identity_verified": False,
            "verification_method": method}
