import re

from app.core.config import settings
from test_phase2 import clients, csrf, register  # noqa: F401


def test_sandbox_ussd_requires_phone_code_and_explicit_version_response(clients, monkeypatch, tmp_path):
    owner, outsider, _staff = clients
    business_id = register(owner, "ussd-owner@example.com", "Fictional Shop")
    register(outsider, "ussd-other@example.com", "Other Shop")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
        json={"display_name": "Test Buyer", "phone": "+256700000001"}).json()
    sale = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
        json={"counterparty_id": customer["id"], "description": "Fictional supplies",
              "transaction_date": "2026-11-24", "total_ugx": 3000,
              "paid_ugx": 1000, "due_date": "2026-12-01"}).json()
    agreement_id = owner.get(f"/api/businesses/{business_id}/transactions/{sale['id']}").json()["agreement"]["id"]
    monkeypatch.setattr(settings, "at_api_key", "sandbox-test-key")
    monkeypatch.setattr(settings, "at_sandbox", True)
    monkeypatch.setattr(settings, "ussd_callback_token", "callback-test-secret")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path / "vault"))
    sent = []
    monkeypatch.setattr("app.modules.ussd.send_message", lambda *args: sent.append(args) or
                        {"provider": "africas_talking", "status": "simulated", "message_id": "sandbox-1"})
    send = owner.post(f"/api/businesses/{business_id}/agreements/{agreement_id}/ussd/send",
        headers=csrf(owner))
    assert send.status_code == 200, send.text
    assert send.json()["status"] == "simulated"
    assert len(sent) == 1
    code = re.search(r"code ([0-9]{6})", sent[0][3]).group(1)
    reference = send.json()["reference"]
    endpoint = "/api/ussd/callback"
    def call(phone, text, token="callback-test-secret"):
        return owner.post(endpoint, headers={"X-USSD-Token": token},
            data={"sessionId": "session-1", "serviceCode": "*123#",
                  "phoneNumber": phone, "text": text})
    assert call("+256700000001", "", "wrong").status_code == 403
    assert call("+256700000099", reference).text.startswith("END")
    assert call("+256700000001", reference).text.startswith("CON")
    terms = call("+256700000001", f"{reference}*{code}")
    assert terms.text.startswith("CON Agreement v1:")
    assert "UGX 2,000" in terms.text
    accepted = call("+256700000001", f"{reference}*{code}*1")
    assert accepted.text == "END Agreement version 1 accepted."
    again = call("+256700000001", f"{reference}*{code}*1")
    assert again.text.startswith("END")
    detail = owner.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").json()
    assert detail["status"] == "confirmed"
    assert len([event for event in detail["events"] if event["action"] == "accepted"]) == 1
    assert outsider.get(f"/api/businesses/{business_id}/agreements/{agreement_id}").status_code == 404
