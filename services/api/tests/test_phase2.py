import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import get_db
from app.main import app


@pytest.fixture
def clients():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    def db_override():
        with DbSession(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as staff:
        yield owner, other, staff
    app.dependency_overrides.clear()
    engine.dispose()


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("mbv_csrf")}


def register(client: TestClient, email: str, business: str):
    response = client.post("/api/auth/register", json={"full_name": "Mike Owner", "email": email,
                                                       "password": "correct-horse-2026", "business_name": business})
    assert response.status_code == 201, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    return response.json()["memberships"][0]["business_id"]


def test_credit_sale_isolated_and_validated(clients):
    owner, other, _staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    other_id = register(other, "other@example.com", "Other Business")
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
                          json={"display_name": "Bosco Okello", "phone": "+256700000001"})
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]
    payload = {"counterparty_id": customer_id, "description": "Wholesale goods", "transaction_date": "2026-11-24",
               "total_ugx": 1_000_000, "paid_ugx": 700_000, "due_date": "2026-12-01"}
    assert owner.post(f"/api/businesses/{business_id}/transactions", json=payload).status_code == 403
    created = owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner), json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["balance_ugx"] == 300_000
    assert created.json()["payment_record_status"] == "reported"
    assert created.json()["created_at"].endswith("Z")
    assert len(owner.get(f"/api/businesses/{business_id}/transactions").json()) == 1
    assert other.get(f"/api/businesses/{business_id}/transactions").status_code == 404
    assert other.get(f"/api/businesses/{business_id}/transactions/{created.json()['id']}").status_code == 404
    assert other.post(f"/api/businesses/{other_id}/transactions", headers=csrf(other), json=payload).status_code == 404
    assert owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
                      json={**payload, "paid_ugx": 1_000_001}).status_code == 422
    assert owner.post(f"/api/businesses/{business_id}/transactions", headers=csrf(owner),
                      json={**payload, "due_date": None}).status_code == 422
    assert owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
                      json={"display_name": "No Contact"}).status_code == 422


def test_transaction_retry_id_is_idempotent_and_business_scoped(clients):
    owner, other, _staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    other_id = register(other, "other@example.com", "Other Business")
    request_id = "e24c55d1-1050-4083-9130-60257af090f2"
    for client, own_id in [(owner, business_id), (other, other_id)]:
        customer = client.post(f"/api/businesses/{own_id}/customers", headers=csrf(client),
            json={"display_name": "Buyer", "phone": "+256700000001"}).json()
        payload = {"client_request_id": request_id, "counterparty_id": customer["id"],
            "description": "Wholesale goods", "transaction_date": "2026-11-24",
            "total_ugx": 1000, "paid_ugx": 200, "due_date": "2026-12-01"}
        first = client.post(f"/api/businesses/{own_id}/transactions", headers=csrf(client), json=payload)
        again = client.post(f"/api/businesses/{own_id}/transactions", headers=csrf(client), json=payload)
        assert first.status_code == again.status_code == 201
        assert first.json()["id"] == again.json()["id"]
        assert len(client.get(f"/api/businesses/{own_id}/transactions").json()) == 1
        changed = client.post(f"/api/businesses/{own_id}/transactions", headers=csrf(client),
            json={**payload, "total_ugx": 2000})
        assert changed.status_code == 409


def test_staff_permissions_and_session_revocation(clients):
    owner, _other, staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    added = owner.post(f"/api/businesses/{business_id}/staff", headers=csrf(owner),
                       json={"full_name": "Sales Person", "email": "sales@example.com",
                             "password": "staff-password-2026"})
    assert added.status_code == 201, added.text
    staff_id = added.json()["id"]
    assert staff.post("/api/auth/login", json={"email": "sales@example.com", "password": "staff-password-2026"}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/transactions").status_code == 403
    assert staff.get(f"/api/businesses/{business_id}/staff").status_code == 403
    customer = owner.post(f"/api/businesses/{business_id}/customers", headers=csrf(owner),
                          json={"display_name": "Private Contact", "phone": "+256700000003"})
    assert customer.status_code == 201
    changed = owner.patch(f"/api/businesses/{business_id}/staff/{staff_id}", headers=csrf(owner),
                          json={"can_view_transactions": True, "can_create_transactions": True,
                                "can_manage_customers": False, "is_active": True})
    assert changed.status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/transactions").status_code == 200
    staff_customers = staff.get(f"/api/businesses/{business_id}/customers")
    assert staff_customers.status_code == 200
    assert staff_customers.json()[0]["display_name"] == "Private Contact"
    assert staff_customers.json()[0]["phone"] is None
    assert staff.put(f"/api/businesses/{business_id}/customers/{customer.json()['id']}",
                     headers=csrf(staff), json={"display_name": "Not Allowed", "phone": "+256700000004"}).status_code == 403
    corrected = owner.put(f"/api/businesses/{business_id}/customers/{customer.json()['id']}",
                          headers=csrf(owner), json={"display_name": "Correct Contact", "phone": "+256700000003"})
    assert corrected.status_code == 200
    assert corrected.json()["display_name"] == "Correct Contact"
    assert owner.patch(f"/api/businesses/{business_id}/staff/{staff_id}", headers=csrf(owner),
                       json={"can_view_transactions": True, "can_create_transactions": True,
                             "can_manage_customers": True, "is_active": True}).status_code == 200
    assert staff.post(f"/api/businesses/{business_id}/customers", headers=csrf(staff),
                      json={"display_name": "Staff Customer", "phone": "+256700000002"}).status_code == 201
    assert staff.patch(f"/api/businesses/{business_id}", headers=csrf(staff),
                       json={"name": "Unauthorized"}).status_code == 403
    assert owner.patch(f"/api/businesses/{business_id}/staff/{staff_id}", headers=csrf(owner),
                       json={"can_view_transactions": False, "can_create_transactions": False,
                             "can_manage_customers": False, "is_active": False}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/transactions").status_code == 404
    assert staff.post("/api/auth/logout", headers=csrf(staff)).status_code == 204
    assert staff.get("/api/auth/me").status_code == 401


def test_login_origin_and_lockout(clients):
    owner, _other, _staff = clients
    blocked = owner.post("/api/auth/register", headers={"Origin": "https://untrusted.example.com"},
                         json={"full_name": "Blocked Owner", "email": "blocked@example.com",
                               "password": "correct-horse-2026", "business_name": "Blocked Business"})
    assert blocked.status_code == 403
    register(owner, "mike@example.com", "Mike Wholesale")
    assert owner.get("/api/auth/me").status_code == 200
    for _ in range(5):
        assert owner.post("/api/auth/login", json={"email": "mike@example.com", "password": "wrong"}).status_code == 401
    assert owner.post("/api/auth/login", json={"email": "mike@example.com",
                                                 "password": "correct-horse-2026"}).status_code == 401
