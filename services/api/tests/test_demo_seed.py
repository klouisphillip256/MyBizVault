from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Agreement, Business, Counterparty, Membership, PaymentRecord, Transaction, User
from scripts import seed_demo


def test_fictional_seed_is_idempotent_and_creates_documents(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(seed_demo, "engine", engine)
    with Session(engine) as db:
        owner = User(email="demo-owner@example.com", full_name="Demo Owner", password_hash="unused")
        business = Business(name="Seed Test Shop")
        db.add_all([owner, business])
        db.flush()
        db.add(Membership(business_id=business.id, user_id=owner.id, role="owner", is_active=True))
        db.commit()

    first = seed_demo.seed("Seed Test Shop")
    second = seed_demo.seed("Seed Test Shop")
    assert first["customers_created"] == 3
    assert first["transactions_created"] == 3
    assert first["payments_created"] == 1
    assert second["customers_created"] == 0
    assert second["transactions_created"] == 0
    assert second["payments_created"] == 0
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Counterparty)) == 3
        assert db.scalar(select(func.count()).select_from(Transaction)) == 3
        assert db.scalar(select(func.count()).select_from(Agreement)) == 2
        assert db.scalar(select(func.count()).select_from(PaymentRecord)) == 1
