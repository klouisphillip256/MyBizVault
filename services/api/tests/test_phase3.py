from hashlib import sha256
from urllib.parse import urlsplit
from datetime import timedelta
import pytest

from app.core.config import settings
from app.db.models import utcnow
from app.modules import agreements
from app.modules import vault
from test_phase2 import clients, csrf, register  # noqa: F401 - shared fixture and helpers


@pytest.fixture(autouse=True)
def isolated_vault(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path / "vault"))


def sale(owner, business_id):
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
                          json={"display_name": "Bosco Okello", "phone": "+256700000001"})
    assert customer.status_code == 201
    transaction = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
                             json={"counterparty_id": customer.json()["id"], "description": "Wholesale goods",
                                   "transaction_date": "2026-11-24", "total_ugx": 1_000_000,
                                   "paid_ugx": 700_000, "due_date": "2026-12-01",
                                   "delivery_notes": "Delivered to Bosco's shop"})
    assert transaction.status_code == 201
    return transaction.json()["id"]


def draft(owner, business_id, transaction_id):
    response = owner.post(f"/api/businesses/{business_id}/agreements", headers=csrf(owner),
                          json={"transaction_id": transaction_id})
    assert response.status_code == 201, response.text
    return response.json()


def invite(owner, business_id, agreement_id):
    response = owner.post(f"/api/businesses/{business_id}/agreements/{agreement_id}/invitation",
                          headers=csrf(owner))
    assert response.status_code == 200, response.text
    url = response.json()["review_url"]
    assert urlsplit(url).path == "/review/invite"
    token = urlsplit(url).fragment.removeprefix("token=")
    assert len(token) > 32
    return {"X-Invitation-Token": token}


def test_acceptance_preserves_exact_version_and_link_access(clients, monkeypatch):
    monkeypatch.setattr(settings, "development_verification", True)
    owner, other, _staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    other_id = register(other, "other@example.com", "Other Business")
    agreement = draft(owner, business_id, sale(owner, business_id))
    agreement_id = agreement["id"]
    first = agreement["versions"][0]
    assert "UGX 300,000" in first["content"]
    assert first["content_sha256"] == sha256(first["content"].encode()).hexdigest()
    assert owner.post(f"/api/businesses/{business_id}/agreements", headers=csrf(owner),
                      json={"transaction_id": agreement["transaction_id"]}).status_code == 409
    assert other.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").status_code == 404
    assert other.get(f"/api/businesses/{other_id}/agreements/{agreement_id}").status_code == 404
    header = invite(owner, business_id, agreement_id)
    review = other.get("/api/external/review", headers=header)
    assert review.status_code == 200
    assert review.headers["cache-control"] == "no-store"
    assert review.json()["content"] == first["content"]
    assert review.json()["identity_verified"] is False
    assert other.get("/api/external/review", headers={"X-Invitation-Token": "invalid"}).status_code == 404
    challenge = other.post("/api/external/challenge", headers=header)
    assert challenge.status_code == 200, challenge.text
    code = challenge.json()["development_code"]
    assert len(code) == 6
    assert other.post("/api/external/challenge", headers=header).status_code == 429
    wrong_version = other.post("/api/external/accept", headers=header,
                               json={"version_id": "wrong", "code": code,
                                     "explicitly_accepted": True})
    assert wrong_version.status_code == 409
    assert other.post("/api/external/accept", headers=header,
                      json={"version_id": first["id"], "code": code,
                            "explicitly_accepted": False}).status_code == 409
    accepted = other.post("/api/external/accept", headers=header,
                          json={"version_id": first["id"], "code": code,
                                "explicitly_accepted": True})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"status": "confirmed", "version_id": first["id"],
                               "content_sha256": first["content_sha256"], "identity_verified": False}
    assert other.post("/api/external/accept", headers=header,
                      json={"version_id": first["id"], "code": code,
                            "explicitly_accepted": True}).status_code == 404
    assert other.get("/api/external/review", headers=header).json()["status"] == "confirmed"
    preserved = owner.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").json()
    assert preserved["versions"][0] == first
    assert preserved["events"][0]["action"] == "accepted"
    assert preserved["events"][0]["verification_method"] == "development_code"
    documents = owner.get(f"/api/businesses/{business_id}/documents")
    assert documents.status_code == 200
    assert len(documents.json()) == 1
    assert documents.json()[0]["source"] == "agreement"
    document_id = documents.json()[0]["id"]
    content = owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/1/content")
    assert content.status_code == 200
    assert content.content.decode("utf-8") == first["content"]
    archived_again = owner.post(f"/api/businesses/{business_id}/agreements/{agreement_id}/vault-document",
                                headers=csrf(owner))
    assert archived_again.status_code == 200
    assert archived_again.json()["id"] == document_id
    assert other.get(f"/api/businesses/{business_id}/documents/{document_id}").status_code == 404
    assert owner.post(f"/api/businesses/{business_id}/documents/{document_id}/versions",
                      headers=csrf(owner), files={"file": ("changed.pdf", b"%PDF-changed", "application/pdf")}).status_code == 409
    assert owner.put(f"/api/businesses/{business_id}/agreements/{agreement_id}/draft",
                     headers=csrf(owner), json={"content": first["content"] + "\nRevised"}).status_code == 409


def test_correction_creates_new_version_and_revokes_old_link(clients, monkeypatch):
    monkeypatch.setattr(settings, "development_verification", True)
    owner, other, _staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    agreement = draft(owner, business_id, sale(owner, business_id))
    old_id = agreement["versions"][0]["id"]
    first_link = invite(owner, business_id, agreement["id"])
    assert other.post("/api/external/respond", headers=first_link,
                      json={"version_id": old_id, "action": "correction_requested",
                            "note": "Please clarify the delivery location."}).status_code == 200
    assert other.get("/api/external/review", headers=first_link).status_code == 404
    assert owner.put(f"/api/businesses/{business_id}/agreements/{agreement['id']}/draft",
                     headers=csrf(owner), json={"content": agreement["versions"][0]["content"].replace(
                         "Outstanding balance: UGX 300,000", "Outstanding balance: UGX 400,000")}).status_code == 422
    revised = owner.put(f"/api/businesses/{business_id}/agreements/{agreement['id']}/draft",
                        headers=csrf(owner), json={"content": agreement["versions"][0]["content"] +
                                                   "\nDelivery location: Bosco's shop, Kampala."})
    assert revised.status_code == 200, revised.text
    assert revised.json()["current_version"] == 2
    assert revised.json()["versions"][1]["id"] == old_id
    assert revised.json()["events"][0]["action"] == "correction_requested"
    second_link = invite(owner, business_id, agreement["id"])
    assert other.get("/api/external/review", headers=second_link).json()["version"] == 2
    assert other.get("/api/external/review", headers=first_link).status_code == 404
    assert other.post("/api/external/respond", headers=second_link,
                      json={"version_id": old_id, "action": "rejected"}).status_code == 409
    rejected = other.post("/api/external/respond", headers=second_link,
                          json={"version_id": revised.json()["current_version_id"],
                                "action": "rejected", "note": "I do not agree."})
    assert rejected.status_code == 200
    assert owner.get(f"/api/businesses/{business_id}/agreements/{agreement['id']}").json()["status"] == "rejected"


def test_code_attempt_limit_and_staff_permission(clients, monkeypatch):
    monkeypatch.setattr(settings, "development_verification", True)
    owner, other, staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    agreement = draft(owner, business_id, sale(owner, business_id))
    added = owner.post(f"/api/businesses/{business_id}/staff", headers=csrf(owner),
                       json={"full_name": "Sales Staff", "email": "sales@example.com",
                             "password": "staff-password-2026"})
    assert added.status_code == 201
    assert staff.post("/api/auth/login", json={"email": "sales@example.com",
                                                  "password": "staff-password-2026"}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/agreements").status_code == 403
    assert owner.patch(f"/api/businesses/{business_id}/staff/{added.json()['id']}", headers=csrf(owner),
                       json={"can_view_transactions": False, "can_create_transactions": False,
                             "can_manage_customers": False, "can_manage_agreements": True,
                             "is_active": True}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/agreements").status_code == 200
    header = invite(owner, business_id, agreement["id"])
    code = other.post("/api/external/challenge", headers=header).json()["development_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert other.post("/api/external/accept", headers=header,
                          json={"version_id": agreement["current_version_id"], "code": wrong,
                                "explicitly_accepted": True}).status_code == 400
    assert other.post("/api/external/accept", headers=header,
                      json={"version_id": agreement["current_version_id"], "code": code,
                            "explicitly_accepted": True}).status_code == 429


def test_reissue_expiry_and_disabled_delivery(clients, monkeypatch):
    monkeypatch.setattr(settings, "development_verification", False)
    owner, other, _staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    agreement = draft(owner, business_id, sale(owner, business_id))
    first = invite(owner, business_id, agreement["id"])
    assert other.get("/api/external/review", headers=first).status_code == 200
    assert other.post("/api/external/challenge", headers=first).status_code == 503
    second = invite(owner, business_id, agreement["id"])
    assert other.get("/api/external/review", headers=first).status_code == 404
    assert other.get("/api/external/review", headers=second).status_code == 200
    current_time = utcnow()
    monkeypatch.setattr(agreements, "utcnow", lambda: current_time + timedelta(days=8))
    assert other.get("/api/external/review", headers=second).status_code == 404


def test_storage_failure_rolls_back_acceptance(clients, monkeypatch):
    monkeypatch.setattr(settings, "development_verification", True)
    owner, other, _staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    agreement = draft(owner, business_id, sale(owner, business_id))
    header = invite(owner, business_id, agreement["id"])
    code = other.post("/api/external/challenge", headers=header).json()["development_code"]

    class FailingStorage:
        def put(self, key, data, content_type):
            raise OSError("Storage unavailable")

        def delete(self, key):
            pass

    monkeypatch.setattr(vault, "storage", lambda: FailingStorage())
    accepted = other.post("/api/external/accept", headers=header,
                          json={"version_id": agreement["current_version_id"],
                                "code": code, "explicitly_accepted": True})
    assert accepted.status_code == 503
    assert owner.get(f"/api/businesses/{business_id}/agreements/{agreement['id']}").json()["status"] == "invited"
    assert owner.get(f"/api/businesses/{business_id}/documents").json() == []
