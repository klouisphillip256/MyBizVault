from app.core.config import settings
import re
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse
from test_phase2 import clients, csrf, register  # noqa: F401


def test_delivery_log_and_authenticated_webhook_transition(clients, monkeypatch):
    owner, outsider, _staff = clients
    business_id = register(owner, "sender@example.com", "Fictional Seller")
    register(outsider, "outsider@example.com", "Other Seller")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Fictional Buyer", "email": "buyer@example.com"}).json()
    sale = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
        json={"counterparty_id": customer["id"], "description": "Fictional chairs",
              "transaction_date": "2026-11-24", "total_ugx": 1000,
              "paid_ugx": 100, "due_date": "2026-12-01"}).json()
    base = f"/api/businesses/{business_id}/transactions/{sale['id']}"
    agreement_id = owner.get(base).json()["agreement"]["id"]
    assert owner.get(f"/api/businesses/{business_id}/delivery/provider-tests").status_code == 200
    assert outsider.get(f"/api/businesses/{business_id}/delivery/provider-tests").status_code == 404
    monkeypatch.setattr(settings, "brevo_api_key", "test-key")
    monkeypatch.setattr(settings, "brevo_sender_email", "sender@example.com")
    monkeypatch.setattr(settings, "brevo_webhook_token", "webhook-secret")
    calls = []
    monkeypatch.setattr("app.modules.agreements.send_message", lambda *args: calls.append(args) or
                        {"provider": "brevo", "status": "submitted", "message_id": "message-123"})
    assert owner.get(base).json()["communications"] == []
    sent = owner.post(f"/api/businesses/{business_id}/agreements/{agreement_id}/invitation/send",
        headers=csrf(owner), json={"channel": "email"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["delivery_status"] == "submitted"
    assert len(calls) == 1
    assert owner.get(base).json()["communications"][0]["status"] == "submitted"
    hook = "/api/webhooks/brevo"
    event = {"message-id": "message-123", "event": "delivered"}
    assert owner.post(hook, json=event).status_code == 403
    assert owner.post(hook, headers={"Authorization": "Bearer wrong"}, json=event).status_code == 403
    assert owner.post(hook, headers={"Authorization": "Bearer webhook-secret"}, json=event).status_code == 200
    assert owner.get(base).json()["communications"][0]["status"] == "delivered"
    assert owner.post(hook, headers={"Authorization": "Bearer webhook-secret"}, json=event).status_code == 200
    assert owner.get(base).json()["communications"][0]["status"] == "delivered"


def test_explicit_email_code_accepts_exact_version_without_development_mode(clients, monkeypatch):
    owner, customer_client, _staff = clients
    business_id = register(owner, "codes@example.com", "Fictional Codes Shop")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Fictional Buyer", "email": "buyer@example.com"}).json()
    sale = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
        json={"counterparty_id": customer["id"], "description": "Fictional table",
              "transaction_date": "2026-11-24", "total_ugx": 1000,
              "paid_ugx": 0, "due_date": "2026-12-01"}).json()
    agreement_id = owner.get(f"/api/businesses/{business_id}/transactions/{sale['id']}").json()["agreement"]["id"]
    invite = owner.post(f"/api/businesses/{business_id}/agreements/{agreement_id}/invitation",
        headers=csrf(owner)).json()
    token = parse_qs(urlparse(invite["review_url"]).fragment)["token"][0]
    headers = {"X-Invitation-Token": token}
    monkeypatch.setattr(settings, "development_verification", False)
    monkeypatch.setattr(settings, "brevo_api_key", "example-key")
    monkeypatch.setattr(settings, "brevo_sender_email", "sender@example.com")
    sent = []
    monkeypatch.setattr("app.modules.agreements.send_message", lambda *args: sent.append(args) or
                        {"provider": "brevo", "status": "submitted", "message_id": "code-message"})
    review = customer_client.get("/api/external/review", headers=headers).json()
    assert review["verification_delivery_available"] is True
    result = customer_client.post("/api/external/challenge", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["delivery_status"] == "submitted"
    assert "development_code" not in result.json()
    assert len(sent) == 1 and sent[0][0] == "email" and sent[0][1] == "buyer@example.com"
    code = re.search(r"\b\d{6}\b", sent[0][3]).group()
    wrong = customer_client.post("/api/external/accept", headers=headers,
        json={"version_id": "incorrect", "code": code, "explicitly_accepted": True})
    assert wrong.status_code == 409
    accepted = customer_client.post("/api/external/accept", headers=headers,
        json={"version_id": review["version_id"], "code": code, "explicitly_accepted": True})
    assert accepted.status_code == 200, accepted.text
    detail = owner.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").json()
    assert detail["events"][0]["verification_method"] == "email_code"
    assert customer_client.post("/api/external/accept", headers=headers,
        json={"version_id": review["version_id"], "code": code, "explicitly_accepted": True}).status_code == 404


def test_meta_and_at_webhooks_require_shared_secrets(clients, monkeypatch):
    client = clients[0]
    monkeypatch.setattr(settings, "meta_app_secret", "fictional-app-secret")
    monkeypatch.setattr(settings, "at_webhook_token", "fictional-callback-token")
    body = json.dumps({"entry": []}).encode()
    signature = "sha256=" + hmac.new(b"fictional-app-secret", body, hashlib.sha256).hexdigest()
    assert client.post("/api/webhooks/meta", content=body,
        headers={"Content-Type": "application/json"}).status_code == 403
    assert client.post("/api/webhooks/meta", content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature}).status_code == 200
    assert client.post("/api/webhooks/africas-talking", data={"id": "fictional"}).status_code == 403
    assert client.post("/api/webhooks/africas-talking?token=fictional-callback-token",
        data={"id": "fictional", "status": "Success"}).status_code == 200


def test_brevo_sender_probe_matches_configured_active_sender(monkeypatch):
    from app.modules import delivery_routes

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"senders":[{"email":"sender@example.com","active":true}]}'

    monkeypatch.setattr(settings, "brevo_api_key", "test-key")
    monkeypatch.setattr(settings, "brevo_sender_email", "Sender@Example.com")
    monkeypatch.setattr(delivery_routes, "urlopen", lambda *_args, **_kwargs: Response())
    assert delivery_routes._brevo_sender_status() == "active"
    monkeypatch.setattr(settings, "brevo_sender_email", "other@example.com")
    assert delivery_routes._brevo_sender_status() == "not_found"
