from test_phase2 import clients, csrf, register  # noqa: F401

import pytest
from sqlalchemy import create_engine

from app.core.storage import DatabaseStorage
from app.db.base import Base
from app.db.models import StoredObject


def test_receipts_agreement_versions_and_tenant_access(clients):
    owner, outsider, _staff = clients
    business_id = register(owner, "owner@example.com", "Fictional Traders")
    register(outsider, "other@example.com", "Other Fictional Shop")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Fictional Buyer", "phone": "+256700000001",
              "email": "buyer@example.com"}).json()
    assert owner.patch(f"/api/businesses/{business_id}", headers=csrf(owner),
        json={"name": "Fictional Traders", "phone": "+256700000002",
              "email": "seller@example.com"}).status_code == 200
    base = f"/api/businesses/{business_id}/transactions"
    partial = owner.post(base, headers=csrf(owner), json={
        "counterparty_id": customer["id"], "description": "Three fictional chairs",
        "line_items": [{"description": "Fictional chairs", "quantity": 2, "unit_price_ugx": 1000},
                       {"description": "Fictional stool", "quantity": 1, "unit_price_ugx": 1000}],
        "transaction_date": "2026-11-24", "total_ugx": 3000,
        "paid_ugx": 1000, "due_date": "2026-12-01"})
    assert partial.status_code == 201, partial.text
    transaction_id = partial.json()["id"]
    detail = owner.get(f"{base}/{transaction_id}").json()
    assert len(detail["line_items"]) == 2
    assert len(detail["receipts"]) == 1
    assert detail["receipts"][0]["amount_ugx"] == 1000
    assert detail["agreement"]["status"] == "draft"
    agreement_id = detail["agreement"]["id"]
    agreement = owner.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").json()
    assert "Fictional Buyer" in agreement["versions"][0]["content"]
    assert "seller@example.com" in agreement["versions"][0]["content"]
    assert "Item 2: Fictional stool" in agreement["versions"][0]["content"]
    receipt_id = detail["receipts"][0]["id"]
    receipt_url = f"{base}/{transaction_id}/receipts/{receipt_id}/pdf"
    pdf = owner.get(receipt_url)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert outsider.get(receipt_url).status_code == 404
    assert outsider.get(f"{base}/{transaction_id}").status_code == 404
    agreement_pdf = owner.get(f"/api/businesses/{business_id}/agreements/{agreement_id}/pdf?version=1")
    assert agreement_pdf.status_code == 200 and agreement_pdf.content.startswith(b"%PDF")

    payment = owner.post(f"{base}/{transaction_id}/payments", headers=csrf(owner),
        json={"amount_ugx": 2000, "paid_on": "2026-11-24"})
    assert payment.status_code == 201, payment.text
    after = owner.get(f"{base}/{transaction_id}").json()
    assert after["balance_ugx"] == 0
    assert len(after["receipts"]) == 2
    assert after["agreement"]["id"] == agreement_id
    assert after["agreement"]["status"] == "draft"
    assert owner.get(f"{base}/{transaction_id}").json()["receipts"] == after["receipts"]


def test_fully_paid_transaction_has_receipt_without_agreement(clients):
    owner, _other, _staff = clients
    business_id = register(owner, "cash@example.com", "Fictional Cash Shop")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Cash Buyer", "email": "cashbuyer@example.com"}).json()
    transaction = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
        json={"counterparty_id": customer["id"], "description": "Fictional desk",
              "transaction_date": "2026-11-24", "total_ugx": 500, "paid_ugx": 500})
    assert transaction.status_code == 201, transaction.text
    detail = owner.get(f"/api/businesses/{business_id}/transactions/{transaction.json()['id']}").json()
    assert detail["agreement"] is None
    assert len(detail["receipts"]) == 1


def test_database_storage_keeps_bytes_without_local_files(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'objects.db').as_posix()}")
    Base.metadata.create_all(engine, tables=[StoredObject.__table__])
    storage = DatabaseStorage(engine)
    storage.put("business/document.pdf", b"%PDF-demo", "application/pdf")
    assert storage.get("business/document.pdf") == b"%PDF-demo"
    with pytest.raises(Exception):
        storage.put("business/document.pdf", b"replaced", "application/pdf")
    assert storage.get("business/document.pdf") == b"%PDF-demo"
    storage.delete("business/document.pdf")
    with pytest.raises(FileNotFoundError):
        storage.get("business/document.pdf")
    engine.dispose()
