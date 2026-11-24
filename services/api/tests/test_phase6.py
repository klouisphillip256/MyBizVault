from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException

from app.core.config import settings
from test_phase2 import clients, csrf, register  # noqa: F401 - fixture and helpers
from test_phase5 import create_sale, path


@pytest.fixture(autouse=True)
def development_verification(monkeypatch):
    monkeypatch.setattr(settings, "development_verification", True)


def token_from(response):
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["review_url"]).fragment)["token"][0]


def test_proposal_link_reissue_code_and_immutable_original_terms(clients):
    owner, other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    other_id = register(other, "other@example.com", "Other Business")
    sale = create_sale(owner, business_id)
    base = path(business_id, sale["id"])
    proposed_due = (date.today() + timedelta(days=10)).isoformat()
    proposal = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "extension", "proposal": "Allow ten more days for the outstanding balance",
        "proposed_due_date": proposed_due})
    assert proposal.status_code == 201
    invite_path = base + f"/negotiations/{proposal.json()['id']}/invitation"
    assert owner.post(invite_path).status_code == 403
    assert other.post(invite_path, headers=csrf(other)).status_code == 404
    first = token_from(owner.post(invite_path, headers=csrf(owner)))
    second = token_from(owner.post(invite_path, headers=csrf(owner)))
    assert owner.get("/api/external/proposal", headers={"X-Invitation-Token": first}).status_code == 404
    headers = {"X-Invitation-Token": second}
    review = owner.get("/api/external/proposal", headers=headers)
    assert review.status_code == 200
    assert review.headers["cache-control"] == "no-store"
    assert review.json()["original_due_date"] == sale["due_date"]
    assert review.json()["proposed_due_date"] == proposed_due
    assert review.json()["identity_verified"] is False
    challenge = owner.post("/api/external/proposal/challenge", headers=headers)
    assert challenge.status_code == 200
    assert owner.post("/api/external/proposal/challenge", headers=headers).status_code == 429
    incorrect_code = "000000" if challenge.json()["development_code"] != "000000" else "999999"
    wrong = owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal.json()["id"], "action": "accepted",
        "code": incorrect_code, "explicitly_accepted": True})
    assert wrong.status_code == 400
    assert owner.get(base).json()["effective_due_date"] == sale["due_date"]
    accepted = owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal.json()["id"], "action": "accepted",
        "code": challenge.json()["development_code"], "explicitly_accepted": True})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["identity_verified"] is False
    assert owner.get(base).json()["due_date"] == sale["due_date"]
    assert owner.get(base).json()["effective_due_date"] == proposed_due
    assert owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal.json()["id"], "action": "accepted",
        "code": challenge.json()["development_code"], "explicitly_accepted": True}).status_code == 404
    rows = owner.get(base + "/negotiations").json()
    assert rows[0]["verification_source"] == "development_code"
    assert "customer_link_accepted" in [row["action"] for row in owner.get(base + "/obligation-history").json()]
    assert other.get(path(other_id, sale["id"]) + "/negotiations").status_code == 404


def test_proposal_correction_and_production_acceptance_gate(clients, monkeypatch):
    owner, _other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    sale = create_sale(owner, business_id)
    base = path(business_id, sale["id"])
    proposal = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "settlement", "proposal": "Propose a reduced final amount", "proposed_amount_ugx": 500}).json()
    token = token_from(owner.post(base + f"/negotiations/{proposal['id']}/invitation", headers=csrf(owner)))
    headers = {"X-Invitation-Token": token}
    monkeypatch.setattr(settings, "development_verification", False)
    assert owner.post("/api/external/proposal/challenge", headers=headers).status_code == 503
    assert owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal["id"], "action": "accepted",
        "code": "123456", "explicitly_accepted": True}).status_code == 503
    assert owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal["id"], "action": "correction_requested"}).status_code == 422
    corrected = owner.post("/api/external/proposal/respond", headers=headers, json={
        "proposal_id": proposal["id"], "action": "correction_requested",
        "note": "Clarify the proposed final payment date"})
    assert corrected.status_code == 200
    assert owner.get(base + "/negotiations").json()[0]["verification_source"] == "invitation_link_only"
    assert owner.get(base).json()["balance_ugx"] == 800


def test_message_delivery_requires_explicit_action_and_configuration(clients, monkeypatch):
    owner, _other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    sale = create_sale(owner, business_id)
    base = path(business_id, sale["id"])
    proposal = owner.post(base + "/negotiations", headers=csrf(owner), json={
        "kind": "payment_dispute", "proposal": "Please review this delivery disagreement"}).json()
    send_path = base + f"/negotiations/{proposal['id']}/invitation/send"
    assert owner.get("/api/delivery/capabilities").json() == {"email": False, "sms": False}
    assert owner.post(send_path, headers=csrf(owner), json={"channel": "sms"}).status_code == 503
    assert owner.post(send_path, json={"channel": "sms"}).status_code == 403
    calls = []
    monkeypatch.setattr(settings, "sms_webhook_url", "https://sms.example.test/send")
    monkeypatch.setattr(settings, "sms_webhook_token", "test-token")
    monkeypatch.setattr("app.modules.proposal_invitations.send_message",
        lambda *args: calls.append(args))
    assert owner.get("/api/delivery/capabilities").json()["sms"] is True
    manual = owner.post(base + f"/negotiations/{proposal['id']}/invitation", headers=csrf(owner))
    assert manual.status_code == 200 and calls == []
    sent = owner.post(send_path, headers=csrf(owner), json={"channel": "sms"})
    assert sent.status_code == 200 and sent.json()["delivery"] == "sms"
    assert len(calls) == 1 and calls[0][0] == "sms" and calls[0][1] == "+256700000111"
    old_token = parse_qs(urlsplit(manual.json()["review_url"]).fragment)["token"][0]
    assert owner.get("/api/external/proposal", headers={"X-Invitation-Token": old_token}).status_code == 404
    def fail_send(*_args):
        raise HTTPException(503, "SMS delivery failed")
    monkeypatch.setattr("app.modules.proposal_invitations.send_message", fail_send)
    failed = owner.post(send_path, headers=csrf(owner), json={"channel": "sms"})
    assert failed.status_code == 200 and failed.json()["delivery"] == "failed"
    assert failed.json()["review_url"]


def test_agreement_email_send_uses_configured_adapter_only_on_click(clients, monkeypatch):
    owner, _other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Buyer", "email": "buyer@example.com"}).json()
    sale = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
        json={"counterparty_id": customer["id"], "description": "Goods delivered",
              "transaction_date": "2026-11-24", "total_ugx": 1000,
              "paid_ugx": 200, "due_date": "2026-12-01"}).json()
    agreement = owner.post(f"/api/businesses/{business_id}/agreements", headers=csrf(owner),
        json={"transaction_id": sale["id"]}).json()
    base = f"/api/businesses/{business_id}/agreements/{agreement['id']}/invitation"
    assert owner.post(base + "/send", headers=csrf(owner), json={"channel": "email"}).status_code == 503
    calls = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@example.test")
    monkeypatch.setattr("app.modules.agreements.send_message", lambda *args: calls.append(args))
    assert owner.post(base, headers=csrf(owner)).status_code == 200
    assert calls == []
    sent = owner.post(base + "/send", headers=csrf(owner), json={"channel": "email"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["delivery"] == "email"
    assert calls[0][0] == "email" and calls[0][1] == "buyer@example.com"
