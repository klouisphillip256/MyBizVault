"""Document metadata, business isolation and integrity checks."""

import hashlib
import re
import secrets
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.security import utc_iso
from app.core.storage import ObjectStorage, get_storage
from app.db.models import (Agreement, AgreementVersion, Counterparty, Document,
                           DocumentEvent, DocumentVersion, Transaction)

MAX_FILE_BYTES = 10 * 1024 * 1024
UPLOAD_CATEGORIES = {"contract", "receipt", "image", "other"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_file(data: bytes) -> tuple[str, str]:
    if not data:
        raise HTTPException(422, "Choose a non-empty file")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "Files must be 10 MB or smaller")
    if data.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    raise HTTPException(415, "Upload a PDF, PNG or JPEG file")


def safe_filename(filename: str | None, extension: str) -> str:
    leaf = PurePosixPath((filename or "document").replace("\\", "/")).name
    stem = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
    stem = re.sub(r"[^A-Za-z0-9._ -]", "_", stem).strip(" ._")[:140] or "document"
    return stem + extension


def object_key(business_id: str, document_id: str, version: int) -> str:
    return f"{business_id}/{document_id}/v{version}/{secrets.token_hex(16)}"


def version_data(version: DocumentVersion) -> dict:
    return {"id": version.id, "version": version.version, "filename": version.filename,
            "content_type": version.content_type, "size_bytes": version.size_bytes,
            "sha256": version.sha256, "created_at": utc_iso(version.created_at)}


def current_version(db: DbSession, document: Document) -> DocumentVersion:
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document.id,
                                                      DocumentVersion.version == document.current_version))
    if version is None:
        raise HTTPException(409, "Document version metadata is missing")
    return version


def summary(db: DbSession, document: Document) -> dict:
    version = current_version(db, document)
    return {"id": document.id, "title": document.title, "category": document.category,
            "source": document.source, "agreement_version_id": document.agreement_version_id,
            "current_version": document.current_version, "created_at": utc_iso(document.created_at),
            "current_file": version_data(version)}


def list_documents(db: DbSession, business_id: str, query: str | None, category: str | None) -> list[dict]:
    statement = select(Document).where(Document.business_id == business_id)
    if category:
        if category not in UPLOAD_CATEGORIES | {"agreement"}:
            raise HTTPException(422, "Unknown document category")
        statement = statement.where(Document.category == category)
    if query and query.strip():
        term = f"%{query.strip()[:100]}%"
        matching_files = select(DocumentVersion.document_id).where(DocumentVersion.filename.ilike(term))
        statement = statement.where(or_(Document.title.ilike(term), Document.id.in_(matching_files)))
    documents = db.scalars(statement.order_by(Document.created_at.desc()).limit(100)).all()
    return [summary(db, document) for document in documents]


def require_document(db: DbSession, business_id: str, document_id: str) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id,
                                                Document.business_id == business_id))
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


def detail(db: DbSession, business_id: str, document_id: str) -> dict:
    document = require_document(db, business_id, document_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                          .order_by(DocumentVersion.version.desc())).all()
    events = db.scalars(select(DocumentEvent).where(DocumentEvent.document_id == document.id)
                        .order_by(DocumentEvent.created_at)).all()
    return {**summary(db, document), "versions": [version_data(version) for version in versions],
            "events": [{"action": event.action, "version_id": event.document_version_id,
                        "created_at": utc_iso(event.created_at)} for event in events]}


def storage() -> ObjectStorage:
    try:
        return get_storage()
    except Exception:
        raise HTTPException(503, "Private storage is not configured") from None


def store_bytes(provider: ObjectStorage, key: str, data: bytes, media_type: str) -> None:
    try:
        provider.put(key, data, media_type)
    except Exception:
        raise HTTPException(503, "Private storage could not save the file") from None


def cleanup(provider: ObjectStorage, key: str | None) -> None:
    if key:
        try:
            provider.delete(key)
        except Exception:
            pass  # A later orphan sweep can remove an unreferenced object.


def create_upload(db: DbSession, business_id: str, user_id: str, title: str,
                  category: str, filename: str | None, data: bytes) -> dict:
    title = title.strip()
    if len(title) < 2 or len(title) > 180 or category not in UPLOAD_CATEGORIES:
        raise HTTPException(422, "Enter a title and valid category")
    media_type, extension = detect_file(data)
    document = Document(business_id=business_id, title=title, category=category,
                        source="upload", current_version=1, created_by_user_id=user_id)
    db.add(document)
    db.flush()
    key = object_key(business_id, document.id, 1)
    provider = storage()
    try:
        store_bytes(provider, key, data, media_type)
        version = DocumentVersion(document_id=document.id, version=1, storage_key=key,
                                  sha256=sha256(data), size_bytes=len(data),
                                  content_type=media_type, filename=safe_filename(filename, extension),
                                  created_by_user_id=user_id)
        db.add(version)
        db.flush()
        db.add(DocumentEvent(business_id=business_id, document_id=document.id,
                             document_version_id=version.id, actor_user_id=user_id,
                             action="uploaded"))
        db.commit()
    except Exception:
        db.rollback()
        cleanup(provider, key)
        raise
    return detail(db, business_id, document.id)


def add_upload_version(db: DbSession, business_id: str, document_id: str,
                       user_id: str, filename: str | None, data: bytes) -> dict:
    document = require_document(db, business_id, document_id)
    if document.source != "upload":
        raise HTTPException(409, "Confirmed agreement documents cannot be replaced")
    media_type, extension = detect_file(data)
    next_version = document.current_version + 1
    key = object_key(business_id, document.id, next_version)
    provider = storage()
    try:
        store_bytes(provider, key, data, media_type)
        version = DocumentVersion(document_id=document.id, version=next_version, storage_key=key,
                                  sha256=sha256(data), size_bytes=len(data),
                                  content_type=media_type, filename=safe_filename(filename, extension),
                                  created_by_user_id=user_id)
        db.add(version)
        db.flush()
        document.current_version = next_version
        db.add(DocumentEvent(business_id=business_id, document_id=document.id,
                             document_version_id=version.id, actor_user_id=user_id,
                             action="new_version"))
        db.commit()
    except IntegrityError:
        db.rollback()
        cleanup(provider, key)
        raise HTTPException(409, "Document changed while uploading; refresh and try again") from None
    except Exception:
        db.rollback()
        cleanup(provider, key)
        raise
    return detail(db, business_id, document.id)


def load_version_bytes(db: DbSession, business_id: str, document_id: str,
                       version_number: int, user_id: str, record_download: bool) -> tuple[DocumentVersion, bytes]:
    document = require_document(db, business_id, document_id)
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document.id,
                                                      DocumentVersion.version == version_number))
    if version is None:
        raise HTTPException(404, "Document version not found")
    try:
        data = storage().get(version.storage_key)
    except FileNotFoundError:
        raise HTTPException(409, "Stored document is unavailable") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Private storage could not retrieve the file") from None
    if len(data) != version.size_bytes or sha256(data) != version.sha256:
        raise HTTPException(409, "Document integrity check failed")
    if record_download:
        db.add(DocumentEvent(business_id=business_id, document_id=document.id,
                             document_version_id=version.id, actor_user_id=user_id,
                             action="downloaded"))
        db.commit()
    return version, data


def stage_confirmed_agreement(db: DbSession, agreement: Agreement,
                              version: AgreementVersion) -> tuple[Document, str | None, ObjectStorage | None]:
    existing = db.scalar(select(Document).where(Document.agreement_version_id == version.id))
    if existing:
        return existing, None, None
    transaction = db.get(Transaction, agreement.transaction_id)
    customer = db.get(Counterparty, transaction.counterparty_id)
    data = version.content.encode("utf-8")
    if sha256(data) != version.content_sha256:
        raise HTTPException(409, "Agreement version integrity check failed")
    document = Document(business_id=agreement.business_id,
                        title=f"Credit sale agreement — {customer.display_name}",
                        category="agreement", source="agreement",
                        agreement_version_id=version.id, current_version=1)
    db.add(document)
    db.flush()
    key = object_key(agreement.business_id, document.id, 1)
    provider = storage()
    try:
        store_bytes(provider, key, data, "text/plain; charset=utf-8")
        file_version = DocumentVersion(document_id=document.id, version=1,
                                       storage_key=key, sha256=sha256(data), size_bytes=len(data),
                                       content_type="text/plain; charset=utf-8",
                                       filename=f"agreement-version-{version.version}.txt")
        db.add(file_version)
        db.flush()
        db.add(DocumentEvent(business_id=agreement.business_id, document_id=document.id,
                             document_version_id=file_version.id, action="agreement_preserved"))
    except Exception:
        cleanup(provider, key)
        raise
    return document, key, provider


def archive_existing_agreement(db: DbSession, business_id: str, agreement_id: str) -> dict:
    from app.modules.agreements import current_version, require_agreement

    agreement = require_agreement(db, business_id, agreement_id)
    if agreement.status != "confirmed":
        raise HTTPException(409, "Only confirmed agreements can be preserved in the Vault")
    version = current_version(db, agreement)
    key = None
    provider = None
    try:
        document, key, provider = stage_confirmed_agreement(db, agreement, version)
        db.commit()
    except IntegrityError:
        db.rollback()
        if provider:
            cleanup(provider, key)
        raise HTTPException(409, "Agreement was already preserved; refresh and try again") from None
    except Exception:
        db.rollback()
        if provider:
            cleanup(provider, key)
        raise
    return detail(db, business_id, document.id)
