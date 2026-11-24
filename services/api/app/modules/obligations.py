"""Business-recorded obligation history; confirmed agreement terms remain immutable."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.security import utc_iso
from app.db.models import Document, NegotiationRecord, ObligationEvent, PaymentRecord, ProposalResponse, Transaction
from app.modules.schemas import NegotiationIn, NegotiationResponseIn, PaymentRecordIn, PaymentStatusIn


def require_transaction(db: DbSession, business_id: str, transaction_id: str, lock: bool = False) -> Transaction:
    statement = select(Transaction).where(Transaction.business_id == business_id,
                                          Transaction.id == transaction_id)
    transaction = db.scalar(statement.with_for_update() if lock else statement)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    return transaction


def check_evidence(db: DbSession, business_id: str, document_id: str | None) -> None:
    if document_id and db.scalar(select(Document.id).where(Document.id == document_id,
                                                           Document.business_id == business_id)) is None:
        raise HTTPException(404, "Evidence document not found")


def event(db: DbSession, transaction: Transaction, user_id: str, action: str,
          note: str | None = None, payment_id: str | None = None,
          negotiation_id: str | None = None) -> None:
    db.add(ObligationEvent(business_id=transaction.business_id, transaction_id=transaction.id,
                           payment_id=payment_id, negotiation_id=negotiation_id,
                           actor_user_id=user_id, action=action, note=note))


def payment_data(record: PaymentRecord) -> dict:
    return {"id": record.id, "transaction_id": record.transaction_id,
            "amount_ugx": record.amount_ugx, "paid_on": record.paid_on,
            "reference": record.reference, "note": record.note,
            "evidence_document_id": record.evidence_document_id,
            "status": record.status, "verification_source": "business_recorded",
            "created_at": utc_iso(record.created_at)}


def negotiation_data(record: NegotiationRecord) -> dict:
    return {"id": record.id, "transaction_id": record.transaction_id,
            "kind": record.kind, "proposal": record.proposal,
            "proposed_due_date": record.proposed_due_date,
            "proposed_amount_ugx": record.proposed_amount_ugx,
            "evidence_document_id": record.evidence_document_id,
            "status": record.status, "verification_source": record.response_source or "business_recorded",
            "created_at": utc_iso(record.created_at)}


def transaction_totals(db: DbSession, transaction: Transaction) -> dict:
    payments = db.scalars(select(PaymentRecord).where(PaymentRecord.transaction_id == transaction.id,
                                                       PaymentRecord.business_id == transaction.business_id)).all()
    additional_paid = sum(row.amount_ugx for row in payments if row.status != "disputed")
    disputed = sum(row.amount_ugx for row in payments if row.status == "disputed")
    accepted = db.scalars(select(NegotiationRecord).where(
        NegotiationRecord.transaction_id == transaction.id,
        NegotiationRecord.business_id == transaction.business_id,
        NegotiationRecord.kind.in_(["extension", "instalment_plan", "revised_obligation"]),
        NegotiationRecord.status == "accepted",
        NegotiationRecord.proposed_due_date.is_not(None))
        .order_by(NegotiationRecord.created_at.desc(), NegotiationRecord.id.desc())).first()
    effective_due = accepted.proposed_due_date if accepted else transaction.due_date
    balance = max(0, transaction.total_ugx - transaction.paid_ugx - additional_paid)
    return {"additional_paid_ugx": additional_paid, "disputed_ugx": disputed,
            "balance_ugx": balance, "effective_due_date": effective_due,
            "due_date_source": "business_recorded_proposal" if accepted else "original_transaction",
            "is_overdue": bool(balance and effective_due and effective_due < date.today())}


def list_payments(db: DbSession, business_id: str, transaction_id: str) -> list[dict]:
    require_transaction(db, business_id, transaction_id)
    return [payment_data(row) for row in db.scalars(select(PaymentRecord).where(
        PaymentRecord.business_id == business_id, PaymentRecord.transaction_id == transaction_id)
        .order_by(PaymentRecord.created_at.desc())).all()]


def create_payment(db: DbSession, business_id: str, transaction_id: str,
                   user_id: str, payload: PaymentRecordIn) -> dict:
    transaction = require_transaction(db, business_id, transaction_id, lock=True)
    check_evidence(db, business_id, payload.evidence_document_id)
    if payload.paid_on < transaction.transaction_date or payload.paid_on > date.today():
        raise HTTPException(422, "Payment date must be between the transaction date and today")
    if payload.amount_ugx > transaction_totals(db, transaction)["balance_ugx"]:
        raise HTTPException(409, "Reported payment exceeds the outstanding balance")
    record = PaymentRecord(business_id=business_id, transaction_id=transaction_id,
                           amount_ugx=payload.amount_ugx, paid_on=payload.paid_on,
                           reference=payload.reference.strip() if payload.reference else None,
                           note=payload.note.strip() if payload.note else None,
                           evidence_document_id=payload.evidence_document_id,
                           status="reported", created_by_user_id=user_id)
    db.add(record)
    db.flush()
    from app.modules import receipts
    receipts.create_for_payment(db, transaction, record)
    event(db, transaction, user_id, "payment_reported", record.note, payment_id=record.id)
    db.commit()
    return payment_data(record)


def update_payment_status(db: DbSession, business_id: str, transaction_id: str,
                          payment_id: str, user_id: str, payload: PaymentStatusIn) -> dict:
    transaction = require_transaction(db, business_id, transaction_id, lock=True)
    record = db.scalar(select(PaymentRecord).where(PaymentRecord.id == payment_id,
        PaymentRecord.business_id == business_id, PaymentRecord.transaction_id == transaction_id).with_for_update())
    if record is None:
        raise HTTPException(404, "Payment record not found")
    if record.status == payload.action:
        raise HTTPException(409, "Payment already has this status")
    if payload.action == "acknowledged" and record.status == "disputed" and record.amount_ugx > transaction_totals(db, transaction)["balance_ugx"]:
        raise HTTPException(409, "Acknowledgment would exceed the outstanding balance")
    record.status = payload.action
    event(db, transaction, user_id, f"payment_{payload.action}", payload.note.strip(), payment_id=record.id)
    db.commit()
    return payment_data(record)


def list_negotiations(db: DbSession, business_id: str, transaction_id: str) -> list[dict]:
    require_transaction(db, business_id, transaction_id)
    return [negotiation_data(row) for row in db.scalars(select(NegotiationRecord).where(
        NegotiationRecord.business_id == business_id, NegotiationRecord.transaction_id == transaction_id)
        .order_by(NegotiationRecord.created_at.desc())).all()]


def create_negotiation(db: DbSession, business_id: str, transaction_id: str,
                       user_id: str, payload: NegotiationIn) -> dict:
    transaction = require_transaction(db, business_id, transaction_id)
    check_evidence(db, business_id, payload.evidence_document_id)
    if payload.kind in {"extension", "instalment_plan"} and not payload.proposed_due_date:
        raise HTTPException(422, "A proposed final payment date is required")
    if payload.kind == "extension" and transaction.due_date and payload.proposed_due_date <= transaction.due_date:
        raise HTTPException(422, "An extension must be later than the original deadline")
    if payload.kind == "settlement" and payload.proposed_amount_ugx is None:
        raise HTTPException(422, "A proposed settlement amount is required")
    record = NegotiationRecord(business_id=business_id, transaction_id=transaction_id,
        kind=payload.kind, proposal=payload.proposal.strip(),
        proposed_due_date=payload.proposed_due_date,
        proposed_amount_ugx=payload.proposed_amount_ugx,
        evidence_document_id=payload.evidence_document_id,
        status="open", created_by_user_id=user_id)
    db.add(record)
    db.flush()
    event(db, transaction, user_id, "proposal_opened", record.proposal, negotiation_id=record.id)
    db.commit()
    return negotiation_data(record)


def respond_negotiation(db: DbSession, business_id: str, transaction_id: str,
                        negotiation_id: str, user_id: str, payload: NegotiationResponseIn) -> dict:
    transaction = require_transaction(db, business_id, transaction_id, lock=True)
    record = db.scalar(select(NegotiationRecord).where(NegotiationRecord.id == negotiation_id,
        NegotiationRecord.business_id == business_id,
        NegotiationRecord.transaction_id == transaction_id).with_for_update())
    if record is None:
        raise HTTPException(404, "Proposal not found")
    if record.status != "open":
        raise HTTPException(409, "This proposal already has an outcome")
    if payload.action == "resolved" and record.kind != "payment_dispute":
        raise HTTPException(422, "Only a dispute can be resolved")
    if payload.action == "accepted" and record.kind == "payment_dispute":
        raise HTTPException(422, "Resolve a dispute with a recorded resolution")
    record.status = payload.action
    record.response_source = "business_recorded"
    event(db, transaction, user_id, f"proposal_{payload.action}", payload.note.strip(), negotiation_id=record.id)
    db.commit()
    return negotiation_data(record)


def list_history(db: DbSession, business_id: str, transaction_id: str) -> list[dict]:
    require_transaction(db, business_id, transaction_id)
    rows = db.scalars(select(ObligationEvent).where(ObligationEvent.business_id == business_id,
        ObligationEvent.transaction_id == transaction_id).order_by(ObligationEvent.created_at.desc())).all()
    history = [{"id": row.id, "payment_id": row.payment_id, "negotiation_id": row.negotiation_id,
             "action": row.action, "note": row.note, "created_at": utc_iso(row.created_at)} for row in rows]
    responses = db.execute(select(ProposalResponse, NegotiationRecord).join(
        NegotiationRecord, ProposalResponse.negotiation_id == NegotiationRecord.id).where(
        NegotiationRecord.business_id == business_id,
        NegotiationRecord.transaction_id == transaction_id)).all()
    history.extend({"id": response.id, "payment_id": None, "negotiation_id": proposal.id,
        "action": f"customer_link_{response.action}", "note": response.note,
        "created_at": utc_iso(response.created_at)} for response, proposal in responses)
    return sorted(history, key=lambda item: item["created_at"], reverse=True)
