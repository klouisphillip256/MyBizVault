from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session as DbSession

from app.db.models import Membership, User
from app.db.session import get_db
from app.modules import auth, proposal_invitations
from app.modules.business import require_manage_obligations
from app.modules.schemas import ExternalProposalResponseIn, SendInvitationIn

router = APIRouter(prefix="/api")


def private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.post("/businesses/{business_id}/transactions/{transaction_id}/negotiations/{proposal_id}/invitation")
def create_invitation(business_id: str, transaction_id: str, proposal_id: str,
                      _membership: Membership = Depends(require_manage_obligations),
                      _actor: tuple[User, object] = Depends(auth.csrf_session),
                      db: DbSession = Depends(get_db)):
    return proposal_invitations.create_invitation(db, business_id, transaction_id, proposal_id)


@router.post("/businesses/{business_id}/transactions/{transaction_id}/negotiations/{proposal_id}/invitation/send")
def send_invitation(business_id: str, transaction_id: str, proposal_id: str, payload: SendInvitationIn,
                    _membership: Membership = Depends(require_manage_obligations),
                    _actor: tuple[User, object] = Depends(auth.csrf_session),
                    db: DbSession = Depends(get_db)):
    return proposal_invitations.send_invitation(db, business_id, transaction_id, proposal_id, payload.channel)


@router.get("/external/proposal")
def review(response: Response, token: str | None = Header(None, alias="X-Invitation-Token"),
           db: DbSession = Depends(get_db)):
    private(response)
    return proposal_invitations.review(db, token)


@router.post("/external/proposal/challenge")
def challenge(response: Response, token: str | None = Header(None, alias="X-Invitation-Token"),
              db: DbSession = Depends(get_db)):
    private(response)
    return proposal_invitations.issue_challenge(db, token)


@router.post("/external/proposal/respond")
def respond(payload: ExternalProposalResponseIn, response: Response,
            token: str | None = Header(None, alias="X-Invitation-Token"),
            db: DbSession = Depends(get_db)):
    private(response)
    return proposal_invitations.respond(db, token, payload.proposal_id, payload.action,
                                        payload.note, payload.code, payload.explicitly_accepted)
