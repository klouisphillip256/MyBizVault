from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.security import SESSION_DAYS, as_utc, digest, hash_password, new_session, verify_password
from app.db.models import Business, Membership, Session, User, utcnow
from app.db.session import get_db
from app.modules.schemas import LoginIn, RegisterIn

SESSION_COOKIE = "mbv_session"
CSRF_COOKIE = "mbv_csrf"


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    own_origin = str(request.base_url).rstrip("/")
    if origin and origin not in {settings.frontend_origin.rstrip("/"), own_origin}:
        raise HTTPException(403, "Request origin is not allowed")


def set_session_cookies(response: Response, token: str, csrf: str) -> None:
    max_age = int(timedelta(days=SESSION_DAYS).total_seconds())
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/api")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False,
                        secure=settings.cookie_secure, samesite="lax", path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api")
    response.delete_cookie(CSRF_COOKIE, path="/")


def current_session(request: Request, db: DbSession = Depends(get_db)) -> tuple[User, Session]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Sign in required")
    session = db.get(Session, digest(token))
    if session is None or as_utc(session.expires_at) <= utcnow():
        raise HTTPException(401, "Session expired")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user, session


def csrf_session(request: Request, actor: tuple[User, Session] = Depends(current_session)) -> tuple[User, Session]:
    check_origin(request)
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header or digest(csrf_header) != actor[1].csrf_hash:
        raise HTTPException(403, "Invalid request token")
    return actor


def membership_data(db: DbSession, membership: Membership) -> dict:
    business = db.get(Business, membership.business_id)
    return {"id": membership.id, "business_id": membership.business_id,
            "business_name": business.name if business else "",
            "business_phone": business.phone if business else None,
            "business_email": business.email if business else None, "role": membership.role,
            "can_view_transactions": membership.role == "owner" or membership.can_view_transactions or membership.can_manage_agreements or membership.can_manage_obligations,
            "can_create_transactions": membership.role == "owner" or membership.can_create_transactions,
            "can_manage_customers": membership.role == "owner" or membership.can_manage_customers,
            "can_manage_agreements": membership.role == "owner" or membership.can_manage_agreements,
            "can_view_documents": membership.role == "owner" or membership.can_view_documents or membership.can_manage_documents,
            "can_manage_documents": membership.role == "owner" or membership.can_manage_documents,
            "can_manage_obligations": membership.role == "owner" or membership.can_manage_obligations}


def user_data(db: DbSession, user: User) -> dict:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.is_active == True)).all()
    return {"id": user.id, "full_name": user.full_name, "email": user.email,
            "memberships": [membership_data(db, m) for m in memberships]}


def register(payload: RegisterIn, response: Response, db: DbSession, request: Request) -> dict:
    check_origin(request)
    user = User(email=payload.email.lower(), full_name=payload.full_name.strip(),
                password_hash=hash_password(payload.password), failed_logins=0)
    business = Business(name=payload.business_name.strip())
    try:
        db.add_all([user, business])
        db.flush()
        db.add(Membership(business_id=business.id, user_id=user.id, role="owner",
                          can_view_transactions=True, can_create_transactions=True,
                          can_manage_customers=True, can_manage_agreements=True,
                          can_view_documents=True, can_manage_documents=True,
                          can_manage_obligations=True, is_active=True))
        session, token, csrf = new_session(user.id)
        db.add(session)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    set_session_cookies(response, token, csrf)
    return user_data(db, user)


def login(payload: LoginIn, response: Response, db: DbSession, request: Request) -> dict:
    check_origin(request)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        verify_password(payload.password, hash_password("unmatched-account-password"))
        raise HTTPException(401, "Invalid email or password")
    if user.locked_until and as_utc(user.locked_until) > utcnow():
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= 5:
            user.locked_until = utcnow() + timedelta(minutes=15)
            user.failed_logins = 0
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    user.failed_logins = 0
    user.locked_until = None
    session, token, csrf = new_session(user.id)
    db.add(session)
    db.commit()
    set_session_cookies(response, token, csrf)
    return user_data(db, user)
