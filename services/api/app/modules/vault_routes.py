from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session as DbSession

from app.db.models import Business, Membership, User
from app.db.session import get_db
from app.modules import auth, receipts, vault
from app.modules.schemas import ContractDraftIn
from app.modules.business import require_manage_agreements, require_manage_documents, require_view_documents

router = APIRouter(prefix="/api/businesses/{business_id}")


@router.post("/contracts/drafts", status_code=201)
def contract_draft(business_id: str, payload: ContractDraftIn,
                   _membership: Membership = Depends(require_manage_documents),
                   actor: tuple[User, object] = Depends(auth.csrf_session),
                   db: DbSession = Depends(get_db)):
    business = db.get(Business, business_id)
    data = receipts.contract_draft_pdf(payload.title, business.name, payload.counterparty_name,
        payload.purpose, payload.payment_terms, payload.obligations)
    return vault.create_upload(db, business_id, actor[0].id, payload.title, "contract",
        "contract-draft.pdf", data)


@router.get("/documents")
def document_list(business_id: str, q: str | None = Query(None, max_length=100),
                  category: str | None = Query(None),
                  _membership: Membership = Depends(require_view_documents),
                  db: DbSession = Depends(get_db)):
    return vault.list_documents(db, business_id, q, category)


@router.post("/documents", status_code=201)
def document_upload(business_id: str, title: str = Form(...),
                    category: Literal["contract", "receipt", "image", "other"] = Form(...),
                    file: UploadFile = File(...),
                    _membership: Membership = Depends(require_manage_documents),
                    actor: tuple[User, object] = Depends(auth.csrf_session),
                    db: DbSession = Depends(get_db)):
    data = file.file.read(vault.MAX_FILE_BYTES + 1)
    return vault.create_upload(db, business_id, actor[0].id, title, category, file.filename, data)


@router.get("/documents/{document_id}")
def document_detail(business_id: str, document_id: str,
                    _membership: Membership = Depends(require_view_documents),
                    db: DbSession = Depends(get_db)):
    return vault.detail(db, business_id, document_id)


@router.post("/documents/{document_id}/versions", status_code=201)
def document_new_version(business_id: str, document_id: str,
                         file: UploadFile = File(...),
                         _membership: Membership = Depends(require_manage_documents),
                         actor: tuple[User, object] = Depends(auth.csrf_session),
                         db: DbSession = Depends(get_db)):
    data = file.file.read(vault.MAX_FILE_BYTES + 1)
    return vault.add_upload_version(db, business_id, document_id, actor[0].id, file.filename, data)


@router.get("/documents/{document_id}/versions/{version_number}/content")
def document_content(business_id: str, document_id: str, version_number: int,
                     download: bool = False,
                     membership: Membership = Depends(require_view_documents),
                     actor: tuple[User, object] = Depends(auth.current_session),
                     db: DbSession = Depends(get_db)):
    version, data = vault.load_version_bytes(db, business_id, document_id,
                                             version_number, actor[0].id, download)
    disposition = "attachment" if download else "inline"
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox",
               "Content-Disposition": f'{disposition}; filename="{version.filename}"'}
    return Response(content=data, media_type=version.content_type, headers=headers)


@router.post("/agreements/{agreement_id}/vault-document")
def archive_agreement(business_id: str, agreement_id: str,
                      _agreement_permission: Membership = Depends(require_manage_agreements),
                      _document_permission: Membership = Depends(require_manage_documents),
                      _actor: tuple[User, object] = Depends(auth.csrf_session),
                      db: DbSession = Depends(get_db)):
    return vault.archive_existing_agreement(db, business_id, agreement_id)
