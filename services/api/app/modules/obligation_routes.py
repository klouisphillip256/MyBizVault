from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db.models import Membership, User
from app.db.session import get_db
from app.modules import auth, obligations
from app.modules.business import require_manage_obligations, require_view_transactions
from app.modules.schemas import NegotiationIn, NegotiationResponseIn, PaymentRecordIn, PaymentStatusIn

router = APIRouter(prefix="/api/businesses/{business_id}/transactions/{transaction_id}")


@router.get("/payments")
def payments(business_id: str, transaction_id: str,
             _membership: Membership = Depends(require_view_transactions),
             db: DbSession = Depends(get_db)):
    return obligations.list_payments(db, business_id, transaction_id)


@router.post("/payments", status_code=201)
def payment_create(business_id: str, transaction_id: str, payload: PaymentRecordIn,
                   _membership: Membership = Depends(require_manage_obligations),
                   actor: tuple[User, object] = Depends(auth.csrf_session),
                   db: DbSession = Depends(get_db)):
    return obligations.create_payment(db, business_id, transaction_id, actor[0].id, payload)


@router.post("/payments/{payment_id}/status")
def payment_status(business_id: str, transaction_id: str, payment_id: str, payload: PaymentStatusIn,
                   _membership: Membership = Depends(require_manage_obligations),
                   actor: tuple[User, object] = Depends(auth.csrf_session),
                   db: DbSession = Depends(get_db)):
    return obligations.update_payment_status(db, business_id, transaction_id, payment_id, actor[0].id, payload)


@router.get("/negotiations")
def negotiations(business_id: str, transaction_id: str,
                 _membership: Membership = Depends(require_view_transactions),
                 db: DbSession = Depends(get_db)):
    return obligations.list_negotiations(db, business_id, transaction_id)


@router.post("/negotiations", status_code=201)
def negotiation_create(business_id: str, transaction_id: str, payload: NegotiationIn,
                       _membership: Membership = Depends(require_manage_obligations),
                       actor: tuple[User, object] = Depends(auth.csrf_session),
                       db: DbSession = Depends(get_db)):
    return obligations.create_negotiation(db, business_id, transaction_id, actor[0].id, payload)


@router.post("/negotiations/{negotiation_id}/response")
def negotiation_response(business_id: str, transaction_id: str, negotiation_id: str,
                         payload: NegotiationResponseIn,
                         _membership: Membership = Depends(require_manage_obligations),
                         actor: tuple[User, object] = Depends(auth.csrf_session),
                         db: DbSession = Depends(get_db)):
    return obligations.respond_negotiation(db, business_id, transaction_id,
                                           negotiation_id, actor[0].id, payload)


@router.get("/obligation-history")
def history(business_id: str, transaction_id: str,
            _membership: Membership = Depends(require_view_transactions),
            db: DbSession = Depends(get_db)):
    return obligations.list_history(db, business_id, transaction_id)
