import hashlib
import io

import pytest

from app.core.config import settings
from app.core.storage import LocalStorage, S3Storage
from test_phase2 import clients, csrf, register  # noqa: F401 - shared fixture and helpers


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path / "vault"))


def upload(client, business_id, name="receipt.pdf", content=b"%PDF-1.4\nexample", category="receipt"):
    return client.post(f"/api/businesses/{business_id}/documents", headers=csrf(client),
                       data={"title": "Bosco receipt", "category": category},
                       files={"file": (name, content, "application/octet-stream")})


def test_upload_versions_search_download_integrity_and_isolation(clients, tmp_path):
    owner, other, staff = clients
    business_id = register(owner, "mike@example.com", "Mike Wholesale")
    other_id = register(other, "other@example.com", "Other Business")
    initial = b"%PDF-1.4\nexample receipt"
    created = upload(owner, business_id, "..\\Bosco receipt.pdf", initial)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    assert created.json()["current_version"] == 1
    assert created.json()["versions"][0]["filename"] == "Bosco receipt.pdf"
    assert created.json()["versions"][0]["sha256"] == hashlib.sha256(initial).hexdigest()
    assert len(owner.get(f"/api/businesses/{business_id}/documents?q=Bosco&category=receipt").json()) == 1
    assert owner.get(f"/api/businesses/{business_id}/documents?category=contract").json() == []
    assert other.get(f"/api/businesses/{business_id}/documents/{document_id}").status_code == 404
    assert other.get(f"/api/businesses/{other_id}/documents/{document_id}").status_code == 404
    assert staff.get(f"/api/businesses/{business_id}/documents").status_code == 401
    inline = owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/1/content")
    assert inline.status_code == 200
    assert inline.content == initial
    assert inline.headers["cache-control"] == "private, no-store"
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert inline.headers["content-disposition"].startswith("inline")
    downloaded = owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/1/content?download=true")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-disposition"].startswith("attachment")
    assert any(event["action"] == "downloaded" for event in owner.get(
        f"/api/businesses/{business_id}/documents/{document_id}").json()["events"])
    image = b"\x89PNG\r\n\x1a\n" + b"example image"
    newer = owner.post(f"/api/businesses/{business_id}/documents/{document_id}/versions",
                       headers=csrf(owner), files={"file": ("photo.png", image, "image/png")})
    assert newer.status_code == 201, newer.text
    assert newer.json()["current_version"] == 2
    assert len(newer.json()["versions"]) == 2
    assert owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/1/content").content == initial
    assert owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/2/content").content == image
    objects = list((tmp_path / "vault").rglob("*"))
    first_object = next(path for path in objects if path.is_file() and path.read_bytes() == initial)
    first_object.write_bytes(b"tampered")
    assert owner.get(f"/api/businesses/{business_id}/documents/{document_id}/versions/1/content").status_code == 409


def test_upload_limits_and_staff_permissions(clients):
    owner, _other, staff = clients
    business_id = register(owner, "owner@example.com", "Owner Business")
    assert upload(owner, business_id, content=b"<html>not a PDF</html>").status_code == 415
    assert upload(owner, business_id, content=b"").status_code == 422
    assert upload(owner, business_id, content=b"%PDF-" + b"x" * (10 * 1024 * 1024)).status_code == 413
    document = upload(owner, business_id).json()
    staff_account = owner.post(f"/api/businesses/{business_id}/staff", headers=csrf(owner),
                               json={"full_name": "Sales Staff", "email": "sales@example.com",
                                     "password": "staff-password-2026", "can_manage_agreements": True})
    assert staff_account.status_code == 201
    assert staff.post("/api/auth/login", json={"email": "sales@example.com",
                                                  "password": "staff-password-2026"}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/documents").status_code == 403
    assert staff.get(f"/api/businesses/{business_id}/documents/{document['id']}/versions/1/content").status_code == 403
    assert owner.patch(f"/api/businesses/{business_id}/staff/{staff_account.json()['id']}",
                       headers=csrf(owner), json={"can_view_transactions": True,
                                                  "can_create_transactions": False,
                                                  "can_manage_customers": False,
                                                  "can_manage_agreements": True,
                                                  "can_view_documents": True,
                                                  "can_manage_documents": False,
                                                  "is_active": True}).status_code == 200
    assert staff.get(f"/api/businesses/{business_id}/documents").status_code == 200
    assert upload(staff, business_id).status_code == 403
    assert owner.patch(f"/api/businesses/{business_id}/staff/{staff_account.json()['id']}",
                       headers=csrf(owner), json={"can_view_transactions": True,
                                                  "can_create_transactions": False,
                                                  "can_manage_customers": False,
                                                  "can_manage_agreements": True,
                                                  "can_view_documents": True,
                                                  "can_manage_documents": True,
                                                  "is_active": True}).status_code == 200
    assert upload(staff, business_id).status_code == 201


def test_storage_adapters_keep_private_keys(tmp_path, monkeypatch):
    local = LocalStorage(str(tmp_path / "private"))
    local.put("business/document/v1/object", b"data", "application/pdf")
    assert local.get("business/document/v1/object") == b"data"
    with pytest.raises(ValueError):
        local.get("../outside")
    local.delete("business/document/v1/object")
    assert not (tmp_path / "private" / "business" / "document" / "v1" / "object").exists()

    class FakeClient:
        def __init__(self):
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs["Body"]
            assert "ACL" not in kwargs

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            del self.objects[kwargs["Key"]]

    fake = FakeClient()
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: fake)
    s3 = S3Storage("private-bucket", "https://s3.example.com", "us-east-1")
    s3.put("business/document/v1/object", b"data", "application/pdf")
    assert s3.get("business/document/v1/object") == b"data"
    s3.delete("business/document/v1/object")
    assert fake.objects == {}
