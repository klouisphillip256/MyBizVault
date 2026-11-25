"""Versioned payment evidence, separate from agreement acceptance."""

import hashlib
import io
import json
from html import escape

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.security import utc_iso
from app.db.models import Business, Counterparty, Membership, PaymentRecord, Receipt, Transaction, User


def _snapshot(db: DbSession, transaction: Transaction, payment: PaymentRecord | None) -> dict:
    business = db.get(Business, transaction.business_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    owner = db.scalar(select(User).join(Membership, User.id == Membership.user_id).where(
        Membership.business_id == transaction.business_id, Membership.role == "owner"))
    return {
        "seller_name": business.name, "seller_email": business.email or (owner.email if owner else None),
        "seller_phone": business.phone, "buyer_name": customer.display_name,
        "buyer_email": customer.email, "buyer_phone": customer.phone,
        "transaction_id": transaction.id, "transaction_date": transaction.transaction_date.isoformat(),
        "item_description": transaction.description, "total_ugx": transaction.total_ugx,
        "line_items": json.loads(transaction.line_items_json) if transaction.line_items_json else [
            {"description": transaction.description, "quantity": 1, "unit_price_ugx": transaction.total_ugx}],
        "initial_paid_ugx": transaction.paid_ugx,
        "payment_amount_ugx": payment.amount_ugx if payment else transaction.paid_ugx,
        "payment_date": payment.paid_on.isoformat() if payment else transaction.transaction_date.isoformat(),
        "payment_reference": payment.reference if payment else None,
        "payment_status_at_issue": payment.status if payment else "business_reported",
        "payment_id": payment.id if payment else None,
        "original_due_date": transaction.due_date.isoformat() if transaction.due_date else None,
        "delivery_notes": transaction.delivery_notes,
        "recorded_at": utc_iso(payment.created_at if payment else transaction.created_at),
    }


def _make(db: DbSession, transaction: Transaction, payment: PaymentRecord | None) -> Receipt:
    snapshot = json.dumps(_snapshot(db, transaction, payment), sort_keys=True, separators=(",", ":"))
    receipt = Receipt(business_id=transaction.business_id, transaction_id=transaction.id,
        payment_id=payment.id if payment else None,
        kind="payment" if payment else "initial", snapshot_json=snapshot,
        snapshot_sha256=hashlib.sha256(snapshot.encode()).hexdigest())
    db.add(receipt)
    db.flush()
    return receipt


def create_initial(db: DbSession, transaction: Transaction) -> None:
    if transaction.paid_ugx > 0:
        _make(db, transaction, None)


def create_for_payment(db: DbSession, transaction: Transaction, payment: PaymentRecord) -> None:
    _make(db, transaction, payment)


def ensure_for_transaction(db: DbSession, transaction: Transaction) -> None:
    """Backfill old payments on first detail read; never alter existing receipt snapshots."""
    try:
        changed = False
        if transaction.paid_ugx > 0 and db.scalar(select(Receipt.id).where(
                Receipt.transaction_id == transaction.id, Receipt.kind == "initial")) is None:
            _make(db, transaction, None)
            changed = True
        payments = db.scalars(select(PaymentRecord).where(PaymentRecord.transaction_id == transaction.id,
            PaymentRecord.business_id == transaction.business_id).order_by(PaymentRecord.created_at)).all()
        for payment in payments:
            if db.scalar(select(Receipt.id).where(Receipt.payment_id == payment.id)) is None:
                _make(db, transaction, payment)
                changed = True
        if changed:
            db.commit()
    except IntegrityError:
        # Another request inserted the same historical receipt first.
        db.rollback()


def data(receipt: Receipt) -> dict:
    if hashlib.sha256(receipt.snapshot_json.encode()).hexdigest() != receipt.snapshot_sha256:
        raise HTTPException(409, "Receipt integrity check failed")
    snapshot = json.loads(receipt.snapshot_json)
    return {"id": receipt.id, "transaction_id": receipt.transaction_id, "payment_id": receipt.payment_id,
        "kind": receipt.kind, "amount_ugx": snapshot["payment_amount_ugx"],
        "payment_date": snapshot["payment_date"], "payment_status_at_issue": snapshot["payment_status_at_issue"],
        "created_at": utc_iso(receipt.created_at), "sha256": receipt.snapshot_sha256}


def list_for_transaction(db: DbSession, business_id: str, transaction_id: str) -> list[dict]:
    rows = db.scalars(select(Receipt).where(Receipt.business_id == business_id,
        Receipt.transaction_id == transaction_id).order_by(Receipt.created_at, Receipt.id)).all()
    return [data(row) for row in rows]


def require_receipt(db: DbSession, business_id: str, transaction_id: str, receipt_id: str) -> Receipt:
    receipt = db.scalar(select(Receipt).where(Receipt.id == receipt_id,
        Receipt.business_id == business_id, Receipt.transaction_id == transaction_id))
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    data(receipt)
    return receipt


def pdf(receipt: Receipt) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    snapshot = json.loads(receipt.snapshot_json)
    styles = getSampleStyleSheet()
    stream = io.BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, title="MyBizVault payment receipt")
    def p(value: object):
        return Paragraph(escape(str(value) if value is not None else "Not recorded"), styles["Normal"])
    rows = [
        ("Receipt ID", receipt.id), ("Transaction ID", snapshot["transaction_id"]),
        ("Seller", snapshot["seller_name"]), ("Seller phone", snapshot["seller_phone"]),
        ("Seller email", snapshot["seller_email"]), ("Buyer", snapshot["buyer_name"]),
        ("Buyer phone", snapshot["buyer_phone"]), ("Buyer email", snapshot["buyer_email"]),
        ("Goods or services", snapshot["item_description"]),
        ("Total transaction", f"UGX {snapshot['total_ugx']:,}"),
        ("Payment received (business record)", f"UGX {snapshot['payment_amount_ugx']:,}"),
        ("Payment date", snapshot["payment_date"]),
        ("Payment reference", snapshot["payment_reference"]),
        ("Payment status at issue", snapshot["payment_status_at_issue"]),
        ("Original due date", snapshot["original_due_date"]),
        ("Delivery notes", snapshot["delivery_notes"]),
    ]
    item_rows = [(f"Item {index}",
        f"{item['description']} · {item['quantity']} × UGX {item['unit_price_ugx']:,} = UGX {item['quantity'] * item['unit_price_ugx']:,}")
        for index, item in enumerate(snapshot.get("line_items") or [], 1)]
    rows[9:9] = item_rows
    table = Table([[p(label), p(value)] for label, value in rows], colWidths=[170, 330], hAlign="LEFT")
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story = [Paragraph("PAYMENT RECEIPT", styles["Title"]),
        p("This receipt records a payment entered by the business. It is not independent proof that funds cleared."),
        Spacer(1, 12), table, Spacer(1, 12),
        p("Commercial record for a transaction in Uganda. The Sale of Goods and Supply of Services Act 2018, Electronic Transactions Act 2011 and Electronic Signatures Act 2011 may be relevant according to the facts. This document makes no guarantee of enforceability."),
        p(f"Snapshot SHA-256: {receipt.snapshot_sha256}")]
    document.build(story)
    return stream.getvalue()


def agreement_pdf(content: str, agreement_id: str, version: int) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(stream, pagesize=A4,
        title=f"MyBizVault agreement {agreement_id} version {version}")
    story = [Paragraph("CREDIT SALE AGREEMENT", styles["Title"]),
        Paragraph(f"Agreement {escape(agreement_id)} · Version {version}", styles["Normal"]),
        Spacer(1, 12)]
    for line in content.splitlines():
        story.append(Paragraph(escape(line) or "&nbsp;", styles["Normal"]))
        story.append(Spacer(1, 5))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Electronic response and document history are recorded separately. This PDF does not by itself establish identity or legal enforceability.", styles["Italic"]))
    document.build(story)
    return stream.getvalue()


def contract_draft_pdf(title: str, business_name: str, counterparty_name: str,
                       purpose: str, payment_terms: str, obligations: str) -> bytes:
    """A reviewable draft that uses the existing private Vault storage flow."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(stream, pagesize=A4, title=title)
    story = [Paragraph("BUSINESS CONTRACT DRAFT", styles["Title"]),
        Paragraph(escape(title), styles["Heading2"]),
        Paragraph("Draft for review. No party has accepted or signed this document in MyBizVault.", styles["Italic"]),
        Spacer(1, 12)]
    for label, value in [("Business", business_name), ("Other party", counterparty_name),
                         ("Purpose and subject", purpose), ("Payment terms", payment_terms),
                         ("Obligations and delivery", obligations)]:
        story.extend([Paragraph(escape(label), styles["Heading3"]),
                      Paragraph(escape(value).replace("\n", "<br/>"), styles["Normal"]), Spacer(1, 8)])
    story.append(Paragraph("Before use, confirm dates, remedies, dispute terms and legal suitability with the other party or a qualified lawyer. This draft is not an accepted agreement.", styles["Italic"]))
    document.build(story)
    return stream.getvalue()
