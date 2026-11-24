from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import Business, Membership, User
from app.db.session import get_db
from app.modules.auth import current_session


def require_membership(business_id: str, actor: tuple[User, object] = Depends(current_session),
                       db: DbSession = Depends(get_db)) -> Membership:
    membership = db.scalar(select(Membership).where(Membership.business_id == business_id,
                                                    Membership.user_id == actor[0].id,
                                                    Membership.is_active == True))
    if membership is None:
        raise HTTPException(404, "Business not found")
    return membership


def require_owner(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner":
        raise HTTPException(403, "Owner permission required")
    return membership


def require_view_transactions(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not (membership.can_view_transactions or membership.can_manage_agreements or membership.can_manage_obligations):
        raise HTTPException(403, "Transaction access not granted")
    return membership


def require_create_transactions(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not membership.can_create_transactions:
        raise HTTPException(403, "Transaction creation not granted")
    return membership


def require_customers(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not (membership.can_manage_customers or membership.can_create_transactions):
        raise HTTPException(403, "Customer access not granted")
    return membership


def require_manage_customers(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not membership.can_manage_customers:
        raise HTTPException(403, "Customer management not granted")
    return membership


def require_manage_agreements(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not membership.can_manage_agreements:
        raise HTTPException(403, "Agreement access not granted")
    return membership


def require_view_documents(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not (membership.can_view_documents or membership.can_manage_documents):
        raise HTTPException(403, "Document access not granted")
    return membership


def require_manage_documents(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not membership.can_manage_documents:
        raise HTTPException(403, "Document management not granted")
    return membership


def require_manage_obligations(membership: Membership = Depends(require_membership)) -> Membership:
    if membership.role != "owner" and not membership.can_manage_obligations:
        raise HTTPException(403, "Obligation management not granted")
    return membership
