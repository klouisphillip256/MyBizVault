from datetime import date, timedelta

import pytest

from app.core.config import settings
from test_phase2 import clients, csrf, register  # noqa: F401 - fixture and helpers


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path / "vault"))


def create_sale(client, business_id, customer="Bosco", total=1000, paid=200):
    contact = client.post(f"/api/businesses/{business_id}/customers", headers=csrf(client),
                          json={"display_name": customer, "phone": "+256700000111"})
    assert contact.status_code == 201, contact.text
    start = date.today() - timedelta(days=5)
    sale = client.post(f"/api/businesses/{business_id}/transactions", headers=csrf(client),
                       json={"counterparty_id": contact.json()["id"], "description": "Goods delivered",
                             "transaction_date": start.isoformat(), "total_ugx": total,
                             "paid_ugx": paid, "due_date": (date.today() - timedelta(days=1)).isoformat()})
    assert sale.status_code == 201, sale.text
    return sale.json()


def path(business_id, transaction_id):
    return f"/api/businesses/{business_id}/transactions/{transaction_id}"


def test_partial_payments_balances_disputes_and_history(clients):
    owner, other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    other_id = register(other, "other@example.com", "Other Business")
    sale = create_sale(owner, business_id)
    base = path(business_id, sale["id"])
    assert sale["balance_ugx"] == 800 and sale["is_overdue"]
    assert owner.post(base + "/payments", json={"amount_ugx": 300,
                                                "paid_on": date.today().isoformat()}).status_code == 403
    created = owner.post(base + "/payments", headers=csrf(owner),
                         json={"amount_ugx": 300, "paid_on": date.today().isoformat(),
                               "reference": "cash-1"})
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    assert created.json()["verification_source"] == "business_recorded"
    assert owner.get(base).json()["balance_ugx"] == 500
    assert owner.post(base + "/payments", headers=csrf(owner),
                      json={"amount_ugx": 501, "paid_on": date.today().isoformat()}).status_code == 409
    assert owner.post(base + "/payments", headers=csrf(owner),
                      json={"amount_ugx": 1, "paid_on": (date.today() + timedelta(days=1)).isoformat()}).status_code == 422
    assert other.get(base + "/payments").status_code == 404
    assert other.get(path(other_id, sale["id"]) + "/payments").status_code == 404
    disputed = owner.post(base + f"/payments/{payment_id}/status", headers=csrf(owner),
                          json={"action": "disputed", "note": "Customer contests this payment"})
    assert disputed.status_code == 200
    assert owner.get(base).json()["balance_ugx"] == 800
    assert owner.get(base).json()["disputed_ugx"] == 300
    acknowledged = owner.post(base + f"/payments/{payment_id}/status", headers=csrf(owner),
                              json={"action": "acknowledged", "note": "Business reviewed receipt"})
    assert acknowledged.status_code == 200
    assert owner.get(base).json()["balance_ugx"] == 500
    assert [row["action"] for row in owner.get(base + "/obligation-history").json()] == [
        "payment_acknowledged", "payment_disputed", "payment_reported"]


def test_proposals_deadlines_settlements_disputes_and_evidence_scope(clients):
    owner, other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    other_id = register(other, "other@example.com", "Other Business")
    sale = create_sale(owner, business_id)
    other_sale = create_sale(other, other_id, customer="Other")
    base = path(business_id, sale["id"])
    foreign_document = other.post(f"/api/businesses/{other_id}/documents", headers=csrf(other),
        data={"title": "Private receipt", "category": "receipt"},
        files={"file": ("receipt.pdf", b"%PDF-1.4\nreceipt", "application/pdf")})
    assert foreign_document.status_code == 201
    assert owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "payment_dispute", "proposal": "Payment amount is contested",
        "evidence_document_id": foreign_document.json()["id"]}).status_code == 404
    extension_date = (date.today() + timedelta(days=10)).isoformat()
    proposed = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "extension", "proposal": "Allow ten more days to pay", "proposed_due_date": extension_date})
    assert proposed.status_code == 201, proposed.text
    proposal_id = proposed.json()["id"]
    assert owner.get(base).json()["effective_due_date"] == sale["due_date"]
    accepted = owner.post(base + f"/negotiations/{proposal_id}/response", headers=csrf(owner),
                          json={"action": "accepted", "note": "Business recorded verbal response"})
    assert accepted.status_code == 200
    revised = owner.get(base).json()
    assert revised["due_date"] == sale["due_date"]
    assert revised["effective_due_date"] == extension_date
    assert revised["due_date_source"] == "business_recorded_proposal"
    assert not revised["is_overdue"]
    assert owner.post(base + f"/negotiations/{proposal_id}/response", headers=csrf(owner),
                      json={"action": "declined", "note": "Changed mind"}).status_code == 409
    settlement = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "settlement", "proposal": "Offer a reduced final settlement", "proposed_amount_ugx": 600})
    assert settlement.status_code == 201
    assert owner.get(base).json()["balance_ugx"] == 800  # A proposal never writes down the debt.
    dispute = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "payment_dispute", "proposal": "Customer disputes whether goods arrived"})
    assert dispute.status_code == 201
    resolved = owner.post(base + f"/negotiations/{dispute.json()['id']}/response", headers=csrf(owner),
                          json={"action": "resolved", "note": "Business recorded a resolution"})
    assert resolved.status_code == 200
    assert owner.get(base + "/negotiations").json()[0]["status"] == "resolved"
    assert other.get(base + "/negotiations").status_code == 404
    assert owner.get(path(business_id, other_sale["id"]) + "/negotiations").status_code == 404


def test_staff_obligation_permission_is_separate(clients):
    owner, _other, staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    sale = create_sale(owner, business_id)
    base = path(business_id, sale["id"])
    added = owner.post(f"/api/businesses/{business_id}/staff", headers=csrf(owner), json={
        "full_name": "Sales Staff", "email": "staff@example.com", "password": "staff-password-2026",
        "can_view_transactions": True})
    assert added.status_code == 201
    assert staff.post("/api/auth/login", json={"email": "staff@example.com",
        "password": "staff-password-2026"}).status_code == 200
    assert staff.get(base + "/payments").status_code == 200
    assert staff.post(base + "/payments", headers=csrf(staff), json={
        "amount_ugx": 100, "paid_on": date.today().isoformat()}).status_code == 403
    changed = owner.patch(f"/api/businesses/{business_id}/staff/{added.json()['id']}",
        headers=csrf(owner), json={"can_view_transactions": True, "can_create_transactions": False,
            "can_manage_customers": False, "can_manage_agreements": False,
            "can_view_documents": False, "can_manage_documents": False,
            "can_manage_obligations": True, "is_active": True})
    assert changed.status_code == 200
    assert staff.post(base + "/payments", headers=csrf(staff), json={
        "amount_ugx": 100, "paid_on": date.today().isoformat()}).status_code == 201
