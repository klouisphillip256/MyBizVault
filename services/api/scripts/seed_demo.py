"""Add an idempotent, fictional transaction walkthrough to one existing business.

Run with DATABASE_URL from a trusted secret manager:
    python scripts/seed_demo.py --business "Business name"
No invitation, email, SMS, or approval is sent or fabricated.
"""

import argparse
from datetime import date
from uuid import uuid5, NAMESPACE_URL

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, Counterparty, Membership, PaymentRecord, Transaction
from app.db.session import engine
from app.modules import obligations, records
from app.modules.schemas import CounterpartyIn, PaymentRecordIn, TransactionIn


CUSTOMERS = (
    ("Amina Sample", "amina.sample@example.com"),
    ("Daniel Example", "daniel.example@example.com"),
    ("Grace Test", "grace.test@example.com"),
)

SALES = (
    ("fully-paid", "Amina Sample", "Fictional office supply sale", 1250000, 1250000, None,
     (("Desk chairs", 5, 150000), ("Filing cabinets", 2, 250000))),
    ("unpaid", "Daniel Example", "Fictional wholesale stock order", 850000, 0, date(2026, 12, 15),
     (("Display shelves", 2, 275000), ("Storage bins", 10, 30000))),
    ("part-paid", "Grace Test", "Fictional equipment delivery", 2400000, 600000, date(2026, 12, 20),
     (("Equipment units", 3, 700000), ("Installation", 1, 300000))),
)


def seed(business_name: str) -> dict:
    with Session(engine) as db:
        businesses = db.scalars(select(Business).where(Business.name == business_name)).all()
        if len(businesses) != 1:
            raise ValueError("Business name must identify exactly one existing workspace")
        business = businesses[0]
        owner = db.scalar(select(Membership).where(
            Membership.business_id == business.id, Membership.role == "owner", Membership.is_active.is_(True)))
        if owner is None:
            raise ValueError("Selected business has no active owner")
        customer_ids = {}
        created_customers = created_sales = created_payments = 0
        for name, email in CUSTOMERS:
            customer = db.scalar(select(Counterparty).where(
                Counterparty.business_id == business.id, Counterparty.display_name == name,
                Counterparty.email == email))
            if customer is None:
                customer_data = records.create_customer(db, business.id, CounterpartyIn(
                    display_name=name, email=email,
                    notes="Fictional demonstration customer. Do not send communications."))
                customer_ids[name] = customer_data["id"]
                created_customers += 1
            else:
                customer_ids[name] = customer.id
        sale_ids = {}
        for key, customer_name, description, total, paid, deadline, items in SALES:
            request_id = uuid5(NAMESPACE_URL, f"mybizvault-demo-2026:{business.id}:{key}")
            transaction = db.scalar(select(Transaction).where(
                Transaction.business_id == business.id,
                Transaction.client_request_id == str(request_id)))
            if transaction is None:
                payload = TransactionIn(counterparty_id=customer_ids[customer_name],
                    client_request_id=request_id, description=description,
                    line_items=[{"description": title, "quantity": quantity, "unit_price_ugx": price}
                                for title, quantity, price in items],
                    transaction_date=date(2026, 11, 25), total_ugx=total,
                    paid_ugx=paid, due_date=deadline,
                    delivery_notes="Fictional demonstration transaction; no goods were delivered.")
                sale_ids[key] = records.create_transaction(db, business.id, owner.user_id, payload)["id"]
                created_sales += 1
            else:
                sale_ids[key] = transaction.id
        payment = db.scalar(select(PaymentRecord).where(
            PaymentRecord.business_id == business.id,
            PaymentRecord.transaction_id == sale_ids["part-paid"],
            PaymentRecord.reference == "DEMO-PAYMENT-001"))
        if payment is None:
            obligations.create_payment(db, business.id, sale_ids["part-paid"], owner.user_id,
                PaymentRecordIn(amount_ugx=300000, paid_on=date(2026, 11, 25),
                    reference="DEMO-PAYMENT-001", note="Fictional follow-up payment for demonstration."))
            created_payments = 1
        return {"business": business.name, "customers_created": created_customers,
                "transactions_created": created_sales, "payments_created": created_payments,
                "transaction_ids": sale_ids}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--business", required=True)
    args = parser.parse_args()
    print(seed(args.business))
