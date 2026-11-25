"""Fictional lawyer directory and private, unsent consultation requests."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.security import utc_iso
from app.db.models import ConsultationRequest, Membership, User
from app.db.session import get_db
from app.modules.auth import csrf_session
from app.modules.business import require_owner

router = APIRouter(prefix="/api")

PROFILES = [
    {"id": "commercial", "name": "Amina Kato", "specialization": "Commercial lawyer", "focus": ["contracts", "supplier", "business"], "location": "Kampala", "consultation_method": "Video or office", "availability": "Demo: weekdays"},
    {"id": "contracts", "name": "Daniel Okello", "specialization": "Contract specialist", "focus": ["contracts", "supplier"], "location": "Entebbe", "consultation_method": "Video", "availability": "Demo: next week"},
    {"id": "employment", "name": "Grace Namuli", "specialization": "Employment lawyer", "focus": ["employment"], "location": "Kampala", "consultation_method": "Phone or office", "availability": "Demo: weekdays"},
    {"id": "debt", "name": "Peter Muwanga", "specialization": "Debt recovery specialist", "focus": ["debt", "dispute"], "location": "Jinja", "consultation_method": "Phone or video", "availability": "Demo: next week"},
    {"id": "mediator", "name": "Sarah Nabirye", "specialization": "Mediator", "focus": ["dispute", "mediation"], "location": "Kampala", "consultation_method": "Video or office", "availability": "Demo: weekdays"},
    {"id": "firm", "name": "Lakeview Legal Practice", "specialization": "Law firm", "focus": ["business", "contracts", "employment", "debt", "supplier", "dispute", "mediation"], "location": "Mbarara", "consultation_method": "Video or office", "availability": "Demo: by request"},
]
ISSUE_TYPES = {"business", "contracts", "employment", "debt", "supplier", "dispute", "mediation"}


class ConsultationIn(BaseModel):
    profile_id: str
    issue_type: Literal["business", "contracts", "employment", "debt", "supplier", "dispute", "mediation"]
    issue_summary: str = Field(min_length=20, max_length=2000)

    @field_validator("issue_summary", mode="before")
    @classmethod
    def trim_summary(cls, value):
        return value.strip() if isinstance(value, str) else value


def serialize(row: ConsultationRequest) -> dict:
    return {"id": row.id, "profile_id": row.profile_id, "issue_type": row.issue_type,
            "issue_summary": row.issue_summary, "status": row.status,
            "created_at": utc_iso(row.created_at)}


@router.get("/lawyers/profiles")
def profiles(issue_type: str | None = None):
    if issue_type and issue_type not in ISSUE_TYPES:
        raise HTTPException(422, "Unknown issue type")
    return [{**profile, "fictional": True} for profile in PROFILES
            if not issue_type or issue_type in profile["focus"]]


@router.get("/businesses/{business_id}/consultation-requests")
def list_requests(business_id: str, _owner: Membership = Depends(require_owner),
                  db: DbSession = Depends(get_db)):
    rows = db.scalars(select(ConsultationRequest).where(
        ConsultationRequest.business_id == business_id)
        .order_by(ConsultationRequest.created_at.desc()).limit(100)).all()
    return [serialize(row) for row in rows]


@router.post("/businesses/{business_id}/consultation-requests", status_code=201)
def create_request(business_id: str, payload: ConsultationIn,
                   _owner: Membership = Depends(require_owner),
                   actor: tuple[User, object] = Depends(csrf_session),
                   db: DbSession = Depends(get_db)):
    profile = next((item for item in PROFILES if item["id"] == payload.profile_id), None)
    if profile is None or payload.issue_type not in profile["focus"]:
        raise HTTPException(422, "Select a matching demonstration profile")
    row = ConsultationRequest(business_id=business_id, requested_by_user_id=actor[0].id,
        profile_id=payload.profile_id, issue_type=payload.issue_type,
        issue_summary=payload.issue_summary, status="draft")
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)
