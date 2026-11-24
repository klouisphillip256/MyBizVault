import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.security import hash_password, utc_iso
from app.db.models import Agreement, Business, Counterparty, Membership, Transaction, User
from app.modules.schemas import CounterpartyIn, StaffCreateIn, StaffUpdateIn, TransactionIn


def customer_data(customer: Counterparty, include_contact: bool = True) -> dict:
    return {"id": customer.id, "display_name": customer.display_name,
            "phone": customer.phone if include_contact else None,
            "email": customer.email if include_contact else None,
            "notes": customer.notes if include_contact else None, "created_at": utc_iso(customer.created_at)}


def transaction_data(db: DbSession, transaction: Transaction, customer: Counterparty) -> dict:
    from app.modules.obligations import transaction_totals
    totals = transaction_totals(db, transaction)
    lines = json.loads(transaction.line_items_json) if transaction.line_items_json else [
        {"description": transaction.description, "quantity": 1,
         "unit_price_ugx": transaction.total_ugx}]
    return {"id": transaction.id, "counterparty_id": transaction.counterparty_id,
            "counterparty_name": customer.display_name, "description": transaction.description,
            "line_items": lines,
            "transaction_date": transaction.transaction_date, "total_ugx": transaction.total_ugx,
            "paid_ugx": transaction.paid_ugx, **totals,
            "due_date": transaction.due_date, "delivery_notes": transaction.delivery_notes,
            "created_at": utc_iso(transaction.created_at), "payment_record_status": "reported"}


def list_customers(db: DbSession, business_id: str, include_contact: bool) -> list[dict]:
    customers = db.scalars(select(Counterparty).where(Counterparty.business_id == business_id)
                           .order_by(Counterparty.display_name)).all()
    return [customer_data(customer, include_contact) for customer in customers]


def create_customer(db: DbSession, business_id: str, payload: CounterpartyIn) -> dict:
    customer = Counterparty(business_id=business_id, display_name=payload.display_name.strip(),
                            phone=payload.phone.strip() if payload.phone else None,
                            email=str(payload.email).lower() if payload.email else None,
                            notes=payload.notes.strip() if payload.notes else None)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_data(customer)


def update_customer(db: DbSession, business_id: str, customer_id: str, payload: CounterpartyIn) -> dict:
    customer = db.scalar(select(Counterparty).where(Counterparty.id == customer_id,
                                                    Counterparty.business_id == business_id))
    if customer is None:
        raise HTTPException(404, "Customer not found")
    customer.display_name = payload.display_name
    customer.phone = payload.phone or None
    customer.email = str(payload.email).lower() if payload.email else None
    customer.notes = payload.notes or None
    db.commit()
    return customer_data(customer)


def list_transactions(db: DbSession, business_id: str) -> list[dict]:
    rows = db.execute(select(Transaction, Counterparty)
                      .join(Counterparty, Transaction.counterparty_id == Counterparty.id)
                      .where(Transaction.business_id == business_id, Counterparty.business_id == business_id)
                      .order_by(Transaction.created_at.desc())).all()
    return [transaction_data(db, transaction, customer) for transaction, customer in rows]


def get_transaction(db: DbSession, business_id: str, transaction_id: str) -> dict:
    row = db.execute(select(Transaction, Counterparty)
                     .join(Counterparty, Transaction.counterparty_id == Counterparty.id)
                     .where(Transaction.business_id == business_id, Transaction.id == transaction_id,
                            Counterparty.business_id == business_id)).first()
    if not row:
        raise HTTPException(404, "Transaction not found")
    transaction, customer = row
    from app.modules import communications, obligations, receipts
    receipts.ensure_for_transaction(db, transaction)
    agreement = db.scalar(select(Agreement).where(Agreement.business_id == business_id,
        Agreement.transaction_id == transaction_id))
    return {**transaction_data(db, transaction, customer),
        "customer_phone": customer.phone, "customer_email": customer.email,
        "receipts": receipts.list_for_transaction(db, business_id, transaction_id),
        "payments": obligations.list_payments(db, business_id, transaction_id),
        "approval_history": obligations.list_history(db, business_id, transaction_id),
        "communications": communications.list_for_transaction(db, business_id, transaction_id),
        "agreement": {"id": agreement.id, "status": agreement.status,
            "current_version": agreement.current_version} if agreement else None}


def create_transaction(db: DbSession, business_id: str, user_id: str, payload: TransactionIn) -> dict:
    lines_json = (json.dumps([line.model_dump() for line in payload.line_items],
                sort_keys=True, separators=(",", ":")) if payload.line_items else None)
    def existing_request() -> Transaction | None:
        if not payload.client_request_id:
            return None
        return db.scalar(select(Transaction).where(Transaction.business_id == business_id,
            Transaction.client_request_id == str(payload.client_request_id)))

    def checked_previous(previous: Transaction) -> dict:
        if (previous.counterparty_id != payload.counterparty_id or
            previous.description != payload.description.strip() or
            previous.line_items_json != lines_json or
            previous.transaction_date != payload.transaction_date or
            previous.total_ugx != payload.total_ugx or previous.paid_ugx != payload.paid_ugx or
            previous.due_date != payload.due_date or
            (previous.delivery_notes or "") != (payload.delivery_notes or "").strip()):
            raise HTTPException(409, "Request ID was already used for a different transaction")
        customer = db.get(Counterparty, previous.counterparty_id)
        return transaction_data(db, previous, customer)

    previous = existing_request()
    if previous:
        return checked_previous(previous)
    customer = db.scalar(select(Counterparty).where(Counterparty.id == payload.counterparty_id,
                                                    Counterparty.business_id == business_id))
    if customer is None:
        raise HTTPException(404, "Customer not found")
    transaction = Transaction(business_id=business_id, counterparty_id=customer.id,
                              created_by_user_id=user_id, client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
                              description=payload.description.strip(),
                              line_items_json=lines_json,
                              transaction_date=payload.transaction_date, total_ugx=payload.total_ugx,
                              paid_ugx=payload.paid_ugx, due_date=payload.due_date,
                              delivery_notes=payload.delivery_notes.strip() if payload.delivery_notes else None)
    db.add(transaction)
    try:
        db.flush()
        from app.modules import receipts
        receipts.create_initial(db, transaction)
        if transaction.paid_ugx < transaction.total_ugx:
            from app.modules import agreements
            agreements.stage_draft(db, transaction, db.get(Business, business_id), customer, user_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = existing_request()
        if previous:
            return checked_previous(previous)
        raise
    db.refresh(transaction)
    return transaction_data(db, transaction, customer)


def staff_data(db: DbSession, membership: Membership) -> dict:
    user = db.get(User, membership.user_id)
    return {"id": membership.id, "full_name": user.full_name, "email": user.email,
            "can_view_transactions": membership.can_view_transactions,
            "can_create_transactions": membership.can_create_transactions,
            "can_manage_customers": membership.can_manage_customers,
            "can_manage_agreements": membership.can_manage_agreements,
            "can_view_documents": membership.can_view_documents,
            "can_manage_documents": membership.can_manage_documents,
            "can_manage_obligations": membership.can_manage_obligations,
            "is_active": membership.is_active}


def list_staff(db: DbSession, business_id: str) -> list[dict]:
    memberships = db.scalars(select(Membership).where(Membership.business_id == business_id,
                                                      Membership.role == "staff")).all()
    return [staff_data(db, membership) for membership in memberships]


def create_staff(db: DbSession, business_id: str, payload: StaffCreateIn) -> dict:
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(409, "This email already has an account")
    user = User(email=payload.email.lower(), full_name=payload.full_name.strip(),
                password_hash=hash_password(payload.password), failed_logins=0)
    try:
        db.add(user)
        db.flush()
        membership = Membership(business_id=business_id, user_id=user.id, role="staff",
                                can_view_transactions=payload.can_view_transactions or payload.can_create_transactions or payload.can_manage_agreements or payload.can_manage_obligations,
                                can_create_transactions=payload.can_create_transactions,
                                can_manage_customers=payload.can_manage_customers,
                                can_manage_agreements=payload.can_manage_agreements,
                                can_view_documents=payload.can_view_documents or payload.can_manage_documents,
                                can_manage_documents=payload.can_manage_documents,
                                can_manage_obligations=payload.can_manage_obligations, is_active=True)
        db.add(membership)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This email already has an account") from None
    return staff_data(db, membership)


def update_staff(db: DbSession, business_id: str, staff_id: str, payload: StaffUpdateIn) -> dict:
    membership = db.scalar(select(Membership).where(Membership.id == staff_id,
                                                    Membership.business_id == business_id,
                                                    Membership.role == "staff"))
    if membership is None:
        raise HTTPException(404, "Staff member not found")
    membership.can_view_transactions = payload.can_view_transactions or payload.can_create_transactions or payload.can_manage_agreements or payload.can_manage_obligations
    membership.can_create_transactions = payload.can_create_transactions
    membership.can_manage_customers = payload.can_manage_customers
    membership.can_manage_agreements = payload.can_manage_agreements
    membership.can_view_documents = payload.can_view_documents or payload.can_manage_documents
    membership.can_manage_documents = payload.can_manage_documents
    membership.can_manage_obligations = payload.can_manage_obligations
    membership.is_active = payload.is_active
    db.commit()
    return staff_data(db, membership)


def update_business(db: DbSession, business_id: str, payload) -> dict:
    business = db.get(Business, business_id)
    business.name = payload.name.strip()
    if "phone" in payload.model_fields_set:
        business.phone = payload.phone.strip() if payload.phone else None
    if "email" in payload.model_fields_set:
        business.email = str(payload.email).lower() if payload.email else None
    db.commit()
    return {"id": business.id, "name": business.name,
            "phone": business.phone, "email": business.email}
