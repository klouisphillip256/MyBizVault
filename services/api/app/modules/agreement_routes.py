from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session as DbSession

from app.db.models import Membership, User
from app.db.session import get_db
from app.modules import agreements, auth, receipts
from app.modules.business import require_manage_agreements
from app.modules.schemas import (AgreementAcceptIn, AgreementCreateIn, AgreementDraftIn,
                                 ExternalResponseIn, SendInvitationIn)

router = APIRouter(prefix="/api")


@router.get("/businesses/{business_id}/agreements")
def agreement_list(business_id: str, _membership: Membership = Depends(require_manage_agreements),
                   db: DbSession = Depends(get_db)):
    return agreements.list_agreements(db, business_id)


@router.post("/businesses/{business_id}/agreements", status_code=201)
def agreement_create(business_id: str, payload: AgreementCreateIn,
                     _membership: Membership = Depends(require_manage_agreements),
                     actor: tuple[User, object] = Depends(auth.csrf_session),
                     db: DbSession = Depends(get_db)):
    return agreements.create_draft(db, business_id, payload.transaction_id, actor[0].id)


@router.get("/businesses/{business_id}/agreements/{agreement_id}")
def agreement_detail(business_id: str, agreement_id: str,
                     _membership: Membership = Depends(require_manage_agreements),
                     db: DbSession = Depends(get_db)):
    return agreements.detail(db, business_id, agreement_id)


@router.get("/businesses/{business_id}/agreements/{agreement_id}/pdf")
def agreement_pdf(business_id: str, agreement_id: str, version: int | None = None,
                  download: bool = False,
                  _membership: Membership = Depends(require_manage_agreements),
                  db: DbSession = Depends(get_db)):
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.db.models import AgreementVersion
    agreement = agreements.require_agreement(db, business_id, agreement_id)
    number = version if version is not None else agreement.current_version
    entry = db.scalar(select(AgreementVersion).where(
        AgreementVersion.agreement_id == agreement.id, AgreementVersion.version == number))
    if entry is None:
        raise HTTPException(404, "Agreement version not found")
    if agreements.content_digest(entry.content) != entry.content_sha256:
        raise HTTPException(409, "Agreement version integrity check failed")
    disposition = "attachment" if download else "inline"
    return Response(receipts.agreement_pdf(entry.content, agreement.id, entry.version),
        media_type="application/pdf", headers={"Cache-Control": "private, no-store",
        "Content-Disposition": f'{disposition}; filename="agreement-{agreement.id}-v{entry.version}.pdf"'})


@router.put("/businesses/{business_id}/agreements/{agreement_id}/draft")
def agreement_revise(business_id: str, agreement_id: str, payload: AgreementDraftIn,
                     _membership: Membership = Depends(require_manage_agreements),
                     actor: tuple[User, object] = Depends(auth.csrf_session),
                     db: DbSession = Depends(get_db)):
    return agreements.revise_draft(db, business_id, agreement_id, actor[0].id, payload.content)


@router.post("/businesses/{business_id}/agreements/{agreement_id}/invitation")
def agreement_invite(business_id: str, agreement_id: str,
                     _membership: Membership = Depends(require_manage_agreements),
                     actor: tuple[User, object] = Depends(auth.csrf_session),
                     db: DbSession = Depends(get_db)):
    return agreements.create_invitation(db, business_id, agreement_id, actor[0].id)


@router.post("/businesses/{business_id}/agreements/{agreement_id}/invitation/send")
def agreement_send(business_id: str, agreement_id: str, payload: SendInvitationIn,
                   _membership: Membership = Depends(require_manage_agreements),
                   actor: tuple[User, object] = Depends(auth.csrf_session),
                   db: DbSession = Depends(get_db)):
    return agreements.send_invitation(db, business_id, agreement_id, actor[0].id, payload.channel)


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("/external/review")
def external_review(response: Response, token: str | None = Header(None, alias="X-Invitation-Token"),
                    db: DbSession = Depends(get_db)):
    private_response(response)
    return agreements.external_review(db, token)


@router.get("/external/pdf")
def external_agreement_pdf(token: str | None = Header(None, alias="X-Invitation-Token"),
                           db: DbSession = Depends(get_db)):
    _invitation, agreement, version = agreements.invitation_for_token(db, token, allow_completed=True)
    # Apply the same customer and business checks as the text review.
    agreements.external_review(db, token)
    pdf_response = Response(receipts.agreement_pdf(version.content, agreement.id, version.version),
        media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="agreement-{agreement.id}-v{version.version}.pdf"',
            "X-Content-Type-Options": "nosniff"})
    private_response(pdf_response)
    return pdf_response


@router.post("/external/challenge")
def external_challenge(response: Response, token: str | None = Header(None, alias="X-Invitation-Token"),
                       db: DbSession = Depends(get_db)):
    private_response(response)
    return agreements.issue_challenge(db, token)


@router.post("/external/accept")
def external_accept(payload: AgreementAcceptIn, response: Response,
                    token: str | None = Header(None, alias="X-Invitation-Token"),
                    db: DbSession = Depends(get_db)):
    private_response(response)
    return agreements.accept(db, token, payload.version_id, payload.code, payload.explicitly_accepted)


@router.post("/external/respond")
def external_respond(payload: ExternalResponseIn, response: Response,
                     token: str | None = Header(None, alias="X-Invitation-Token"),
                     db: DbSession = Depends(get_db)):
    private_response(response)
    return agreements.respond(db, token, payload.version_id, payload.action, payload.note)
