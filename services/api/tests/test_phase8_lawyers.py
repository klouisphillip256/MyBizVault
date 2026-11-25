from test_phase2 import clients, csrf, register  # noqa: F401
from app.core.config import settings


def test_fictional_profiles_filter_and_requests_stay_in_business(clients):
    owner, other, staff = clients
    business_id = register(owner, "phase8-owner@example.com", "Fictional Company")
    other_id = register(other, "phase8-other@example.com", "Another Company")

    profiles = owner.get("/api/lawyers/profiles?issue_type=employment")
    assert profiles.status_code == 200
    assert profiles.json() and all("employment" in item["focus"] and item["fictional"] for item in profiles.json())
    assert owner.get("/api/lawyers/profiles?issue_type=unknown").status_code == 422

    path = f"/api/businesses/{business_id}/consultation-requests"
    payload = {"profile_id": "employment", "issue_type": "employment",
               "issue_summary": "Fictional request for advice on employee contract terms."}
    assert owner.post(path, json=payload).status_code == 403
    assert owner.post(path, headers=csrf(owner), json={**payload, "profile_id": "debt"}).status_code == 422
    created = owner.post(path, headers=csrf(owner), json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    assert owner.get(path).json()[0]["issue_summary"] == payload["issue_summary"]
    assert other.get(path).status_code == 404
    assert other.post(path, headers=csrf(other), json=payload).status_code == 404
    assert other.get(f"/api/businesses/{other_id}/consultation-requests").json() == []
    assert staff.get(path).status_code == 401


def test_contract_draft_uses_existing_private_vault(clients, monkeypatch, tmp_path):
    owner, other, _staff = clients
    business_id = register(owner, "phase8-contract@example.com", "Fictional Seller")
    register(other, "phase8-outsider@example.com", "Other Seller")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path / "vault"))
    payload = {"title": "Fictional Supply Terms", "counterparty_name": "Demo Buyer",
               "purpose": "Supply ten fictional office chairs.",
               "payment_terms": "UGX 100,000 after delivery.",
               "obligations": "Seller delivers the chairs and buyer checks them on receipt."}
    url = f"/api/businesses/{business_id}/contracts/drafts"
    assert owner.post(url, json=payload).status_code == 403
    created = owner.post(url, headers=csrf(owner), json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["category"] == "contract" and item["current_file"]["content_type"] == "application/pdf"
    assert owner.get(f"/api/businesses/{business_id}/documents/{item['id']}").status_code == 200
    content = owner.get(f"/api/businesses/{business_id}/documents/{item['id']}/versions/1/content")
    assert content.status_code == 200 and content.content.startswith(b"%PDF-")
    assert other.get(f"/api/businesses/{business_id}/documents/{item['id']}").status_code == 404
