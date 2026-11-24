from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.db.models import Business, Membership, User
from app.db.session import get_db
from app.core.delivery import capabilities
from app.modules import auth, records
from app.modules.business import (require_create_transactions, require_customers,
                                  require_manage_customers, require_owner,
                                  require_view_transactions)
from app.modules.schemas import (BusinessUpdateIn, CounterpartyIn, LoginIn, RegisterIn,
                                 StaffCreateIn, StaffUpdateIn, TransactionIn)

router = APIRouter(prefix="/api")


@router.get("/delivery/capabilities")
def delivery_capabilities(_actor: tuple[User, object] = Depends(auth.current_session)):
    return capabilities()


@router.post("/auth/register", status_code=201)
def register(payload: RegisterIn, request: Request, response: Response, db: DbSession = Depends(get_db)):
    return auth.register(payload, response, db, request)


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: DbSession = Depends(get_db)):
    return auth.login(payload, response, db, request)


@router.get("/auth/me")
def me(actor: tuple[User, object] = Depends(auth.current_session), db: DbSession = Depends(get_db)):
    return auth.user_data(db, actor[0])


@router.post("/auth/logout", status_code=204)
def logout(response: Response, actor: tuple[User, object] = Depends(auth.csrf_session),
           db: DbSession = Depends(get_db)):
    db.delete(actor[1])
    db.commit()
    auth.clear_session_cookies(response)


@router.patch("/businesses/{business_id}")
def rename_business(business_id: str, payload: BusinessUpdateIn,
                    _owner: Membership = Depends(require_owner),
                    _actor: tuple[User, object] = Depends(auth.csrf_session),
                    db: DbSession = Depends(get_db)):
    return records.update_business(db, business_id, payload.name)


@router.get("/businesses/{business_id}/staff")
def staff_list(business_id: str, _owner: Membership = Depends(require_owner),
               db: DbSession = Depends(get_db)):
    return records.list_staff(db, business_id)


@router.post("/businesses/{business_id}/staff", status_code=201)
def staff_create(business_id: str, payload: StaffCreateIn,
                 _owner: Membership = Depends(require_owner),
                 _actor: tuple[User, object] = Depends(auth.csrf_session),
                 db: DbSession = Depends(get_db)):
    return records.create_staff(db, business_id, payload)


@router.patch("/businesses/{business_id}/staff/{staff_id}")
def staff_update(business_id: str, staff_id: str, payload: StaffUpdateIn,
                 _owner: Membership = Depends(require_owner),
                 _actor: tuple[User, object] = Depends(auth.csrf_session),
                 db: DbSession = Depends(get_db)):
    return records.update_staff(db, business_id, staff_id, payload)


@router.get("/businesses/{business_id}/customers")
def customer_list(business_id: str, _membership: Membership = Depends(require_customers),
                  db: DbSession = Depends(get_db)):
    return records.list_customers(db, business_id,
                                  include_contact=_membership.role == "owner" or _membership.can_manage_customers)


@router.post("/businesses/{business_id}/customers", status_code=201)
def customer_create(business_id: str, payload: CounterpartyIn,
                    _membership: Membership = Depends(require_manage_customers),
                    _actor: tuple[User, object] = Depends(auth.csrf_session),
                    db: DbSession = Depends(get_db)):
    return records.create_customer(db, business_id, payload)


@router.put("/businesses/{business_id}/customers/{customer_id}")
def customer_update(business_id: str, customer_id: str, payload: CounterpartyIn,
                    _membership: Membership = Depends(require_manage_customers),
                    _actor: tuple[User, object] = Depends(auth.csrf_session),
                    db: DbSession = Depends(get_db)):
    return records.update_customer(db, business_id, customer_id, payload)


@router.get("/businesses/{business_id}/transactions")
def transaction_list(business_id: str, _membership: Membership = Depends(require_view_transactions),
                     db: DbSession = Depends(get_db)):
    return records.list_transactions(db, business_id)


@router.post("/businesses/{business_id}/transactions", status_code=201)
def transaction_create(business_id: str, payload: TransactionIn,
                       membership: Membership = Depends(require_create_transactions),
                       actor: tuple[User, object] = Depends(auth.csrf_session),
                       db: DbSession = Depends(get_db)):
    return records.create_transaction(db, membership.business_id, actor[0].id, payload)


@router.get("/businesses/{business_id}/transactions/{transaction_id}")
def transaction_detail(business_id: str, transaction_id: str,
                       _membership: Membership = Depends(require_view_transactions),
                       db: DbSession = Depends(get_db)):
    return records.get_transaction(db, business_id, transaction_id)
