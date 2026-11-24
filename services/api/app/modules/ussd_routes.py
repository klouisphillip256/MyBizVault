import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.db.models import Membership, User
from app.db.session import get_db
from app.modules import auth, ussd
from app.modules.business import require_manage_agreements

router = APIRouter(prefix="/api")


@router.post("/businesses/{business_id}/agreements/{agreement_id}/ussd/send")
def send_ussd_code(business_id: str, agreement_id: str,
                   _membership: Membership = Depends(require_manage_agreements),
                   actor: tuple[User, object] = Depends(auth.csrf_session),
                   db: DbSession = Depends(get_db)):
    return ussd.send_request(db, business_id, agreement_id, actor[0].id)


@router.post("/ussd/callback")
async def callback(request: Request, x_ussd_token: str | None = Header(None),
                   db: DbSession = Depends(get_db)):
    token = x_ussd_token or request.query_params.get("token")
    if not settings.ussd_callback_token or not token or not hmac.compare_digest(token, settings.ussd_callback_token):
        raise HTTPException(403, "USSD callback authentication failed")
    form = await request.form()
    phone = str(form.get("phoneNumber") or "")
    text = str(form.get("text") or "")
    if not form.get("sessionId") or not phone or len(phone) > 32 or len(text) > 128:
        raise HTTPException(422, "Invalid USSD callback")
    return Response(ussd.callback(db, phone, text), media_type="text/plain",
        headers={"Cache-Control": "no-store"})
